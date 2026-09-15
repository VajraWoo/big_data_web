# ML 目录说明

本目录不再包含第一周的本地 CPU NLP 方案。最终 T007 和 T011 使用 Qwen3.5-4B、vLLM、NVIDIA/Linux 离线完成，正式代码分别位于：

- `pipelines/t007/`
- `pipelines/t011/run_t011_qwen.py`

当前仅保留：

- `xpu/`：项目早期实际使用过的 Windows Intel XPU 实验与辅助脚本；
- `model-lock.json`：`xpu/test_models.py` 仍读取的模型版本清单。

XPU 代码不是最终 T007/T011 的推理后端，不参与正式 Gold 结果。未采用的 DistilBERT、MiniLM CPU 环境、VADER 和 DeBERTa zero-shot 代码已迁移到 `historical_experiments/local_cpu_nlp/`。
