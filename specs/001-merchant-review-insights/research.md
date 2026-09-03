# Phase 0 Research: Amazon 商品需求洞察与质量问题预警

**Date**: 2026-09-02  
**Scope**: 解析规划阶段的技术、统计、NLP、部署和数据服务未知项。所有版本在实现时进入
锁文件；本文中的“当前”均指本研究日期。

## 1. 运行时与 Spark 版本

**2026-09-03 实施修正**：以下是最初调研决策，不是安装结果。4.1.3 的官方 Docker
标签 API 实测 404；本轮固定官方 Spark 4.1.2 / Java 21 / Python3 镜像及 digest，
MongoDB 固定 8.0.29。当前可运行版本以 `infra/compose.yaml` 和环境验收报告为准。
不更改双 Worker、Spark ML、后续 NLP/Web 方案；这些依赖仍需实施时逐项验收。

**Decision**: 使用 Python 3.12.x、Java 21 LTS、Spark/PySpark 4.1.3、Scala 2.13，
MongoDB Spark Connector 使用
`org.mongodb.spark:mongo-spark-connector_2.13:11.1.0`。

**Rationale**: Spark 4.x 支持 Java 17/21/25 和 Python 3.10+。4.1.3 是已有功能线的最新
补丁，4.2.0 在研究时刚发布；三周课程项目优先降低版本新鲜度风险。Connector 11.1 支持
Spark 4.0+，并匹配 Spark 4 的 Scala 2.13 ABI。

**Alternatives considered**: Spark 4.2.0 可在完整冒烟测试后升级；Spark 3.5.x 更成熟但需
退回 Scala 2.12 与 Connector 10.x；Python 3.14 的 ML 二进制生态风险较高；Java 17 是
兼容性回退项。

**Sources**: [Spark 文档](https://spark.apache.org/docs/latest/index.html)、
[Spark 下载与版本](https://spark.apache.org/downloads)、
[MongoDB Spark Connector 兼容性](https://www.mongodb.com/docs/spark-connector/current/)

## 2. 分布式执行形态

**Decision**: Docker Compose 中运行 1 Master + 2 Workers 的 Spark Standalone 集群，
Driver 提交到 `spark://spark-master:7077`；开发单元测试使用 `local[2]`。共享只读 Bronze，
Silver/Gold 优先分区写 Parquet。

**Rationale**: 官方文档允许在一台机器上启动 Standalone 守护进程用于测试，能够实际演示
Master 调度、多 Executor/进程、Stage/Task 分发及 Worker 故障重调度。它必须被表述为
“单主机伪分布式 Spark Standalone”，因为所有 Worker 仍共享物理故障域，不能证明跨机器
网络、数据本地性或横向扩展。

**Alternatives considered**: `local[*]` 资源更省但无法演示 Master/Worker；三台真实主机最
接近生产但运维成本超出周期；Kubernetes 不解决当前业务问题；只有教师明确要求分布式
存储时才追加 HDFS，并同样如实说明单机 DataNode 的限制。

**Source**: [Spark Standalone](https://spark.apache.org/docs/latest/spark-standalone.html)

## 3. Bronze、Silver、Gold 边界

**Decision**:

- Bronze：不可变的原始 gzip、来源 URL、下载时间、字节数、行数、SHA-256 和许可说明；
- Silver：Spark 解析后的行级可信明细，保留每一条原始记录的去向、类型/时间规范化、
  元数据关联、语言/正文适用性、重复簇、评分文本不一致等标记；
- Gold：面向业务查询的组合、商品群、商品、问题、需求、趋势、预警、证据、校准、模型
  评价和批次结果。Parquet 是可复算产物，MongoDB 是 Web 查询投影。

**Rationale**: 清洗不是删除“看起来不正常”的评论，而是保留原始事实、显式标记每个任务
是否适用，再形成可审计业务结果。该边界支持重新运行、数量守恒和任一结论回溯。

**Alternatives considered**: 全部明细直接写 MongoDB 会增加导入和索引成本；只保留清洗后
数据无法解释损失；用 CSV 作为中间格式会丢失嵌套结构和类型信息。

**Source**: [Medallion architecture](https://docs.databricks.com/aws/en/lakehouse/medallion)

## 4. MongoDB 服务边界

**Decision**: MongoDB Community 8.0.x（实施时固定补丁和镜像 digest），PyMongo 4.17.x；
FastAPI 使用 `AsyncMongoClient`。MongoDB 保存 Gold 及证据索引，数据库目录使用 Docker
named volume；Bronze 与 Parquet 不强制导入 MongoDB。

**Rationale**: 8.0 是生命周期可预测的 Major Release。官方已将 Motor 置于弃用迁移路径，
新项目直接采用 PyMongo Async。API 只读预计算 Gold，避免请求期间启动 Spark 作业导致
延迟和资源不可控。

**Alternatives considered**: 原生 Windows MongoDB 会降低团队复现性；MongoDB 8.3 演进
更快但无必需特性；同步 PyMongo 是异步测试成本过高时的可接受简化；不采用 Motor。

**Sources**: [MongoDB 版本策略](https://www.mongodb.com/docs/manual/reference/versioning/)、
[PyMongo Async 迁移](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/)、
[MongoDB Docker 镜像](https://hub.docker.com/_/mongo)

## 5. Web 技术栈

**Decision**: 后端为 FastAPI 0.141.1 + Pydantic 2.x + PyMongo；前端为 Node 24 LTS、
Vue 3.5.38、TypeScript 5.x、Vite 8.x、ECharts 6.x。Python 用 `uv.lock`，npm 用 lockfile
固定精确版本。除非跨页面状态确实复杂，否则不增加 Pinia；第一版 SPA 不使用 SSR。

**Rationale**: FastAPI 提供类型校验和 OpenAPI，Vue/ECharts 适合交互式下钻和趋势图；
Node 24 满足 Vue/Vite 要求并处于 LTS。API 和 UI 独立部署，使接口契约可以先行验证。

**Alternatives considered**: Flask 需要额外补齐契约和校验；Django 对只读分析 API 偏重；
Nuxt/SSR 不产生课程核心价值；请求实时跑 Spark 不满足 3 秒交互目标。

**Sources**: [FastAPI 发布说明](https://fastapi.tiangolo.com/release-notes/)、
[FastAPI 容器指南](https://fastapi.tiangolo.com/deployment/docker/)、
[Vue Quick Start](https://vuejs.org/guide/quick-start.html)、
[Node 发布状态](https://nodejs.org/en/about/previous-releases)、
[ECharts 6](https://echarts.apache.org/handbook/en/basics/release-note/v6-feature/)

## 6. 商品与问题分级准入

**Decision**: 不直接采用“50 条评论、10 条问题证据”。预注册至少三组候选：商品可用正文
30/50/100，独立问题评论 5/10/20，总活跃月 6/9/12，单比较窗口 20/30/50，每活跃月
5/10/20。重复簇只计一个独立证据单位。结果状态为 `insufficient`、`exploratory`、
`qualified`。

**Rationale**: 候选按全量覆盖率、95% Wilson 区间宽度、分层人工评价和滚动时间回测比较；
先声明质量底线，再从满足底线者中选择覆盖率最大的配置。每次选择保存候选、指标、理由、
适用群组和版本，符合 FR-019/SC-009。

**Alternatives considered**: 经验阈值不可复现；统一阈值忽略不同商品群基准率；只看 p 值会
让大样本中的微小无业务意义差异显著。

**Source**: [NIST 比例置信区间](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)

## 7. 问题率、排序与不确定性

**Decision**: 页面同时展示原始计数、比例和 Wilson 置信区间；正式跨商品排名在商品群内
使用 Beta-Binomial 经验贝叶斯收缩，展示后验区间。问题优先级由影响范围、严重度、近期
变化、持续性组成，置信度作为资格/标签，不伪装成业务重要性。对综合分、趋势和排名稳定性
使用 bootstrap。

候选权重至少包含等权、严重度偏重、变化偏重三组，并在盲法人工成对优先级判断上用
Spearman、NDCG 和 bootstrap 稳定性选择；最终分数公开每个组成项和参数版本。有用票经
`log1p`、组内分位数和 P95/P99 截尾后最多只作 10% 的证据质量/同分决胜项，不进入问题
流行度计数。

**Rationale**: 收缩能降低小样本极端比例的排名膨胀，原始数又保证可解释性。把置信度与
重要性分离，避免“证据很多”被误解为“问题更严重”。

**Alternatives considered**: 直接按负面评论数会偏向热门商品；直接按负面比例会偏向小样本；
隐藏的单一加权公式无法解释；有用票直接加权容易被少数旧评论支配。

**Sources**: [Bayesian Data Analysis](https://sites.stat.columbia.edu/gelman/book/BDA3.pdf)、
[NIST Bootstrap](https://www.nist.gov/system/files/documents/itl/ssd/cs/bootBCa-manual.pdf)

## 8. 趋势与预警

**Decision**: 月份缺失表示“无可用观察”，不得补成零问题率。进入趋势前检查总/近期活跃
月、基线和近期样本、最大间隔及单月集中度。主预警使用“近期相对基线恶化超过最小业务
效应”的后验概率，要求持续窗口确认，并对同批多问题检验使用 Benjamini-Hochberg FDR；
CUSUM 仅作辅助对照。

采用滚动起点回测，并注入 5/10/15 个百分点的恶化，记录每千商品月误报数、注入召回、
检测延迟、人工精确率、覆盖率、持续性和 Top-K 稳定性。SC-007 的“明显恶化”与“稳定
对照”据此固化为版本化 fixture。

**Rationale**: 同时约束统计证据、业务效应和持续性，能减少小样本与一次性爆发误报；FDR
控制适合每月大量商品×问题并行检测。

**Alternatives considered**: 固定极低/极高评分不是异常；单一 z-score 忽略样本充分性；
仅 CUSUM 难向业务用户解释多重比较和效应大小。

**Sources**: [Benjamini-Hochberg](https://rss.onlinelibrary.wiley.com/doi/pdf/10.1111/j.2517-6161.1995.tb02031.x)、
[NIST CUSUM](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm)

## 9. NLP 主线与基线

**Decision**: 采用“双轨”设计：

1. 全量 Spark ML 基线：Tokenizer/NGram → HashingTF 或 CountVectorizer → IDF →
   LogisticRegression；评分 1–2 与 4–5 只作弱标签，3 星及矛盾文本不作可靠标签；Spark LDA
   作为主题基线。
2. 精细商品群主线：`distilbert-base-uncased` 做属性情感与明确需求两个独立任务，初始
   最大长度 128、3–5 epoch 作为待基准候选；`all-MiniLM-L6-v2` 只用于语义召回和聚类，
   不替代最终情感分类。

每个商品群定义约 8–15 个可解释属性。先用名词/元数据/负面句和 MiniLM 发现候选，由人
合并为属性词表；属性句对形如 `[aspect] [SEP] [sentence]`，输出正/中/负及置信度。一条
评论可以有多个属性和不同倾向。明确需求先由规则召回，再由独立 DistilBERT 二分类，随后
用 MiniLM 嵌入聚类并由人命名主题。隐含需求只由负面属性推导为实验性机会，分区展示。

**Rationale**: Spark 基线证明全量大数据计算并提供简单可解释比较；小型 Transformer 在
当前 32 GB、无独显主机上可以 CPU 微调与批量推理，同时比“评分等于情感”更贴近属性级
任务。候选句筛选控制成本，但完整数据仍经过 Spark。

**Alternatives considered**: 只做词频/LDA 不足以完成属性倾向和需求识别；大型生成模型
本地成本高且证据边界难验收；把 MiniLM 直接当情感模型任务不匹配；不强制 GPU。

**Sources**: [DistilBERT](https://arxiv.org/abs/1910.01108)、
[MiniLM](https://arxiv.org/abs/2002.10957)、
[SemEval ABSA](https://aclanthology.org/S14-2004/)、
[Suggestion Mining](https://aclanthology.org/S19-2151/)、
[Spark 特征](https://spark.apache.org/docs/latest/ml-features.html)

## 10. 人工标注与模型验收

**Decision**: 先标 100 句 pilot 修订指南，再建立联合属性/情感基础集约 2,400 句，并为
明确需求强化约 600 句。按 `parent_asin` 与近重复簇分组切分，禁止同源泄漏。独立属性
情感测试集不少于 600 句，明确需求测试集不少于 600 句，均覆盖 spec 的最低 500/300；
测试集 100% 双人标注并仲裁，训练/验证至少 20% 双标。

属性识别/情感报告 Macro-F1、分属性 F1、混淆矩阵及不同评分/长度误差；明确需求报告
precision、recall、F1、PR-AUC 和规则基线差异。模型卡记录数据、随机种子、参数、吞吐、
主要错误和适用边界。

**Rationale**: 人工独立测试集把弱监督标签与最终评价隔离；按父商品和重复簇切分防止同一
文本或变体泄漏。双标和仲裁使任务定义本身可审查。

**Alternatives considered**: 随机逐句切分容易泄漏；只用星级评价会循环论证；全量双标的
人力投入不匹配课程周期。

## 11. 模型运行与硬件

**Decision**: PyTorch CPU FP32 是可靠参考；在同一 10,000 句上比较 PyTorch CPU、
OpenVINO CPU、OpenVINO Intel GPU FP16 和 INT8。只有吞吐提高且 Macro-F1 损失不超过
预注册候选 0.01/0.02 时采用优化后端。集成 Intel Arc 只作可选推理加速，训练按 CPU 可
完成设计；模型 profile 与 Spark profile 错峰运行。

**Rationale**: Core Ultra 5 + 32 GB 足以训练 DistilBERT 级别的小模型和 MiniLM 推理，
只是耗时高于独显。先测量再选择后端，比为了“用 GPU”增加脆弱依赖更可靠。

**Alternatives considered**: 云 GPU 可加速但增加环境与费用；大型模型不满足时间和解释性；
SetFit 可作为标注或训练时间不足时的实验回退，不替代既定验收。

**Sources**: [Optimum Intel OpenVINO](https://huggingface.co/docs/optimum-intel/openvino/optimization)、
[ONNX Runtime OpenVINO](https://onnxruntime.ai/docs/execution-providers/OpenVINO-ExecutionProvider.html)

## 12. 代表性证据

**Decision**: 先按近重复簇去重，再选簇内 medoid；跨簇使用 MMR 兼顾与主题相关性和多样性，
并强制同时包含支持与反例、不同时间和不同评分（有数据时）。页面展示原文、评分、时间、
验证购买、有用票、模型标签和批次，不生成替代原文。

**Rationale**: 代表评论的作用是让结论可核验，而非再次说服用户。先去重避免模板评论占满
证据位，MMR 避免只展示相似的支持样本。

**Alternatives considered**: 最高有用票会偏向旧评论；随机样本可能不相关；生成式摘要无法
替代可追踪证据。

**Source**: [Maximal Marginal Relevance](https://aclanthology.org/X98-1025/)

## 13. 本机部署与资源预算

**Decision**: Docker Desktop 使用 WSL 2 backend 和 Compose Specification，不写旧式
顶层 `version`。profiles 分为 `app`、`spark`、`ml`、`test`。WSL 总上限 20–22 GiB、
10 逻辑 CPU、4–8 GiB swap；Windows/IDE/浏览器至少保留 8 GiB。磁盘建议保留 50–70 GiB。

初始容器预算：Master 0.5 GiB；2×Worker 5 GiB/4 core；Driver 3 GiB；MongoDB 3–4 GiB；
API 0.5–1 GiB；前端 0.5 GiB。遇到内存问题先处理倾斜、缓存和分区，不盲目扩堆。

**Rationale**: profiles 允许全量 Spark 与 NLP 训练错峰，适配当前 32 GB 主机；Compose
统一环境也方便组员复现。

**Alternatives considered**: 全部原生 Windows 安装版本容易漂移；所有服务常驻会挤占模型
内存；Kubernetes 与真实多机集群超出本项目收益。

**Sources**: [Docker Desktop WSL 2](https://docs.docker.com/desktop/features/wsl/)、
[Compose 安装](https://docs.docker.com/compose/install/)、
[Compose Specification](https://docs.docker.com/reference/compose-file/)

## 14. 测试策略

**Decision**: 数据转换用 pytest + PySpark `local[2]` 小型确定性 fixture；集成测试通过
Compose 启动真实 MongoDB。管道断言 schema、数量守恒/损失原因、标识唯一性、Bronze
不可变、Silver 规则和 Gold 公式。API 做契约与错误状态测试；Vue 用 Vitest，核心商家路径
用 Playwright Chromium，最终验收再扩展浏览器。完整数据运行是单独可复查验收，不进入
日常 CI。

**Rationale**: 单元测试保持快速，真实 MongoDB 验证索引、聚合和 BSON 行为，全量运行
证明规模与资源行为；三者不能互相替代。

**Alternatives considered**: mongomock 不能替代真实数据库；每次 CI 跑 212 万数据成本过高；
只做截图不能证明交互和异常路径。

**Sources**: [FastAPI 测试](https://fastapi.tiangolo.com/tutorial/testing/)、
[pytest 兼容政策](https://docs.pytest.org/en/stable/backwards-compatibility.html)、
[Playwright 浏览器](https://playwright.dev/docs/browsers)

## Resolved Unknowns

规划阶段没有遗留未决澄清项。商品群正式选择、准入数值、排序权重、预警最小
效应和模型优化后端不是未说明的需求，而是必须由后续版本化画像/校准/基准任务依据本文
预注册方法产出的数据决策；在报告完成前只能使用 `candidate` 状态。
