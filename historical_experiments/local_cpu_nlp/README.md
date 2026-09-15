# 历史实验：本地 CPU NLP

本目录归档第一周搭建但未被最终语义流水线采用的本地 CPU NLP 方案，保留它只为呈现真实研发过程和 Git 提交历史。

归档内容包括：

- DistilBERT 与 MiniLM 的下载和离线环境验证；
- VADER 情感标注作业；
- DeBERTa zero-shot 需求分类作业；
- 对应 Docker、Compose、依赖锁和测试代码；
- 原始第一周运行说明 `ORIGINAL_README.md`。

这些代码不参与 T007–T011，不生成当前 Gold 数据，也不是正式应用的运行依赖。原始说明中的路径保留历史语境，迁移后不保证可以直接执行。

最终采用的语义方案为：

- T007：`prototypes/t007_context_insight_v2_1/` 中的 Qwen3.5-4B vLLM runner；
- T011：`pipelines/run_t011_qwen.py` 中的 Qwen3.5-4B vLLM runner。
