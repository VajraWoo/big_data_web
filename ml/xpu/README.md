# Intel Arc XPU 独立验证环境

此目录使用Windows原生Python，不改变ml/的CPU Docker环境。
当前状态：2026-09-03，用户将Arc130T驱动更新至32.0.101.8991后，
设备测试2项、XPU模型测试2项、CPU对照模型测试2项全部通过。
此前32.0.101.6104下出现`could not make an engine with allocator`；
同一代码/依赖在更新后通过，保留失败历史及结果于../../docs/runs/xpu-environment-2026-09-03.md。
本机现在无需重装Python或模型，也不要求额外重启；以后驱动变更应复测。

仓库根目录、普通PowerShell安装（无需管理员）：

```powershell
uv sync --project ml/xpu --python 3.12.12 --frozen
uv run --project ml/xpu --frozen pytest ml/xpu/test_device.py -q -s
```

第二条必须显示真实Intel设备并通过张量和线性层运算/反向传播，失败时停止，不回退CPU。
torch和triton-xpu均取自PyTorch官方XPU索引；其余依赖固定于本目录uv.lock。
与CUDA版本不同，不需要NVIDIA驱动，不需要源码编译或额外安装整套oneAPI开发工具。

模型测试复用ml/model-lock.json固定的文件。tmp/xpu/models须包含distilbert、minilm
及download-manifest.json；本机已从CPU模型卷只读复制并验证权重hash。
该缓存不进入Git，复制不会改变Docker模型卷。

设备检测通过后，在仓库根目录分别执行以下命令，测试期间不跑Spark批处理：

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:NLP_DEVICE = 'cpu'
uv run --project ml/xpu --frozen pytest ml/xpu/test_models.py -q -s
$env:NLP_DEVICE = 'xpu'
uv run --project ml/xpu --frozen pytest ml/xpu/test_models.py -q -s
```

只使用本地文件，未设置系统级断网。报告输出tmp/xpu/reports/<device>-<model>.json，
重复执行覆盖同名诊断报告，不保存正式训练权重。
同一Windows/XPU版PyTorch、FP32、eager attention、batch8；2次预热、5次计时，
XPU在计时边界同步。DistilBERT固定128token；MiniLM为24条合成句子。
报告区分Windows进程累计峰值工作集与PyTorch XPU分配器峰值；两者不是同一个量，
不得相加作为整机内存，也不能把共享内存标称16GB当成独立显存。
没有AMP或torch.compile，不据此保证全量训练速度；无真实评论数据。

本次FP32小基准：DistilBERT训练步骤CPU0.764秒/XPU0.208秒，推理CPU0.180秒/XPU0.046秒；
MiniLM encode CPU0.0261秒/XPU0.0230秒，短用例差异较小，不推广为稳定加速承诺。
本机可使用XPU继续模型开发，CPU仍是可用对照。正式训练设备/批次须在真实样本上校准。
XPU分配器峰值不等于全部宿主内存；本次XPU测试进程累计峰值工作集约4.73GiB，
与Spark全量作业错峰运行。Windows原生XPU进程不受Docker的12GiB容器限制。
