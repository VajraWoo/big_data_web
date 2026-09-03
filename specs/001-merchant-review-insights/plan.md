# Implementation Plan: Amazon 商品需求洞察与质量问题预警

**Branch**: `001-merchant-review-insights` | **Date**: 2026-09-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-merchant-review-insights/spec.md`

## Summary

构建一个面向商品运营人员的中文 Web 分析应用：完整处理 Amazon Reviews 2023
Appliances 的 2,128,605 条评论，形成可追踪的 Bronze、Silver、Gold 数据链路；从公开
品牌/店铺商品组合下钻到商品群和父商品，展示属性级质量问题、明确需求主题、趋势、预警
及可回看的正反证据。

离线层使用单主机双 Worker 的 Spark Standalone 伪分布式集群完成全量数据校验、关联、
重复标记、通用聚合和文本基线。精细 NLP 仅在选择报告确认的至少两个语义一致商品群上
运行，以 Spark ML 基线对照 DistilBERT 属性情感和明确需求分类，并用 MiniLM 聚类需求
表达。Parquet 保存可复算明细，MongoDB 保存面向查询的 Gold 文档；FastAPI 提供只读
API，Vue 3 与 ECharts 完成组合、商品群、商品和证据下钻。

## Technical Context

**Language/Version**: Python 3.12.x；Java 21 LTS；Scala ABI 2.13（Spark 依赖）；
TypeScript 5.x；Node.js 24 LTS

**Primary Dependencies**: Apache Spark/PySpark 4.1.2（镜像可获取性修正见 environment.md）、MongoDB Spark Connector 11.1.0、
FastAPI 0.141.1、Pydantic 2.x、PyMongo 4.17.x、Transformers/PyTorch、
sentence-transformers（MiniLM）、可选 OpenVINO/ONNX Runtime、Vue 3.5.38、Vite 8.x、
ECharts 6.x

**Storage**: 不可变原始 gzip/manifest（Bronze）；分区 Parquet（Silver 及可复算 Gold）；
MongoDB Community 8.0.29（在线 Gold 结果、证据索引、批次与评价元数据）

**Testing**: pytest 9.x、pytest-cov、FastAPI TestClient/httpx、PySpark `local[2]`
确定性 fixture、真实 MongoDB Compose 集成测试；Vitest 4.1.x、Vue Test Utils、
Playwright 1.62.x；数据质量断言、模型独立评测、预警回测和端到端验收

**Target Platform**: Windows 11 主机上的 Docker Desktop + WSL 2 Linux 容器；开发机
Intel Core Ultra 5 225H、32 GB RAM、Intel Arc 集成显卡；现代桌面浏览器

**Project Type**: Web 应用 + 离线大数据/NLP 管道

**Performance Goals**: 已预计算结果的筛选、趋势和详情操作 p95 小于 3 秒；全量 Spark
运行记录总耗时、Stage/Task、峰值资源和失败信息；NLP 各后端在同一 10,000 句基准上
记录吞吐、延迟和精度差，是否启用加速由基准决定

**Constraints**: Docker/WSL 总预算 20 GiB、项目容器 CPU 配额最多 10.5、swap 4 GiB；
Spark Master 0.5 GiB，两个 Worker 各最多 5 GiB，Driver 3 GiB，MongoDB 3–4 GiB；
不得对百万级数据无界 `collect()`/`toPandas()`；Spark 全量作业与模型训练不同时运行；
所有正式门槛必须经分布、区间、覆盖率、人工评价或回测校准；第一版只读且不宣称实时

2026-09-03 环境实施细化见 [environment.md](environment.md)：用户已设置 WSL memory=20GB，
WSL 可见 14 个逻辑 CPU 暂不更改；常驻容器 CPU 配额合计 9.5，另有按需 Driver 1 CPU。
本轮只完成基础设施准备，不进入完整功能开发；后续 Web/ML 版本仍需各自实施时验证和锁定。

同日Web环境增量已按 [web-environment.md](web-environment.md) 完成：FastAPI/PyMongo
依赖锁于backend/uv.lock，Vue/Vite/ECharts锁于frontend/package-lock.json。Web额外上限
1.5GiB/2CPU；整套环境含按需Driver最高18GiB/12.5CPU，不与模型训练同时满载。
同日CPU NLP环境按 [nlp-environment.md](nlp-environment.md) 完成：Python3.12.12、
torch2.14.0+cpu、Transformers5.16.1、sentence-transformers6.0.1已锁定；固定revision的
DistilBERT与MiniLM在断网容器完成文件校验、CPU前向/反向参数更新与3×384句向量检查。
证据见 ../../docs/runs/nlp-environment-2026-09-03.md。仅验证环境，不是正式模型训练；
这次CPU验收不包含Intel GPU/OpenVINO，正式业务仍待教师确认后开发。

后续用户授权补充本机Intel GPU验证，见[xpu-environment.md](xpu-environment.md)。
独立Windows XPU环境已安装，不更改上面的CPU Docker环境；旧驱动下线性层和两模型
曾报运行时引擎初始化错误。用户更新驱动至32.0.101.8991后，不修改测试或模型，两者
全部通过；同环境CPU对照通过。FP32/batch8的小基准中，DistilBERT训练步骤GPU速度
约为CPU的3.67倍，MiniLM encode约1.14倍。可以在本机使用XPU继续开发/训练验证；
正式设备与批次选择仍须真实样本基准和质量评测，不把合成小基准当成上文10,000句验收。
记录见../../docs/runs/xpu-environment-2026-09-03.md；OpenVINO仍未安装。

**Scale/Scope**: 2,128,605 条评论、94,327 条商品元数据、104,237 个 ASIN 变体、
94,319 个父商品；全量进入可信明细与通用聚合；至少两个经选择报告确认的商品群进入精细
分析。当前候选为 Ice Makers（105,100 条评论）和 Portable Washers（53,608 条评论），
但候选必须与其他群组按 FR-021 的预先声明规则比较后才能转为正式范围

连接器已完成最小运行验收：11.1.0 / Java Driver 5.1.4 固定于 v2 镜像，256条合成记录读写、BSON类型与按_id重放通过。证据见 [连接器验收记录](../../docs/runs/connector-environment-2026-09-03.md)。真实数据基础清洗按 [Silver增量规约](silver-cleaning.md) 实施，不代表Gold或正式模型完成。

## Constitution Check

*GATE: Phase 0 前检查通过；Phase 1 设计完成后复查通过。*

| 原则/门禁 | 设计证据 | 结果 |
|---|---|---|
| I. 规约先于编码 | `spec.md` 已澄清；本计划、研究、数据模型、契约和验证指南先于任务与实现 | PASS |
| II. 四层闭环 | Vue/ECharts → FastAPI → MongoDB/NLP → Spark/Parquet，边界和输入输出明确 | PASS |
| III. 数据真实可复现 | 原始文件、SHA-256、行级去向、规则/数据版本和 Bronze/Silver/Gold 均有设计 | PASS |
| IV. 挖掘有效可解释 | Spark 基线、深度模型、人工独立评测、阈值校准、代表性证据和已知边界齐备 | PASS |
| V. 验证追踪与 AI 问责 | 各层测试、批次追踪、日志、Git 与 `docs/prompts/` 提示词留档进入结构 | PASS |
| 文档数据与专用存储 | 212.86 万条文档记录，使用 MongoDB；显著超过 10,000 条门槛 | PASS |
| 大数据引擎 | Spark Standalone 双 Worker 真实执行全量步骤，并如实标注单物理机局限 | PASS |
| 选题门禁 | 在完整开发前仍需取得教师对选题、初版分工和数据来源的确认 | PASS（外部待办） |

Phase 1 复查：API 仅查询 Gold，不绕过 Spark；数据模型保存来源和血缘；契约为不足、失败、
实验性结果定义显式状态；Quickstart 含小样本、全量、模型和四层验收。未发现需要 Constitution
例外的设计。

## Project Structure

### Documentation (this feature)

```text
specs/001-merchant-review-insights/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── openapi.yaml
└── tasks.md                 # 后续 $speckit-tasks 生成，本阶段不创建
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── api/routes/
│   ├── config/
│   ├── domain/
│   ├── repositories/
│   ├── schemas/
│   └── services/
└── tests/{contract,integration,unit}/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   ├── router/
│   ├── services/
│   └── types/
└── tests/{component,e2e}/

pipelines/
├── src/
│   ├── jobs/{bronze,silver,gold}/
│   ├── quality/
│   └── statistics/
└── tests/{integration,unit}/

ml/
├── src/{annotation,evaluation,features,inference,training}/
├── configs/
└── tests/

infra/
├── compose.yaml
├── mongodb/
└── spark/

scripts/
tests/e2e/
data/{bronze,silver,gold}/     # 大文件由 .gitignore 管理，清单和小 fixture 可版本化
docs/{prompts,research,runs}/
```

**Structure Decision**: 采用按可独立验证职责拆分的 Web + 数据 + ML 多目录结构。
`pipelines` 是 Spark 批处理的唯一入口，`ml` 保存可独立评价的模型生命周期，`backend`
只通过 repository 读取 MongoDB Gold，`frontend` 只消费版本化 API。`infra` 固化单主机
伪分布式演示环境，避免各成员本机安装产生不可复现差异。

## Complexity Tracking

没有 Constitution 违规，因而无需例外说明。双 Worker、MongoDB 与独立 ML 目录分别对应
课程的大数据执行、文档服务和模型评价边界，不属于无业务依据的额外复杂度。
