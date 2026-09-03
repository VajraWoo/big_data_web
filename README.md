# big_data_web - Amazon 商品需求洞察与质量问题预警

面向商品运营人员的大数据 Web 课程项目，使用 Amazon Reviews 2023 Appliances 历史评论，
研究商品质量问题、明确需求与变化趋势。当前处于第一周准备阶段，尚无可运行的业务系统。

## 首版快照（2026-09-03）

| 内容 | 当前状态 |
|---|---|
| 选题与业务需求 | 已形成初稿，等待教师确认 |
| SDD 需求、初步设计和 API 契约 | 已形成文档；设计不等于实现，将随验证修订 |
| 原始数据获取 | 已下载完整 Appliances 评论及商品元数据，保存来源和 SHA-256 |
| 初始画像 | 已完成探索性全量扫描，不是正式 Silver 清洗产物 |
| WSL 环境 | Ubuntu 已以 WSL 2 运行，Ubuntu 软件源 HTTPS 可访问 |
| Docker / Spark / MongoDB | 项目运行环境尚未搭建完成 |
| 小样本清洗与 Silver 管道 | 尚未实现 |
| 初版分工表与教师确认材料 | 尚待整理和确认 |
| Vibe Coding 提示词留档 | 尚待整理；不得以事后摘要冒充完整原文记录 |

此提交是已有工作的真实首次快照，不补造历史提交，也不代表第一周全部完成。

## 文档入口

- [需求规约](specs/001-merchant-review-insights/spec.md)
- [初步设计](specs/001-merchant-review-insights/plan.md)
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

## 第一周剩余范围

完成环境配置，使用约 10,000 条真实评论验证基本清洗规则，输出 Silver 样例及数量报告；
再按验证结果推进全量清洗和补充画像，整理初版分工与选题确认材料。
本阶段不提前开展完整 Web、深度模型训练和 Gold 业务挖掘。

## 提交边界

版本化项目文档、规约、工具模板、数据清单及后续代码；排除原始大数据、模型权重、
虚拟环境、密码/密钥、临时文件和私人对话。教师提供的 PDF 暂存本机，不默认获得再分发授权。
提交必须对应实际工作进展，并如实标注未完成部分。
