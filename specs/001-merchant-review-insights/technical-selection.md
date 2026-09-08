# 技术选型：家电整机评论洞察

**Status**: T007 accepted; T008 and T009 completed
**Updated**: 2026-09-08

## T007 当前选型边界

旧 PyABSA/DeBERTa sentence-level ABSA 与 NLI attribution 仅保留为历史 baseline，不再产生正式业务结果。新版 T007 使用完整 `text_raw`、当前商品标题和类目做结构化 insight extraction；正式验收的全量候选为 `Qwen/Qwen3.5-4B` revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`。

当前执行层为 NVIDIA/Linux vLLM 0.28.0 continuous batching 与原生 structured JSON。Windows Intel Arc 原型只接受明确 XPU 执行；所有后端均禁止 silent CPU fallback。计算位置不改变输出契约。具体 prompt、量化、batch、生成上限、structured-decoding 后端和 bounded retry 属于实验参数，可按记录在案的小规模结果调整。

## T007 选型演进与当前证据

| 阶段 | 执行方式 | 结果与决定 |
|---|---|---|
| 串行 baseline | Transformers逐条`generate()`＋LMFE `prefix_allowed_tokens_fn` | 约0.033 reviews/s（约30秒/条）；4B降到2B几乎未改善且2B语义退化，判定主要瓶颈为执行架构，淘汰为全量runner |
| vLLM v1 | Qwen3.5-4B、continuous batching、原生structured JSON | 初版全量约12 reviews/s；200条人工复核：89通过、38轻微、73失败，暴露漏抽、scope和evidence完整性问题 |
| v2.1候选 | 保持4B和schema；强化多观点、scope、简洁evidence及逐项校验；1024 output tokens | 73条问题样本重跑：41通过、19轻微、13失败；25条保护样本：19不变/更好、5轻微、1明显退化，无新增严重scope错误；已知超长JSON截断得到修复 |

当前全量运行使用 v2.1；采用 resume、逐批写入和单条失败保留。`partial_success` 保存通过校验的 insights，并在 `rejected_insights` 中记录不合法项。

本次全量推理于 2026-09-08 12:10:53（Asia/Shanghai）正常结束。输入与输出均为116,728行，逐行JSON解析全部成功；输入和输出各有116,728个唯一`review_id`，无缺失、重复或额外ID。模型元数据在全量输出中一致：`Qwen/Qwen3.5-4B`、revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`、prompt `t007-context-insight-v2.1`、vLLM 0.28.0。加载69.230秒，推理13,238.895秒，总计13,308.124秒；推理吞吐8.81705 reviews/s，端到端吞吐约8.771 reviews/s。共保留350,656个有效insight和7,026个`rejected_insights`；有效insight的evidence offset全量回指`text_raw`无不一致。

最终验收发现需要在不重跑模型的情况下归一化输出schema：原始状态为`success=110,358`、`partial_success=6,193`、`failed=157`、契约外`success_no_insight=20`。20条空洞察成功记录应确定性改为`success`并保留`insights=[]`；32条`JSONDecodeError`失败记录缺少数组形态的`insights/rejected_insights`，应补为空数组，同时保留`failed`、`error_type/error_message`和`raw_output`。因此当前推理已经结束，但T007尚未通过最终输出契约验收，仍不是正式Gold。

在最终 v2.1 全量输出中以固定随机种子`20260908`抽取200条fresh样本；抽样前排除曾用于开发、回归、旧200条抽测、已知失败、定向诊断和验证的406个唯一`review_id`，合格抽样总体为116,322条，样本SHA-256为`a2266ef51c1a0f321fec041b84c98b1071e5aa87a9b7c196bfb493382e59966b`。逐条阅读原文与当前输出后，结果为严格通过117条（58.5%）、轻微问题60条（30.0%）、实质失败23条（11.5%）。问题按评论计数（标签可重叠）：漏抽45条、scope 25条、polarity 20条、错误观点/主题17条。186条contract `success`中仍有18条实质失败；14条`partial_success`中有5条实质失败，因此contract状态不能替代语义质量。

最终决定：T007正式验收，不再重跑；fresh审阅揭示的剩余语义误差作为taxonomy阶段可容忍噪声记录。T008随后按category完成高置信度community发现与人工审核，正式冻结13类、887个taxonomy theme；未进入community的insight不强制分类。

## 原则

使用成熟、公开、可在本地直接推理的现成方法；不自行训练，不组织模型竞赛。关键词不能直接决定建议标签。Spark只承担数据处理与聚合，Transformer统一在Windows XPU进程运行。

## 固定技术与当前证据

| 任务 | 固定技术 | 本地运行位置 | 当前测试或运行结果 |
|---|---|---|---|
| 原始清洗与关联 | Spark 4.1.2、Parquet | Docker：1 Master＋2 Workers | 2,128,605条评论和94,327条商品元数据已完成Silver |
| 语言识别 | fastText `lid.176` | Docker Spark | 1,815,794条有效英文评论已完成 |
| 正式商品范围 | 类目白名单＋时间/活跃度/数量规则 | Windows DuckDB读取Parquet | 139个整机商品、13类、116,728条评论；结果已与Parquet重计数一致 |
| 整体情感 | VADER 3.3.2 | Docker Spark CPU | 1,815,794条已完成：正面1,333,505、负面268,727、中性213,562；98.42秒 |
| 属性及属性情感 | `yangheng/deberta-v3-base-end2end-absa`，锁定revision `23e6d43431a5f96d8a7b7b9721d59bbda30cc63d` | Windows `ml/xpu/.venv`，Intel Arc XPU，batch 16，最大256 token | XPU通过；1,024条真实评论47.071秒，21.755条/秒；纯推理外推116,728条约89.43分钟；峰值allocated约1.29GB、reserved约1.41GB |
| 明确建议确认 | 全部句子使用`cross-encoder/nli-MiniLM2-L6-H768`；entailment同时高于neutral和contradiction才接受 | Windows XPU | 459,186句三分类分数已完成，0失败；旧规则产生166,197条且97.3%的接收项为neutral最高，待直接复用分数重算 |
| 相似主题合并 | `all-MiniLM-L6-v2`＋Sentence-Transformers Fast Community Detection；相似度0.75、最少10条不同评论；无合格社区时返回空 | Windows XPU生成向量；CPU执行聚类 | 模型与设备已验证；旧候选和聚类受建议误召回及业务类型混合影响，不得发布 |
| 主题自动命名 | 高频属性＋聚类中心观点短语＋模板规范化；失败时用中心短语 | Windows普通Python | 方法已批准；尚未实现 |
| 数量与时间趋势 | Spark按商品、主题、月份分组聚合 | Docker Spark | Spark能力已有全量任务验证；新版主题尚未聚合 |
| Gold查询与原文下钻 | Parquet→MongoDB 8→FastAPI→Vue 3/ECharts | Docker服务 | 环境已建立；新版业务数据和页面尚未完成 |

## ABSA输出约定

模型只承担属性及属性情感，不声称输出完整观点三元组。每项结果保存属性文本、极性、置信度、字符位置和完整原句。已验证示例包括：

- `ice maker / Negative`
- 同一句中的`basket / Negative`与`controls / Positive`
- `cooling performance / Positive`

模型可能将漏水句抽取为`water / Negative`，因此最终问题主题必须结合原句和后续MiniLM聚类形成，不能把属性词直接当作主题名称。

## 明确建议流程

```text
评论切句
  → 全部句子进入cross-encoder/nli-MiniLM2-L6-H768
  → 保存entailment、neutral、contradiction三项分数
  → entailment同时大于neutral和contradiction时确认明确改进建议
  → 保留建议句、三项分数和评论ID
```

`wish / need / should / could / would like / if only / hope`不得成为入口或判断依据。全部句子进入NLI，不设置MiniLM前置召回阈值，也不另设主观置信度阈值；判定规则固定为entailment是三分类最高分。不增加人工标注评价集，不比较其他模型或多套阈值规则。已有三项分数可直接在CPU重算，不重复执行XPU推理。

## 评价主题与改进需求

- 每个`parent_asin`独立聚类，不跨不同商品混合主题。
- MiniLM生成向量，Fast Community Detection按余弦相似度寻找局部语义社区；使用官方默认相似度0.75和最小社区10条不同评论。
- 评价主题只使用ABSA：正面属性形成正面评价主题，负面属性形成负面评价主题。
- 改进需求使用合格的明确建议和负面ABSA产生的隐式问题候选；两类来源可以合并，但必须保留来源类型。
- 某个分析维度没有满足0.75/10的社区时返回0个主题并记录`no_qualified_theme`；不得降低标准或强制生成fallback。
- 名称优先使用高频属性＋中心观点短语＋固定模板；没有可靠模板时直接使用中心问题或建议短语，不推断原文没有表达的解决方案。

## 性能解释

ABSA的89.43分钟是1,024条真实评论、batch 16、最大256 token下的纯推理外推，不包含正式读写、长评论分块和失败重试，不能写成正式任务承诺。昨天三小时未完成的是CPU Spark中的四标签DeBERTa zero-shot旧任务，与本次单次token-classification XPU基准不同。

## 已否决方案

- 所有至少50条评论的商品进入前端；
- 只选择Water Filters和Ice Makers；
- 裸关键词召回后对205,855条评论执行四标签DeBERTa-base zero-shot；
- 在Spark partition中创建Transformer pipeline；
- 使用旧TF-IDF词组作为新版最终主题；
- 把明确建议无条件标成负面评价；
- 为保证每个维度非空而强制生成主题；
- 自行训练或比较大量候选模型。
## T009 确定性 insight→taxonomy 映射（2026-09-08）

- 输入：`data/gold/t008-candidates-20260908-v2`、`data/gold/t008-clusters-20260908-v2`、`data/gold/t008-final-20260908-v1`。
- 方法：按`candidate_id`连接一级cluster member，再按`cluster_id`连接审核后taxonomy；不对未聚类insight执行nearest-theme补映射，不使用新embedding或相似度阈值。
- 输出：`data/gold/t009-insight-taxonomy-20260908-v1`。
- 结果：315,400条candidate exact-once；230,278条`mapped_by_cluster`，85,122条`unmapped_no_cluster`。
- 验证：candidate重复0、member重复0、孤儿member 0、身份字段错配0、未知taxonomy 0、映射空值契约错误0；JSONL 315,400行均可解析，`validation.status=ready`。
