# 技术选型：家电整机评论洞察

**Status**: Approved  
**Updated**: 2026-09-06

## 原则

使用成熟、公开、可在本地直接推理的现成方法；不自行训练，不组织模型竞赛。关键词不能直接决定建议标签。Spark只承担数据处理与聚合，Transformer统一在Windows XPU进程运行。

## 固定技术与当前证据

| 任务 | 固定技术 | 本地运行位置 | 当前测试或运行结果 |
|---|---|---|---|
| 原始清洗与关联 | Spark 4.1.2、Parquet | Docker：1 Master＋2 Workers | 2,128,605条评论和94,327条商品元数据已完成Silver |
| 语言识别 | fastText `lid.176` | Docker Spark | 1,815,794条有效英文评论已完成 |
| 正式商品范围 | 类目白名单＋时间/活跃度/数量规则 | Windows DuckDB读取Parquet | 139个整机商品、13类、116,728条评论；结果已与Parquet重计数一致 |
| 整体情感 | VADER 3.3.2 | Docker Spark CPU | 1,815,794条已完成：正面1,333,505、负面268,727、中性213,562；98.42秒 |
| 属性及属性情感 | `yangheng/deberta-v3-base-end2end-absa`，锁定revision `23e6d43431a5f96d8a7b7b9721d59bbda30cc63d` | Windows `ml/xpu/.venv`，Intel Arc XPU，batch 16，最大256 token | XPU通过；1,024条真实评论47.071秒，21.755条/秒；纯推理外推116,728条约89.43分钟；峰值allocated约1.29GB、reserved约1.41GB |
| 明确建议确认 | 全部句子使用`cross-encoder/nli-MiniLM2-L6-H768`；`entailment > contradiction`即接受 | Windows XPU | 选型和判定规则已确定；尚未下载和进行兼容/吞吐检查 |
| 相似主题合并 | `all-MiniLM-L6-v2`＋Sentence-Transformers Fast Community Detection；相似度0.75、最少10条不同评论 | Windows XPU生成向量；CPU执行聚类 | MiniLM既有24句XPU检查通过；聚类算法和官方默认参数已确定；正式范围尚未运行 |
| 主题自动命名 | 高频属性＋聚类中心观点短语＋模板规范化；失败时用中心短语 | Windows普通Python | 方法已批准；尚未实现 |
| 数量与时间趋势 | Spark按商品、主题、月份分组聚合 | Docker Spark | Spark能力已有全量任务验证；新版主题尚未聚合 |
| Gold查询与原文下钻 | Parquet→MongoDB 8→FastAPI→Vue 3/ECharts | Docker服务 | 环境已建立；新版业务数据和页面尚未完成 |

## ABSA输出约定

模型只承担属性及属性情感，不声称输出完整观点三元组。每项结果保存属性文本、极性、置信度、字符位置和完整原句。已验证示例包括：

- `ice maker / Negative`
- 同一句中的`basket / Negative`与`controls / Positive`
- `cooling performance / Positive`

模型可能将漏水句抽取为`water / Negative`，因此最终问题主题必须结合原句和后续MiniLM聚类形成，不能把属性词直接当作主题名称。

## 明确建议流程

```text
评论切句
  → 全部句子进入cross-encoder/nli-MiniLM2-L6-H768
  → entailment分数大于contradiction分数时确认明确改进建议
  → 保留建议句、分数和评论ID
```

`wish / need / should / could / would like / if only / hope`不得成为入口或判断依据。全部句子进入NLI，不设置MiniLM前置召回阈值，也不另设主观置信度阈值；判定规则固定为`entailment > contradiction`。

## 主题与需求合并

- 每个`parent_asin`独立聚类，不跨不同商品混合主题。
- MiniLM生成向量，Fast Community Detection按余弦相似度寻找局部语义社区；使用官方默认相似度0.75和最小社区10条不同评论。
- 明确建议与ABSA负面问题分别保留来源类型，合并后仍可区分显式建议和隐式改进方向。
- 名称优先使用高频属性＋中心观点短语＋固定模板；没有可靠模板时直接使用中心短语。

## 性能解释

ABSA的89.43分钟是1,024条真实评论、batch 16、最大256 token下的纯推理外推，不包含正式读写、长评论分块和失败重试，不能写成正式任务承诺。昨天三小时未完成的是CPU Spark中的四标签DeBERTa zero-shot旧任务，与本次单次token-classification XPU基准不同。

## 已否决方案

- 所有至少50条评论的商品进入前端；
- 只选择Water Filters和Ice Makers；
- 裸关键词召回后对205,855条评论执行四标签DeBERTa-base zero-shot；
- 在Spark partition中创建Transformer pipeline；
- 使用旧TF-IDF词组作为新版最终主题；
- 自行训练或比较大量候选模型。
