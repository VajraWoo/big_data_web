# 第一周 NLP 环境增量规约

2026-09-03。用户：“好的。那nlp继续完成？”
承接plan.md的CPU训练主线，只验证环境，不做真实评论标注、训练、推断或业务结论。

**文档性质**：第一周 NLP 环境验收历史记录。这里验证的 DistilBERT/MiniLM CPU/XPU 环境
不是最终 T007/T011 推理方案；正式语义流水线后来采用 Qwen3.5-4B，并已完成和冻结。

## 验收

- NLP-ENV-01：Linux/Python3.12、CPU版PyTorch、Transformers、sentence-transformers
  与测试依赖锁定；不安装CUDA，不修改Windows全局Python。
- NLP-ENV-02：DistilBERT/MiniLM从官方仓库按40位commit下载，仅safetensors权重和
  配置/tokenizer/模型卡，不执行远程仓库代码；缓存不进Git。
- NLP-ENV-03：真实DistilBERT CPU前向、反向、optimizer.step通过，loss/梯度有限、
  至少一个主干参数改变；合成数据仅验证训练机械流程，随机分类头不代表情感识别能力。
- NLP-ENV-04：MiniLM将3个英文句子编码为3×384有限向量，归一化长度合理。
- NLP-ENV-05：完整本地模型可在network none、offline环境中加载并完成上述检查，
  保存版本、模型commit、哈希、耗时和内存报告，不把短测试当全量训练耗时估计。
- NLP-ENV-06：独立按需容器12GiB/8CPU、不映射端口、不挂载真实数据；与Spark全量作业错峰。

## 设计与任务

原 `ml/pyproject.toml` 与 `ml/uv.lock` 已归档到 `historical_experiments/local_cpu_nlp/ml/`；它们曾用于独立锁定第一周 NLP 环境。
固定Python3.12.12/uv0.12.9基础镜像digest。torch2.14.0+cpu使用官方CPU索引，
Transformers5.16.1、sentence-transformers6.0.1、huggingface-hub1.29.0使用PyPI。
`ml/model-lock.json` 保存模型 repo/commit、许可和明确文件列表。下载流程与离线验收分开：
nlp-download容器允许网络；nlp-check容器network_mode=none、模型卷只读、只写报告卷。
两个服务默认不启动；不需要停止空闲Web/数据库，但执行前确认没有Spark作业。
OpenVINO/IntelGPU为设计中可选后端，本轮不声称其已配置或测出加速效果。

- [x] N001 写配置验收与模型锁文件，记录环境文件缺失的失败证据。
- [x] N002 锁定依赖；原 `ml/Dockerfile` 和 `infra/compose.nlp.yaml` 现归档于 `historical_experiments/local_cpu_nlp/`。
- [x] N003 下载固定revision模型并记录文件SHA-256。
- [x] N004 断网完成CPU推理、反向更新、句向量测试，记录docs/runs/nlp-environment-2026-09-03.md。
- [x] N005 更新当时的第一周进度；“正式模型训练与数据清洗尚未完成”仅描述 2026-09-03
  的阶段状态。当前 Silver 清洗和 T007–T011 均已完成。
