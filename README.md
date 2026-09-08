# Amazon 家电评论洞察分析系统

## 项目简介

本项目使用 Amazon Reviews 2023 Appliances 数据集，对家电商品评论进行细粒度观点抽取、主题归纳和趋势统计，并通过 FastAPI 与 Vue 页面提供查询和可视化。

正式处理链如下：

```text
Amazon 评论
→ 细粒度 insight 提取
→ 类别级 taxonomy
→ insight-taxonomy mapping
→ 商品级聚合
→ FastAPI API
→ Vue Web 可视化
```

## 当前正式数据规模

- 139 个商品
- 116,728 条正式评论
- 13 个商品类别

## Pipeline

### T007：评论洞察提取

T007 从完整评论中抽取 `topic_raw`、观点、证据、极性和目标范围，共得到 350,656 条有效 insight。下游只使用 `target_scope = current_product` 的结果。T007 已完成并冻结。

### T008：类别级 taxonomy

T008 使用 `all-MiniLM-L6-v2`、归一化向量和 Fast Community Detection 形成高置信度语义社区，再按商品类别进行语义与业务合并。

- 315,400 条 current-product candidate insight
- 4,992 个一级 cluster
- 887 个最终 category-level taxonomy theme
- 4,992 / 4,992 一级 cluster exact-once 映射

### T009：insight-taxonomy 映射

T009 通过确定性 join 连接 candidate、一级 cluster 和最终 taxonomy。

- 230,278 条 `mapped_by_cluster`
- 85,122 条 `unmapped_no_cluster`

未进入 community 的 insight 保留在 T009 结果中，不执行 nearest-theme 或强制分类。

### T010：商品级聚合

正式 T010 使用 DuckDB 完成确定性聚合。聚合按唯一 `review_id + taxonomy_id` 去重，并保留正面、负面、中性和 mixed 口径。

- 139 个商品
- 15,852 条 `product × taxonomy × sentiment` 主题业务记录
- 116,328 条主题月度趋势记录
- 222,069 条主题—评论证据记录

15,852 是商品、taxonomy 与情感组合后的业务记录数，不是 taxonomy 数量；正式 taxonomy 数量仍为 887。

Spark 和 Docker 保留用于全量清洗及早期环境实验，正式 T010 不依赖 Spark。

## 当前功能

- 商品选择和类别筛选
- 正面、负面主题切换
- 主题排行
- 月度趋势
- 动态主题词云
- 主题到原始评论证据下钻

当前正式数据链没有生成“产品改进需求”Gold，因此前端不展示该功能。旧接口中的兼容 route 或 pending 字段不代表该能力已经完成。

## 技术栈

- Python、DuckDB、Parquet
- Qwen3.5-4B
- Sentence-Transformers、all-MiniLM-L6-v2
- FastAPI
- Vue 3、TypeScript、Vite、ECharts
- Spark、Docker（全量清洗和历史环境）

## 项目结构

```text
pipelines/                              数据清洗、T009 映射与 T010 聚合脚本
data/gold/                              本地 Gold 产物；Git 仅保留小型验证摘要
backend_generated/backend/              正式 FastAPI 后端和 Gold repository
frontend_story_dashboard/frontend/      正式 Vue 前端
specs/001-merchant-review-insights/      需求、设计、任务和数据模型
infra/                                  Docker、Spark 和 MongoDB 环境配置
ml/                                     本地 NLP 与 XPU 处理脚本
docs/                                   环境说明和运行记录
```

## 启动方式

以下命令均从项目根目录开始执行。

后端：

```powershell
Set-Location backend_generated
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

后端默认读取：

```text
data/gold/t010-aggregation-20260908-v1-duckdb
```

前端：

```powershell
Set-Location frontend_story_dashboard\frontend
npm.cmd run dev
```

## 验证摘要

- [T008 validation](data/gold/t008-final-20260908-v1/validation.json)
- [T009 validation](data/gold/t009-insight-taxonomy-20260908-v1/validation.json)
- [T010 validation](data/gold/t010-aggregation-20260908-v1-duckdb/validation.json)

## 后续工作

- 将当前 Gold repository 与部署环境整理为可复现的发布配置。
- 在前端趋势图中将缺失月份补为 0；该显示问题不需要重跑 T010。
- 产品改进需求如需恢复，必须先建立对应的正式 Gold 数据链。
