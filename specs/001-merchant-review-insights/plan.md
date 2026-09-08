# Implementation Plan：家电整机评论洞察

**Updated**: 2026-09-08
**Spec**: [spec.md](spec.md)
**Technical selection**: [technical-selection.md](technical-selection.md)

## 当前执行覆盖说明

旧 ABSA→NLI attribution 链和 Transformers＋LMFE 串行 runner 仅作历史 baseline。新版T007已验收；T008已按category完成审核后taxonomy并冻结887个主题。当前推进T009：将315,400条`current_product` candidate逐条连接到一级cluster及taxonomy；未进入community的candidate保留为`unmapped_no_cluster`，不强制分类。

实现可在不修改 SDD 的情况下调整 prompt、量化、batch、constrained-decoding 后端和有限重试策略；每次候选实验必须记录配置与结果。业务 schema、数据范围、Gold 定义和禁止项不可由实现自行改变。

## 唯一处理链

```text
Bronze 2,128,605条原始评论
  → Docker Spark：Silver清洗、关联、语言与文本画像（已完成）
  → 正式范围：139个整机商品、116,728条评论（已完成）
  → 复用VADER整体情感（已完成）
  → NVIDIA/Linux：Qwen3.5-4B读取完整text_raw和商品上下文
  → vLLM continuous batching＋原生structured JSON生成insight
  → 程序执行schema校验、evidence grounding和字符offset计算
  → 保存success、partial_success、failed及rejected_insights
  → T008按category形成审核后taxonomy（已完成）
  → T009生成全量insight映射与未映射状态
  → T010按唯一review_id聚合主题数量、占比和趋势
  → 高频属性＋中心短语＋模板分别自动命名
  → Docker Spark：数量、占比、月度趋势、评论映射
  → Gold Parquet → MongoDB → FastAPI → Vue/ECharts
```

## 模块和依赖

| 模块 | 责任 | 依赖 |
|---|---|---|
| `scope` | 固定前端与完整NLP共同使用的139个整机商品 | Silver、文本画像、VADER |
| `absa` | 属性、属性情感、原句 | `scope` |
| `explicit-demand` | 对全部句子执行NLI并以三分类argmax确认明确建议 | `scope` |
| `evaluation-theme` | 分别合并正面和负面ABSA评价并自动命名 | `absa` |
| `improvement-theme` | 合并明确建议与隐式问题候选并自动命名 | `absa`、`explicit-demand` |
| `gold-aggregate` | 两类主题的数量、占比、趋势、状态和评论映射 | `evaluation-theme`、`improvement-theme` |
| `web` | 商品选择、主题、趋势、需求和原文展示 | `gold-aggregate` |

顺序固定为：`scope → absa、explicit-demand → evaluation-theme、improvement-theme → gold-aggregate → web`。

## 本地执行设计

- Docker Spark只执行批量读取、join、filter、groupBy和Gold聚合，不加载Transformer。
- T007 全量执行层为 NVIDIA/Linux vLLM；模型只加载一次并使用 continuous batching。Windows Intel XPU可用于兼容性实验，但不是本次全量后端。
- 禁止 silent CPU fallback；设备不满足要求时直接失败。
- runner 支持 resume、分片和逐批追加JSONL；单条失败不终止整个批次。
- 正式任务开始前打印输入行数；按固定间隔写入已处理量、吞吐和预计剩余时间；完成后核对输入、输出、success、partial_success和failed数量。
- 正式Gold采用新run id。旧TF-IDF主题和旧demands目录只保留为历史记录，不进入MongoDB活动批次。

## 输入处理

- ABSA保留属性所在原句；超过模型长度的评论按句子边界分块，不直接截掉后半段。
- 明确建议按句处理，全部句子进入NLI；entailment同时高于neutral和contradiction才确认，不设置MiniLM前置召回阈值，也不使用关键词过滤。
- 正面主题来自正面属性及原句；负面主题来自负面属性及原句；整体VADER作为评论级辅助字段，不代替属性极性。
- 明确建议不进入负面评价主题；它只进入改进需求链。
- 负面ABSA证据同时进入负面评价链和隐式改进候选链；两次出现是跨任务复用。
- 每个商品、每类主题独立聚类。显式建议和隐式问题可合并到相同改进主题，但必须保留来源类型。
- 任一分析维度在固定0.75/10参数下没有社区时输出0个主题，并记录`ready/no_qualified_theme`，不生成fallback。

## 验证关卡

1. `scope`：139个商品、13类、116,728条评论，前端集合与NLP集合一致。
2. `absa`：无CPU回退；每条输入有成功、无属性或失败状态；属性位置能回指原句。
3. `explicit-demand`：全部句子进入NLI，不得用关键词决定结果；保存三分类分数与模型版本；neutral最高不得确认。
4. `evaluation-theme`：只使用对应极性的ABSA；主题只包含同一商品；允许0主题并记录原因。
5. `improvement-theme`：只使用合格建议和隐式问题候选；来源、中心句和名称均可追溯；允许0主题并记录原因。
6. `gold-aggregate`：主题数量与映射中的不同`review_id`一致；趋势分母明确；三个分析维度状态齐全。
7. `web`：完成“选商品→评价主题→趋势→原文→改进需求”，并正确显示无合格主题状态；API请求不触发离线计算。

## 已知风险与限定

- ABSA正式处理时间尚未实测；现有89.43分钟只是最大256 token评论级纯推理外推。
- NLI模型的XPU兼容、吞吐和全量三分类分数已完成；旧接收规则错误忽略neutral，必须从现有分数重算。
- 模型可能抽取较宽泛属性，例如漏水句得到`water`；必须结合原句聚类，不直接发布属性词。
- NLI判定固定为entailment同时高于neutral和contradiction；不得另加未批准阈值或通过反复试验进行模型或规则竞赛。

## 不实施

预警、推荐、竞品分析、图数据库、评论有用性预测、模型训练、模型竞赛、零件/配件分析均不在本计划内。
