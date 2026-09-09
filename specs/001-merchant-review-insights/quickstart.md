# Quickstart: Current Gold Web Application

**Updated**: 2026-09-09

当前 T007–T011 已完成。以下命令只启动正式后端和前端，不运行数据 pipeline、Spark 或模型。

## Required local data

后端需要：

```text
data/gold/t010-aggregation-20260908-v1-duckdb/
data/gold/t011-final-corrected-20260909-v1.ndjson
data/gold/t010-polarity-overrides-20260909-v1.json
```

T010 目录必须包含 products、product_facets、themes、theme_timeseries、theme_reviews、batch 和 validation 文件。T011 corrected 文件应为 7,734 行；override 应包含 13 条 correction。

## Start backend

```powershell
Set-Location D:\CS_Projects\big_data_web\backend_generated
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

## Start frontend

```powershell
Set-Location D:\CS_Projects\big_data_web\frontend_story_dashboard\frontend
npm.cmd run dev
```

## Lightweight verification

```powershell
Set-Location D:\CS_Projects\big_data_web\backend_generated\backend
..\.venv\Scripts\python.exe -m pytest -q

Set-Location D:\CS_Projects\big_data_web\frontend_story_dashboard\frontend
npm.cmd run build
```

联调时验证：商品列表可用；正负主题按 override 正确分流；负面主题详情显示趋势、T011 建议和评论证据；正面主题不显示建议；无建议主题呈现明确空状态。

## Do not run

当前阶段不要重跑 T007–T011，不要重新连接 GPU/AutoDL，不要启动 Spark 聚合，不要重新执行 embedding、clustering、reranking 或阈值实验。
