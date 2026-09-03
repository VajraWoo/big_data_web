# 第一周 Intel GPU 验证增量

2026-09-03。用户授权先安装并验证本机Intel GPU，再继续第一周收尾。
本增量补充CPU环境，不改变业务范围，不要求队友联合训练或统一GPU型号。

## 验收和实施顺序

- [x] X001：独立Windows Python3.12环境和XPU依赖锁定；不替换CPU Docker镜像或全局Python。
- [x] X002：识别Intel Arc 130T，真实XPU张量及线性层计算与反向传播通过；不可静默回退CPU。
- [x] X003：固定版本DistilBERT训练步骤/推理、MiniLM句向量在真实XPU上验证通过。
- [x] X004：相同模型、输入、精度、批次下CPU/XPU预热后比较；同步GPU计时，报告内存口径。
- [x] X005：记录实际结果、阻碍与复现命令；需要驱动更新/重启时先告知用户，不擅自执行。

首次本机检查：Intel Arc 130T，当时驱动32.0.101.6104（2024-11-09）。
PyTorch2.14对应Intel官方Windows指南建议32.0.101.8801或更新，现有版本低于该指南。
先准备隔离软件环境并检查设备；不得在尚未运行模型前宣称GPU已可用或比CPU快。
若必须用户更新驱动则在此门禁暂停，不将CPU通过冒充XPU通过。

实际进展：torch2.14.0+xpu/triton-xpu3.8.0和其余依赖安装成功，uv pip check通过。
最小逐元素设备测试1 passed，实际设备Intel Arc 130T；随后扩充线性层测试，
得到1 passed、1 failed，报could not make an engine with allocator。
两模型XPU测试均在Linear前向失败；同一XPU安装环境切换CPU则2 passed。
不能把简单张量通过视为模型训练可用。当时X002—X004未完成，记录见docs/runs/xpu-environment-2026-09-03.md。

同日13:00复测：用户更新驱动至32.0.101.8991后，代码、依赖、模型不变，设备2项、
XPU模型2项和CPU对照2项全部通过。训练主干更新、有限梯度、384维归一化句向量确认。
本轮X001—X005完成；FP32合成小基准不等于正式训练或10,000句性能验收。

采用ml/xpu/.venv的Windows原生路径，原因是官方支持Windows XPU，可以直接使用宿主显卡，
无需改动现有Docker/WSL服务或向Docker添加实验性Intel GPU映射。
沿用ml/model-lock.json模型版本；本地缓存和临时报告放tmp/xpu，不进入Git。
仅合成输入，不做真实评论训练、标注或Silver/Gold。

依据：
- https://docs.pytorch.org/docs/2.14/notes/get_start_xpu.html
- https://www.intel.com/content/www/us/en/developer/articles/tool/pytorch-prerequisites-for-intel-gpu/2-14.html
