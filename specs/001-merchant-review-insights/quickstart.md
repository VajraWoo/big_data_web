# Quickstart：新版处理链

## 已有数据

```powershell
python -m pipelines.scope_filter_job --silver-root data/silver/silver-full-20260903T154909-6c310067 --sentiment-root data/gold/sentiment-20260905T202327/sentiment --output data/gold/scope-filter-20260906-v3
```

预期：139个整机商品、13类、116,728条正式评论。该目录已存在时不得覆盖；当前结果直接复用。

## XPU环境

```powershell
uv run --project ml/xpu --frozen pytest ml/xpu/test_device.py -q -s
```

必须显示Intel Arc 130T并通过；失败时停止，不回退CPU。

## 后续正式命令

ABSA、明确建议、主题聚类和新版Gold脚本尚未实现。实现后必须在本文件补充可直接复制的完整PowerShell命令；在此之前不得使用旧`ml/run_demands.ps1`或把旧`pipelines/run_topics.ps1`输出发布为新版Gold。

## Web环境

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml up -d --build
Invoke-RestMethod http://localhost:8000/api/v1/health
```

验证目标：选择正式商品、查看正负主题、查看数量和趋势、下钻原文、查看明确建议和隐式改进方向。
