# big_data_web - Amazon 商品需求洞察与质量问题预警

面向商品运营人员的大数据 Web 课程项目，使用 Amazon Reviews 2023 Appliances 历史评论，
研究商品质量问题、明确需求与变化趋势。当前处于第一周准备阶段，尚无可运行的业务系统。

## 当前进展（2026-09-03）

| 内容 | 当前状态 |
|---|---|
| 选题与业务需求 | 已形成初稿，等待教师确认 |
| SDD 需求、初步设计和 API 契约 | 已形成文档；设计不等于实现，将随验证修订 |
| 原始数据获取 | 已下载完整 Appliances 评论及商品元数据，保存来源和 SHA-256 |
| 初始画像 | 已完成探索性全量扫描，不是正式 Silver 清洗产物 |
| WSL 环境 | Ubuntu 已以 WSL 2 运行，Ubuntu 软件源 HTTPS 可访问 |
| Docker / Spark / MongoDB | 基础设施已实测通过：双 Worker 计算、Parquet 回读、MongoDB 持久化 |
| Spark—MongoDB 连接器 | 11.1.0已固定入镜像，256条合成数据读写、BSON类型和按_id重放验收通过 |
| Web 基础环境 | FastAPI/PyMongo与Vue/Vite/ECharts已锁依赖，真实浏览器连通、异常恢复及构建验证通过 |
| NLP 基础环境 | CPU依赖和模型已锁定；断网推理、反向参数更新、384维句向量验证通过 |
| Intel GPU 补充验证 | 驱动8991下张量、线性层、DistilBERT训练步骤及MiniLM通过；CPU/GPU小基准已完成 |
| 小样本基础清洗 | 固定种子随机10,000条验证通过；两次逐ID与内容对账一致 |
| 全量基础 Silver | 已处理2,128,605评论及94,327元数据，Parquet回读、数量守恒、ID唯一与安全关联通过 |
| 高级质量检查 | 语言/文本NLP准入、近似重复、评分文本矛盾和爆发检测尚未评估 |
| 初版分工表与教师确认材料 | 尚待整理和确认 |
| Vibe Coding 提示词留档 | 本轮清洗完整请求及后续消息已保存；此前完整历史仍待整理，不以摘要冒充原文 |

首版提交保留已有工作的真实快照，不补造历史；后续环境验收也不代表第一周全部完成。

当前计划内的本机基础环境已全部完成最小运行验收，可转入数据清洗；这不等于生产部署、
业务功能或第一周全部完成。连接器证据见[验收记录](docs/runs/connector-environment-2026-09-03.md)。

## 已可运行的环境

Docker Desktop 保持运行，在仓库根目录执行：

```powershell
docker compose -f infra/compose.yaml build spark-master
docker compose -f infra/compose.yaml up -d --wait --wait-timeout 180
docker compose -f infra/compose.yaml --profile tools run --rm spark-driver
```

Spark 管理页面：http://localhost:8080 （不是商家 Web 应用）。
详细步骤、停止方式和限制见 [环境使用说明](infra/README.md)，
实际证据见 [环境验收记录](docs/runs/environment-2026-09-03.md)。
验收计算10万条合成记录，不是已经完成真实评论清洗；原始数据保持只读。

Web环境启动（只启动Web及所需数据库）：

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web up -d --build --wait --wait-timeout 120 backend frontend
```

访问 http://localhost:5173 ，应显示“Web 环境检查”和真实连接状态，而不是业务分析。
验收详情见 [Web环境记录](docs/runs/web-environment-2026-09-03.md)。

NLP环境已构建并缓存模型，重复检查无需联网：

```powershell
docker compose -f infra/compose.nlp.yaml --profile ml run --rm nlp-check
```

首次在其他电脑配置时，先按 [NLP使用说明](ml/README.md) 构建镜像并下载模型。
实际证据见 [NLP环境记录](docs/runs/nlp-environment-2026-09-03.md)。
这是CPU运行与训练链路检查，不是已训练好的业务模型；不要与Spark全量作业同时运行。

## 文档入口

- [本次全量Silver清洗报告与复现命令](docs/runs/silver-cleaning-2026-09-03.md)
- [Silver增量规约](specs/001-merchant-review-insights/silver-cleaning.md)
- [需求规约](specs/001-merchant-review-insights/spec.md)
- [初步设计](specs/001-merchant-review-insights/plan.md)
- [第一周环境实施规约](specs/001-merchant-review-insights/environment.md)
- [技术与算法调研](specs/001-merchant-review-insights/research.md)
- [数据模型](specs/001-merchant-review-insights/data-model.md)
- [API 契约](specs/001-merchant-review-insights/contracts/openapi.yaml)
- [未来实现的验证指南](specs/001-merchant-review-insights/quickstart.md)
- [初始数据画像](docs/research/initial-data-profile.md)
- [数据来源与完整性清单](data/bronze/amazon_reviews_2023/appliances/manifest.json)
- [项目开发原则](.specify/memory/constitution.md)

`quickstart.md` 中的业务命令是后续实现目标，目前不可视为可运行入口。
规约中的 `001-merchant-review-insights` 是功能编号；本仓库工作快照位于 `main` 分支，
保留远程仓库的初始提交，尚未创建同名 Git 功能分支。

## 数据与技术范围

原始评论共 2,128,605 条，商品元数据共 94,327 条；原始 gzip 不进入 Git。
文件下载地址、大小和摘要见 manifest，获取后需校验摘要再使用。

拟采用 Spark、MongoDB、FastAPI、Vue/ECharts，精细文本分析保留轻量深度模型。
Docker + WSL 2 用于统一服务环境；单机多 Worker 必须如实称为伪分布式，不冒充多物理机集群。
精细商品群、准入参数和排序权重尚需数据验证，不能把候选值当成正式结论。

## 当前完成范围与后续工作

第一周已经完成基础环境配置、10,000条随机样本验证，以及同一管道的全量基础清洗，
产出可追溯的Silver Parquet、质量报告和运行证据。选题范围、数据来源、系统架构与
初版分工将在第一周汇报中请教师确认。

第二周将根据确认结果开展语言与文本适用性评估、候选商品群选择、问题与需求挖掘、
Gold结果设计、MongoDB查询、FastAPI业务接口和初版可视化页面。高级质量规则和正式
分析门槛须根据数据分布与人工评价校准，当前基础清洗结果不代表这些分析已经完成。

已实际执行的全量复现命令（每次新建批次，保留原始数据和旧结果）：

```powershell
powershell -ExecutionPolicy Bypass -File pipelines/run_silver.ps1 -Mode full
```

本次输出：`data/silver/silver-full-20260903T154909-6c310067/`。
2,065条空正文保留评分资格；22,656次精确重复额外出现与285,655次重复正文额外出现只标记，
不静默删除。非空正文的NLP资格保持待评估，不能直接称为英文可用数据。

## 提交边界

版本化项目文档、规约、工具模板、数据清单及后续代码；排除原始大数据、模型权重、
虚拟环境、密码/密钥、临时文件和私人对话。教师提供的 PDF 暂存本机，不默认获得再分发授权。
提交必须对应实际工作进展，并如实标注未完成部分。
