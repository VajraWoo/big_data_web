# T011：产品改进建议

- `prepare_t011_inputs.py`：按 `parent_asin + taxonomy_id` 准备确定性输入；
- `run_t011_qwen.py`：使用 Qwen3.5-4B、vLLM 和 structured JSON 离线生成建议；
- `tests/`：输入准备和 runner 单元测试。

原始 7,747 个触发组全部生成。纠正 13 个假负面组后，正式结果为 `data/gold/t011-final-corrected-20260909-v1.ndjson` 中的 7,734 条建议；对应展示层修正位于 `data/gold/t010-polarity-overrides-20260909-v1.json`。

本阶段已经离线完成，正式 API 不调用模型。
