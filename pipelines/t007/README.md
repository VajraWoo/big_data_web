# T007 正式 Qwen3.5-4B Insight Runner

本目录是 T007 最终冻结并实际完成全量处理的正式源码，不是旧 CPU NLP baseline。

## 文件职责

- `runner.py`：vLLM structured-output 批处理、checkpoint/resume、失败隔离及运行汇总。
- `prompt.py`：`t007-context-insight-v2.1` 提示词和 JSON schema。
- `contract.py`：输出规范化、evidence grounding、offset 计算和拒绝原因。
- `tests/`：schema、prompt、quote grounding、失败记录与 runner 行为测试。

## 冻结配置与结果

- 模型：`Qwen/Qwen3.5-4B`
- revision：`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`
- 运行环境：NVIDIA/Linux、vLLM 0.28.0、RTX 4090
- 输入/输出：116,728 / 116,728 条，`review_id` exact-once
- 有效 insight：350,656 条
- prompt version：`t007-context-insight-v2.1`

输入使用完整评论 `text_raw`，一条评论可以产生零到多个 grounded insight。正式结果已经完成并冻结；最终 Web 请求不会调用本 runner。

全流程位置和 T008–T011 的衔接见上级 `README.md`。
