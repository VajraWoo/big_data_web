# big_data_web - Amazon 家电评论需求洞察与质量问题预警

使用 Amazon Reviews 2023 Appliances 历史评论，分析家电商品的质量问题、用户需求和时间变化，为商品改进提供评论证据。

## 当前进展（2026-09-03）

| 内容 | 状态 |
|---|---|
| 选题与业务需求 | 已形成初稿，等待教师确认 |
| SDD 文档 | 已完成需求规约、技术设计、任务拆分和 API 契约 |
| 原始数据 | 已下载 Appliances 评论及商品元数据，并保存来源、文件大小和 SHA-256 |
| 开发环境 | Spark、MongoDB、FastAPI、Vue/ECharts 和 NLP 环境已配置 |
| Spark—MongoDB 连接器 | 已完成 256 条合成数据读写、BSON 类型和按 `_id` 重放测试 |
| 小样本清洗 | 已完成固定种子随机 10,000 条评论的清洗和结果对账 |
| 全量清洗 | 已处理 2,128,605 条评论及 94,327 条商品元数据 |
| 下一阶段 | 选择演示商品，开展问题、需求和时间趋势分析 |

## 运行环境

启动 Spark 和 MongoDB：

```powershell
docker compose -f infra/compose.yaml build spark-master
docker compose -f infra/compose.yaml up -d --wait --wait-timeout 180
docker compose -f infra/compose.yaml --profile tools run --rm spark-driver
```

Spark 管理页面：http://localhost:8080

启动 Web 环境：

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web up -d --build --wait --wait-timeout 120 backend frontend
```

访问：http://localhost:5173

运行 NLP 环境检查：

```powershell
docker compose -f infra/compose.nlp.yaml --profile ml run --rm nlp-check
```

环境的构建、停止和故障处理方法见 [infra/README.md](infra/README.md) 和 [ml/README.md](ml/README.md)。

## 数据清洗

数据集包含 2,128,605 条评论和 94,327 条商品元数据。原始文件的下载地址、大小和 SHA-256 记录在 [manifest.json](data/bronze/amazon_reviews_2023/appliances/manifest.json)。

执行全量清洗：

```powershell
powershell -ExecutionPolicy Bypass -File pipelines/run_silver.ps1 -Mode full
```

本次输出目录：`data/silver/silver-full-20260903T154909-6c310067/`

清洗过程统一字段类型和 UTC 时间，使用 `parent_asin` 关联评论与商品元数据，并为缺失正文和重复记录添加标记。全量结果中有 2,065 条空正文、22,656 条精确重复的额外记录，以及 285,655 条正文重复的额外记录；所有记录均保留在 Silver 数据中。

## 技术架构

| 层级 | 技术 | 用途 |
|---|---|---|
| 数据处理 | Spark、Parquet | 全量清洗和批量计算 |
| 数据存储 | Bronze、Silver、Gold、MongoDB | 保存原始数据、清洗明细和分析结果 |
| 后端 | FastAPI | 提供商品、分析结果和评论查询接口 |
| 前端 | Vue、ECharts | 展示问题、需求、趋势和评论证据 |
| 文本分析 | PyTorch、Transformers、sentence-transformers | 评论分类、语义表示和需求识别 |

当前 Spark 环境在一台计算机上运行一个 Master 和两个 Worker。

## 后续工作

第二周计划选择真实商品案例，完成语言与文本适用性评估、问题和需求挖掘、时间趋势计算、Gold 数据设计、业务接口和第一版可视化页面。

## 文档

- [全量 Silver 清洗报告](docs/runs/silver-cleaning-2026-09-03.md)
- [Silver 清洗规约](specs/001-merchant-review-insights/silver-cleaning.md)
- [需求规约](specs/001-merchant-review-insights/spec.md)
- [技术设计](specs/001-merchant-review-insights/plan.md)
- [环境实施规约](specs/001-merchant-review-insights/environment.md)
- [技术与算法调研](specs/001-merchant-review-insights/research.md)
- [数据模型](specs/001-merchant-review-insights/data-model.md)
- [API 契约](specs/001-merchant-review-insights/contracts/openapi.yaml)
- [初始数据画像](docs/research/initial-data-profile.md)
- [环境验收记录](docs/runs/environment-2026-09-03.md)
- [Web 环境记录](docs/runs/web-environment-2026-09-03.md)
- [NLP 环境记录](docs/runs/nlp-environment-2026-09-03.md)
