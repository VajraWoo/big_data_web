# Tasks：家电整机评论洞察

## 已完成基础

- [x] T001 Spark清洗2,128,605条评论和94,327条商品元数据。
- [x] T002 fastText完成语言识别与文本画像，得到1,815,794条有效英文评论。
- [x] T003 VADER完成1,815,794条评论的整体情感。
- [x] T004 按批准规则确定139个整机商品、13类、116,728条正式评论。
- [x] T005 验证`yangheng/deberta-v3-base-end2end-absa`可在Intel Arc XPU运行并记录吞吐、内存和示例输出。

## 历史业务链与冻结输入

- [x] T006 实现正式范围导出和评论句子/长文本分块。
  - 验收：输入商品恰为139个；评论恰为116,728条；每条评论具有唯一处理状态。
  - 验证：重算不同`review_id`和`parent_asin`并与scope Gold核对。
- [x] T007-legacy 实现Windows XPU ABSA分片推理（历史 baseline，已否决为正式来源）。
  - 验收：输出属性、属性极性、置信度、位置、原句、模型revision；无CPU回退；可断点续跑。
  - 验证：输入数＝成功＋无属性＋失败，属性位置能回指原句。
- [x] T008-legacy 检查`cross-encoder/nli-MiniLM2-L6-H768`的XPU兼容和固定吞吐（历史 baseline）。
  - 验收：能输出entailment/neutral/contradiction；记录模型revision、批次、内存和速度。
  - 验证：固定语义用例通过；不比较其他模型。
- [x] T009-legacy 使用已有全量NLI三分类分数重新确认明确建议（历史 baseline，已否决为 attribution patch）。
  - 验收：不使用关键词或MiniLM前置召回；entailment同时高于neutral和contradiction才接受；保存三项分数、原句和评论ID；不重复执行XPU推理。
  - 验证：459,186句＝建议＋非建议＋失败；neutral最高的句子不进入建议；固定正反例可解释。
- [x] T010-legacy 分开实现评价主题、改进需求的每商品Fast Community Detection和自动命名（历史 baseline）。
  - 验收：正负评价只来自对应ABSA；改进需求只来自合格建议和隐式问题候选；来源可追溯；不跨商品或主题类型聚类；不生成fallback。
  - 验证：三个分析维度均有完成状态；允许`ready/0/no_qualified_theme`；主题成员、中心句和名称均可回查。

## 当前任务：新版 T007

- [x] T007 执行完整评论上下文的结构化 insight 全量候选运行。
  - 输入：冻结的 T006-v2 `review_inputs.parquet`，读取 `text_raw`、商品标识、标题和类目。
  - 输出：`topic_raw/polarity/evidence/target_scope`、程序计算的 evidence offsets、`model_id/revision/prompt_version/processing_status`，以及可选 `rejected_insights`。
  - 当前执行：`Qwen/Qwen3.5-4B`＋NVIDIA/Linux vLLM continuous batching＋原生 structured JSON；prompt v2.1；全局生成上限1024 tokens。
  - 状态：每条输入保留 `success|partial_success|failed`；逐 insight 校验允许保留合法结果并记录被拒绝项；禁止 silent CPU fallback。
  - 依据：旧串行 runner 约0.033 reviews/s，已因吞吐淘汰；vLLM 初版全量约12 reviews/s。200条人工复核为89严格通过、38轻微问题、73失败；v2.1重跑73条后41通过、19轻微、13失败；25条退化检查为19不变或更好、5轻微变化、1明显退化且未新增严重scope错误。1024 tokens修复已知长评论JSON截断。
  - 边界：不得训练或微调、覆盖旧产物或写入人工 Gold。batch、GPU、生成上限、prompt和后端是可调整运行参数，不作为永久业务约束。
  - 完成条件：当前116,728条候选运行结束后，对账输入、输出和各处理状态数量并保存最终运行摘要；完成不等于自动发布为正式Gold。
  - 全量运行结果（2026-09-08）：进程正常结束；输入/输出均为116,728行且JSON逐行可解析，`review_id`均唯一，零缺失、零重复、零额外；全量模型元数据一致。加载69.230秒、推理13,238.895秒、总计13,308.124秒，推理吞吐8.81705 reviews/s（端到端约8.771 reviews/s）；有效insight 350,656个，`rejected_insights` 7,026个，offset全量回指通过。
  - 最终状态：已正式验收；不再重跑。原始候选中的剩余语义误差作为 taxonomy 阶段可容忍噪声处理。
  - Fresh语义验收（seed `20260908`）：排除旧开发/回归/抽测涉及的406个唯一评论后，从116,322条合格总体简单随机抽取200条；严格通过117（58.5%）、轻微问题60（30.0%）、实质失败23（11.5%）。问题评论计数（可重叠）：漏抽45、scope 25、polarity 20、错误观点/主题17。contract `success`中仍有18条实质失败，不能以contract状态替代语义质量。明细见`docs/runs/t007-fresh-semantic-audit-20260908.json`。
  - 验收决定：T007正式验收，允许下游仅使用`current_product`有效 insight 构建审核后的 taxonomy。

## 当前任务：新版 T008–T010

- [x] T008 按 category 对`current_product` insight 构建并人工审核 taxonomy。
  - 正式输入：315,400条 candidate；MiniLM＋Fast Community Detection形成4,992个一级cluster、230,278个member。
  - 正式输出：`data/gold/t008-final-20260908-v1`，包含13类、887个taxonomy theme；4,992/4,992一级cluster exact-once映射，`validation.status=ready`。
  - 边界：85,122条未进入community的candidate不是丢失数据；不得强制分类、重调阈值或继续压缩887个主题。
- [x] T009 生成全量 insight 到审核后 taxonomy 的可追溯映射。
  - 输入：`data/gold/t008-candidates-20260908-v2`、`data/gold/t008-clusters-20260908-v2`、`data/gold/t008-final-20260908-v1`。
  - 输出：315,400条candidate逐条保留；已有cluster链的230,278条标记`mapped_by_cluster`，无cluster的85,122条标记`unmapped_no_cluster`。
  - 字段：保留`candidate_id/review_id/parent_asin/product_category/topic_raw/evidence/polarity/target_scope`，并附`cluster_id/taxonomy_id/canonical_theme_name/mapping_status`。
  - 验收：candidate_id唯一且exact-once；映射状态合计等于315,400；映射链不存在孤儿或category错配；不计算nearest theme、不新增embedding/阈值、不修改T008 Gold。
  - 完成结果（2026-09-08）：`data/gold/t009-insight-taxonomy-20260908-v1`写出315,400行；`mapped_by_cluster=230,278`、`unmapped_no_cluster=85,122`；candidate重复、member孤儿、身份错配、未知taxonomy和空值契约错误均为0，`validation.status=ready`。
- [ ] T010 按唯一`review_id`生成主题数量、占比和时间趋势。
  - 前置：只使用T009中`mapped_by_cluster`记录进入canonical-theme聚合；`unmapped_no_cluster`保留但不进入主题统计。
  - 输出：`products/product_facets/themes/theme_timeseries/theme_reviews` Gold表，字段与现有`backend_generated` repository和`frontend_completed`类型直接对齐；同时保留完整polarity breakdown。
  - ratio：商品主题分母为该商品全部正式唯一评论数；月度分母为该商品当月全部正式唯一评论数。
  - mixed：先按`parent_asin + taxonomy_id + review_id`去重；正负并存或含原生mixed时记为一次mixed，不重复计入positive或negative；neutral与单一方向并存时保留该方向。
  - 验收：主题计数可由不同`review_id`重算；缺月份只退出趋势；所有ratio分子不大于分母；不修改现有前后端。

## 后续集成任务
- [ ] T011 使用Spark生成新版Gold数量、占比、月度趋势和主题—评论映射。
  - 验收：分别生成评价主题和改进需求统计；每个主题的评论数等于不同评论ID数；缺时间只影响趋势；商品分析维度状态完整。
  - 验证：Gold对账程序通过，0主题维度与`no_qualified_theme`一致。
- [ ] T012 将唯一通过验证的新版Gold发布到MongoDB。
  - 验收：旧TF-IDF和旧demands结果不成为活动批次。
  - 验证：MongoDB集合计数与Gold一致。
- [ ] T013 实现FastAPI只读接口。
  - 验收：分开支持评价主题、改进需求、分析状态、趋势和原文分页查询；请求不启动离线作业。
  - 验证：后端接口测试通过。
- [ ] T014 实现Vue/ECharts完整业务流程。
  - 验收：只能选择139个正式商品，分开展示正负评价与改进需求，支持趋势和原文下钻，并正确展示无合格主题状态。
  - 验证：前端构建和端到端流程通过。

## 执行约束

- 一次只执行当前任务及其验收，不增加未列功能。
- 每个模块只做与交付直接相关的最小工程验证；不追求覆盖率，不反复运行相同检查。
- 正式全量阶段不做模型或规则竞赛、训练或人工标注评价集。
- T007 Transformer在NVIDIA/Linux vLLM执行且禁止CPU回退；历史模型的Windows XPU约束只适用于其历史任务。Spark只做数据处理和聚合。
- 用户未要求的报告、预警、额外模型和业务页面不得创建。
