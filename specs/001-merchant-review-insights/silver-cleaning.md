# 第一周 Silver 基础清洗增量规约

日期：2026-09-03。授权范围：本轮用户完整提示；15:35 开始，17:05 截止（Asia/Shanghai）。
这是现有需求的实施增量，不重启选题或完整业务设计。

**文档性质**：已完成的 Silver 基础清洗阶段记录。文中的“本轮”“后续”和“未完成”均指
2026-09-03 当次增量的边界；当前项目已完成正式商品范围以及 T007–T011，最新状态以
`spec.md`、`plan.md` 和 `tasks.md` 为准。

## 目标和追踪

FR-001：只读 Bronze、manifest 字节数/SHA-256/全量行数与 gzip EOF 校验。
FR-002：字段类型/缺失/非法、评分、月份、正文长度、重复、关联、商品评论量画像；该阶段语言仅为
unknown，候选群选择和人工语言复核尚未纳入当次验收。FR-003/004：保留行级原文、类型校验、UTC、重复与任务准入、
父商品安全关联。FR-016/SC-001：每行恰有一个去向，批次/输入摘要/规则/执行证据可追踪。
该轮只验收基础 Silver；后续正式范围选择和语义处理已经在 T006–T011 中完成。

## 输入、身份和抽样

输入固定 manifest 中两份 gzip；发布 ID 为 amazon-reviews-2023-appliances-v1。
先验摘要和大小，流式解压读到 EOF（触发 gzip CRC 校验），按物理行从 1 编号。
在分布式步骤前仅登记 `source_file/source_line_number/raw_json`，分片为可切分 JSONL；
不在此阶段以 pandas 或主机内存完成清洗。无效 UTF-8 保留 base64 字节并隔离。
Spark 在两个现有 Worker 上解析、校验、重复聚合、关联和输出 Parquet。
review_id/metadata_id = SHA256(发布 ID + 换行 + 文件名 + 换行 + 十进制来源行号)。
身份不依赖分区、任务重试或批次；相同内容的不同行有不同 ID。

小样本用 Python 3.12 random.Random(20260903).sample(range(1,N+1),10000)，无放回，
选中行按来源顺序登记，记录实际行号列表、其摘要和种子。全量仍验证 EOF/行数。
样本元数据使用全量 94,327 行，避免因抽样人为造成关联失败；样本重复统计仅代表样本内部。
同一入口 `pipelines/run_silver.ps1 -Mode sample|full`，新批次绝不覆盖旧目录。

## 字段和规则 silver-basic-v1

保留每个可解析 JSON 对象及 raw_json；语法错误、非对象、重复 JSON 键、非有限 JSON 数字、
UTF-8 错误独立隔离，并保留原因。字段非法不整行隔离，不用 null 掩盖原始值。
字段状态为 missing/null/valid/invalid_type/invalid_value；保存 field_types 和 field_issues。
rating 必须为有限数值（非 bool）且 1<=rating<=5；不强制整数、不把 1/5 视为异常。
timestamp 必须为非 bool 整数毫秒，位于 Unix epoch 至数据截止月末 2023-09-30T23:59:59.999Z；
越界或错类型保留原值并标记；UTC timestamp、review_month 从有效值派生。
helpful_vote 必须为非负 64 位整数（非 bool），verified_purchase 必须为 JSON bool。
asin/parent_asin/user_id/title/text 要求字符串，标识空白视为缺失有效值；不猜测或改写 ASIN。
user_id 只另存稳定 SHA-256；raw_json 留在本地 Silver 审计层，不用于 Web 批量公开。
元数据保存 parent_asin/title/store/main_category/categories、details/features 等原始 JSON；
price 仅接受非负有限数值，否则标记，缺失绝不补零。原始其他字段仍可从 raw_json 复查。

文本原文不变，normalized 仅 Unicode NFC 与首尾空白；保留否定、内部空白、HTML、URL、
标点和表情。text_status=empty/invalid_type/pending_assessment；非空绝不等于英文可用。
eligible_rating_stats 只由有效评分决定，rating_exclusion_reasons 独立保存；
eligible_text 表示可进行基础正文处理（字符串且非空），不是主题/NLP准入；
eligible_nlp 对空/错类型为 false，对非空为 null，nlp_exclusion_reasons 包含 language_not_assessed、
text_suitability_not_calibrated。language=unknown，近似重复/评分文本矛盾/爆发均 null+not_assessed。

exact_hash 为整个 JSON 对象的排序键规范 JSON SHA-256（包含全部源字段，不包含血缘）；
同 hash 多行标 exact_duplicate，保存 group_size，不删除。重复正文基于 NFC+strip 非空正文
全局 hash；保存 body_group_size、distinct users/parents/asins 和跨用户/父商品/变体标记。
这些只是重复关系，不宣称虚假，也不在本轮强行决定独立业务证据单位。

元数据按来源身份全部保留；父键计数形成每键一行映射。唯一键才关联具体 metadata_id，
多行父键为 ambiguous、不随意挑一行；缺失父键为 missing_parent、无匹配为 unmatched。
评论左关联后行数必须不变。额外保存 asin-parent_asin 关系表，不假定变体只有一个父商品。

## 输出和实现设计

Python 标准库 unittest 延续 infra 的轻量测试习惯；运行时使用既有 Spark4.1.2/Python3.12.12/
Java21 镜像，不加第三方依赖。代码位于 pipelines/，单元测试在 pipelines/tests/。
函数采用 snake_case；例如 `rating_valid = type(value) in (int, float) and 1 <= value <= 5`。
Compose 增量为 Driver/两个 Worker/Master 提供一致的只读代码、只读 Bronze、可写 Silver 路径，
不变更现有资源预算。16 个 shuffle 分区，禁用无界 collect/toPandas，仅收集有界质量聚合。
每批输出 data/silver/<run_id>/{reviews,products,product_keys,variants,quarantine_reviews,
quarantine_products,profiles,_staging,quality.json,run.json}，另存 Spark event log、执行日志和 schema。
运行依次 registered -> staging -> processing -> validating -> passed_basic_silver 或 failed。
passed_basic_silver 不是 data-model.md 中包含 Gold/模型验收的 published。

## 验收和复现

1. 先编写合成异常单元测试，记录 RED，再实现 GREEN；Spark fixture 覆盖重复和关联增殖风险。
2. 真实 10,000 样本先通过；同输入再次运行比较来源 ID 和确定性内容（排除 processing_run_id）。
3. 全量 2,128,605 评论、94,327 元数据，输入=Silver保留+独立隔离，ID唯一且两去向不重叠。
4. Parquet 回读验证 schema、行数、身份、原文/时间/标记、有限样本；关联不放大。
5. quality.json 中每项指标有 numerator/denominator，画像以分组计数和候选分布落盘；
   文本长度 P50/P90/P95/P99，商品量 20/50/100（现有规约候选）仅描述覆盖，正式门槛仍 null。
6. 保存实际应用 ID、实际执行主机/行数、Spark event log、代码/输入 hash、参数、耗时和错误。
7. 复现命令：`powershell -ExecutionPolicy Bypass -File pipelines/run_silver.ps1 -Mode full`；
   单元测试：`python -m unittest discover -s pipelines/tests -v`。

Always：先测试、保留源、保存日志、失败不宣称完成。新增大依赖/管理员操作及时告知。
Never：修改 Bronze、覆盖成功批次、commit/push、业务门槛拍脑袋、以本机双 Worker 冒充多物理机。
用户已明确授权实施及必要配置，不额外请求流程性确认。
