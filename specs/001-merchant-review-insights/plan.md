# Implementation Plan：家电整机评论洞察

**Updated**: 2026-09-06
**Spec**: [spec.md](spec.md)
**Technical selection**: [technical-selection.md](technical-selection.md)

## 唯一处理链

```text
Bronze 2,128,605条原始评论
  → Docker Spark：Silver清洗、关联、语言与文本画像（已完成）
  → 正式范围：139个整机商品、116,728条评论（已完成）
  → 复用VADER整体情感（已完成）
  → Windows XPU：ABSA属性及属性情感
  → Windows XPU：全部句子经MiniLM NLI确认明确建议
  → Windows XPU/CPU：MiniLM向量＋Fast Community Detection
  → 高频属性＋中心短语＋模板自动命名
  → Docker Spark：数量、占比、月度趋势、评论映射
  → Gold Parquet → MongoDB → FastAPI → Vue/ECharts
```

## 模块和依赖

| 模块 | 责任 | 依赖 |
|---|---|---|
| `scope` | 固定前端与完整NLP共同使用的139个整机商品 | Silver、文本画像、VADER |
| `absa` | 属性、属性情感、原句 | `scope` |
| `explicit-demand` | 对全部句子执行NLI并确认明确建议 | `scope` |
| `theme-merge` | 合并正负属性问题与建议并自动命名 | `absa`、`explicit-demand` |
| `gold-aggregate` | 数量、占比、趋势和评论映射 | `theme-merge` |
| `web` | 商品选择、主题、趋势、需求和原文展示 | `gold-aggregate` |

顺序固定为：`scope → absa、explicit-demand → theme-merge → gold-aggregate → web`。

## 本地执行设计

- Docker Spark只执行批量读取、join、filter、groupBy和Gold聚合，不加载Transformer。
- `ml/xpu/.venv/Scripts/python.exe`负责ABSA、MiniLM和NLI；设备必须是`xpu`，不可静默回退CPU。
- 模型只在长生命周期Windows进程中加载一次，按批写入可恢复的分片结果。
- 正式任务开始前打印输入行数；按固定间隔写入已处理量、吞吐和预计剩余时间；完成后核对输入、输出和失败数量。
- 正式Gold采用新run id。旧TF-IDF主题和旧demands目录只保留为历史记录，不进入MongoDB活动批次。

## 输入处理

- ABSA保留属性所在原句；超过模型长度的评论按句子边界分块，不直接截掉后半段。
- 明确建议按句处理，全部句子进入NLI；`entailment > contradiction`即确认，不设置MiniLM前置召回阈值，也不使用关键词过滤。
- 正面主题来自正面属性及原句；负面主题来自负面属性及原句；整体VADER作为评论级辅助字段，不代替属性极性。
- 每个商品独立聚类。显式建议和隐式问题可合并到相同改进主题，但必须保留来源类型。

## 验证关卡

1. `scope`：139个商品、13类、116,728条评论，前端集合与NLP集合一致。
2. `absa`：无CPU回退；每条输入有成功、无属性或失败状态；属性位置能回指原句。
3. `explicit-demand`：全部句子进入NLI，不得用关键词决定结果；保存entailment、contradiction分数与模型版本。
4. `theme-merge`：主题只包含同一商品；名称可追溯；评论映射去重。
5. `gold-aggregate`：主题数量与映射中的不同`review_id`一致；趋势分母明确。
6. `web`：完成“选商品→主题→趋势→原文→改进需求”，API请求不触发离线计算。

## 已知风险与限定

- ABSA正式处理时间尚未实测；现有89.43分钟只是最大256 token评论级纯推理外推。
- NLI模型尚未完成XPU兼容与吞吐检查，必须先检查再运行全部正式句子。
- 模型可能抽取较宽泛属性，例如漏水句得到`water`；必须结合原句聚类，不直接发布属性词。
- NLI判定固定为`entailment > contradiction`；不得另加未批准阈值或通过反复试验进行模型竞赛。

## 不实施

预警、推荐、竞品分析、图数据库、评论有用性预测、模型训练、模型竞赛、零件/配件分析均不在本计划内。
