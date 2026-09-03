请接手项目 D:\CS_Projects\big_data_web，完成第一周的“环境收尾＋可复现数据清洗”。

不要重新开始选题，不要重复搭建已经通过验收的环境。先阅读文件，再执行；不要只给计划。

一、时间与范围

从开始执行本请求起，环境收尾、阅读必要文件、编写规约和测试、实现清洗、运行验证，总计最多90分钟。

记录开始时间和截止时间。时间分配只是预算，不保证全量处理必然完成：
- 0—10分钟：必要阅读、环境收尾、清洗范围与验收规则确认。
- 10—40分钟：测试先行、实现管道、小样本规则验证。
- 40—75分钟：同一管道运行全量数据，生成Silver和质量统计。
- 75—90分钟：回读验收、整理结果和复现命令。

根据实际进度调整，但不得擅自超过90分钟。发现可能影响期限的问题立即告诉我，不要到最后才报告。临近截止时间时不再启动明显无法完成的长任务；保留日志和中间结果，如实交接。

本轮不做完整Web业务页面、Gold业务挖掘、深度模型训练，也不整理完整的教师汇报材料和分工表。这些是后续第一周/项目任务，不代表取消。

二、已知状态——先接受这些交接事实，不要全套重测

1. 原始数据已下载：
   Amazon Reviews 2023，Appliances：
   - 评论：2,128,605条。
   - 商品元数据：94,327条。
   初始画像是探索性全量扫描，不是正式清洗结果。
   小样本清洗和正式Silver管道尚未实现。

2. 本机基础环境已经通过最小运行验收：
   - Docker Desktop＋WSL2。
   - Spark 4.1.2、Python 3.12.12、Java 21，单物理机双Worker。
   - MongoDB 8.0.29。
   - MongoDB Spark Connector 11.1.0、Java Driver 5.1.4。
   - FastAPI/PyMongo、Vue/Vite/ECharts。
   - CPU NLP环境、Intel GPU XPU环境。

3. Spark当前镜像：
   big-data-web-spark:4.1.2-python3.12.12-v2

4. Connector已真实验证：
   256条合成记录写入、读回一致；Unicode、null、数组、嵌套对象、
   UTC时间和BSON类型检查通过；按_id重复写入后仍是256条。
   两个Worker均参与检查且能连接MongoDB。
   新镜像下原Spark十万条计算和Parquet回读通过。
   基础设施测试11项、后端测试3项通过；前后端健康接口连接MongoDB正常。

5. Docker由用户启动。先做轻量存活检查即可。
   若当前PowerShell找不到docker，可在本次进程PATH中加入：
   C:\Users\31407\AppData\Local\Programs\DockerDesktop\resources\bin
   不要修改全局PATH或重新安装Docker。

6. 本机物理内存32GB，WSL上限20GB；Intel Core Ultra 5 225H，
   Intel Arc 130T集成显卡。不要沿用历史聊天中的16GB误判。
   保留现有资源配置，不同时满载运行Spark和模型训练。

三、任务1：必要阅读和环境文档收尾

以下文件路径均相对于项目根目录。

先阅读：
- README.md
- .specify/memory/constitution.md
- specs/001-merchant-review-insights/spec.md
- specs/001-merchant-review-insights/plan.md
- specs/001-merchant-review-insights/data-model.md
- docs/research/initial-data-profile.md
- data/bronze/amazon_reviews_2023/appliances/manifest.json
- infra/README.md
- infra/compose.yaml

按实际需要阅读：
- specs/001-merchant-review-insights/research.md：清洗、抽样、语言识别和阈值依据。
- specs/001-merchant-review-insights/quickstart.md：
  注意其中业务命令是未来设计，不是已实现入口。
- specs/001-merchant-review-insights/connector-environment.md
- infra/compose.connector.yaml
- infra/tests/mongo_connector_smoke.py
- infra/tests/spark_smoke.py
- infra/tests/test_compose.py
- infra/tests/test_connector_config.py

环境历史证据已有：
- docs/runs/environment-2026-09-03.md
- docs/runs/web-environment-2026-09-03.md
- docs/runs/nlp-environment-2026-09-03.md
- docs/runs/xpu-environment-2026-09-03.md

不要为了清洗重读所有GPU安装历史或重跑模型基准。

需要修正的文档收尾：
A. docs/runs/connector-environment-2026-09-03.md 尚未创建，
   但README和规约已引用它。补齐真实证据，不能把文件不存在当成测试没做。
   上次机器可读结果位于Spark共享输出卷：
   /opt/spark/work-dir/connector/595cace4674f4caeb18b003f02c86d74.json
   Spark应用ID：app-20260903051538-0000
   MongoDB诊断集合：
   environment_checks.connector_595cace4674f4caeb18b003f02c86d74
   优先读取已存报告，不要为了补文档重新搭环境。
   若证据暂时无法读取，明确标记“交接记录记载，当前未复核”，不得伪造日志。

B. plan.md 的Scale/Scope段落中误插入了：
   <!-- Connector implementation status is recorded below, not a change to business scale. -->
   删除这个无意义注释，在适当位置补充连接器完成状态。

四、任务2：先形成清洗增量规约和可执行任务

遵守项目SDD和测试先行要求，使用适用的项目skills；
读取被使用skill的完整SKILL.md，但不要把整套业务重新规划一遍。

建议新增以下文件，名称可根据项目结构调整，必须清楚说明：
- specs/001-merchant-review-insights/silver-cleaning.md
- specs/001-merchant-review-insights/silver-cleaning-tasks.md

在实现前明确：
- 对应现有需求FR-001～FR-004、FR-016及相关质量约束。
- 输入、输出、字段、规则版本、抽样方法、行级身份。
- 解析失败和无效字段如何保留/隔离。
- 任务准入如何区分，哪些能力本轮实现、哪些尚未评估。
- 单元测试、小样本检查和全量验收标准。

不要为了90分钟而悄悄降低已有需求。
近似重复、评分文本不一致等若属于后续算法工作，应显式标为未评估，
不能填false冒充已检查。语言识别或文本准入若暂无法可靠完成，
应保留unknown/待评估状态并报告缺口，不能把非空文本全部宣称英文可用。

五、任务3：测试先行，实现并验证小样本清洗

先检查仓库是否已有可复用代码；不要假定scripts/或tools/已经存在。

小样本：
- 约10,000条真实评论，记录固定种子、抽样规则和来源行号。
- 不把文件头10,000条冒充有代表性的随机样本。
- 额外用小型合成fixture覆盖真实样本不一定出现的异常。
- 小样本只是验证步骤，不是全量清洗交付。

至少覆盖：
1. 原始gzip与manifest摘要校验；Bronze只读。
2. JSON解析、字段类型、缺失值、无效评分及时间处理。
3. 稳定review_id和来源追踪；不要使用不稳定的分区编号充当原始行号。
4. 评分1和5本身合法，不能因极端评分删除。
5. 空正文保留，合法评分仍可参与评分统计。
6. 文本原文保留；规范化不覆盖原文，不盲目删除否定词、标点或表情。
7. 精确重复与重复正文分别定义并标记，不静默整条删除。
8. 保留asin和parent_asin；商品元数据关联失败不丢评论。
   检查关联键是否唯一，避免join把行数放大。
9. UTC时间、合法有用票数、验证购买字段。
10. 评分统计、正文处理和NLP适用性分别记录原因，不混成统一删除条件。

阈值要求：
评分范围、类型约束等可依据数据schema明确设定；
“正文至少多少字”“商品至少50条”等分析门槛不能凭经验直接定为正式参数。
保存分布、候选和依据；尚未校准则保持待定。
本轮不得为了实施基础清洗而提前定死业务排名或预警门槛。

执行测试并记录失败→实现→通过的证据。
向我简短说明小样本暴露了什么，以及规则是否据此调整。

六、任务4：同一管道运行全量Silver

使用现有Spark双Worker集群真实处理：
- 2,128,605条评论。
- 94,327条商品元数据。

不能退回单机pandas全量处理，再称作Spark管道。
不要对百万级数据无界collect()/toPandas()。

实施注意：
- gzip输入不天然可切分；为后续分布式步骤设计合适的分区，
  同时保证来源行号稳定。必要的流式解压/行号登记必须可复现。
- 现有Compose主要挂载Bronze、检查脚本和检查输出卷；
  新增清洗代码及Silver挂载时，要确保Driver和两个Worker路径一致。
- 原始数据保持只读。
- 按processing_run_id输出新批次，不覆盖已有成功结果。
- 保存依赖/规则版本、参数、输入摘要、命令、Spark应用ID、
  执行时长、数量和错误信息。

输出至少包括：
- Silver评论Parquet。
- Silver商品/关联结果。
- 无效记录或隔离记录及原因。
- 机器可读质量统计。
- 可供人阅读的本次清洗报告。
- 一条清楚、已实际执行验证的复现命令。

Silver先落Parquet；本轮不必为了“用了MongoDB”把全部原始评论再灌入数据库。
MongoDB面向后续Gold服务层，连接器已经验收。

七、任务5：回读与交付验收

必须核对：
- 输入评论数＝保留的评论数＋独立隔离的评论数，不重不漏。
- 元数据也有完整行数去向。
- 稳定ID唯一、关联未导致评论增殖。
- 缺失、非法字段、重复、空正文、关联状态等都有数量和分母。
- 读回Parquet，检查schema、数量和有界样本。
- 同输入/规则再次处理的稳定ID和内容可比较；
  区分批次时间等本来就会变化的字段。
- 记录实际参与的Spark执行情况，不把单主机称为多物理机集群。

用Silver结果补充基础画像：
评分、月份、正文长度、重复类型、元数据关联、商品评论量；
候选商品群分布在不挤占核心清洗验收时补充，不能直接当成正式群组选定结果。

建议报告：
docs/runs/silver-cleaning-<实际日期>.md

更新README真实状态，明确区分：
- 已通过的小样本验证。
- 已完成的全量基础清洗。
- 尚未实现/尚未评估的高级质量检查。
- 尚待完成的第一周材料。

不要仅凭程序exit 0宣称清洗完成。

八、协作与保护要求

- 遇到需要我配置环境、管理员权限、下载较大依赖或重启的问题，
  立即说明具体原因、操作和对90分钟预算的影响。
- 不再扩展安装无关技术栈。
- 保留仓库已有未提交更改；不要reset、清空卷或覆盖Bronze。
- 未经我本轮明确授权，不commit、不push、不创建远程任务。
- 将本次用户提示词留档到docs/prompts/，不要把摘要冒充历史完整原文。
- 状态更新简短，重点说实际结果、阻碍和剩余时间。

最终给我：
1. 哪些已完成，哪些未完成。
2. 全量实际处理数量及主要质量问题。
3. 输出文件/目录和复现命令。
4. 总耗时，以及第一周还剩什么。

现在开始执行，不必再次让我确认这份已经明确的任务。