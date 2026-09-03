# Intel Arc XPU 环境检查：更新驱动后通过

最新状态：2026-09-03约13:00，用户安装驱动32.0.101.8991后，设备、XPU模型与CPU对照
测试全部通过。下文先保留旧驱动失败历史，末尾记录复测和速度比较，不覆盖历史失败事实。

日期2026-09-03。先写增量规约和验收测试，再安装依赖；依照系统排错流程缩小模型错误，
未跳过失败用例，未把CPU成功当GPU成功。助手没有执行驱动更新、重启或Git推送；
驱动由用户完成更新。没有真实评论训练。

## 安装结果

- 显卡：Intel(R) Arc(TM) 130T GPU (16GB)，Core Ultra 5 225H。
- Windows驱动：32.0.101.6104，2024-11-09；16GB标签不表示独立显存。
- 独立目录ml/xpu/.venv：Windows Python3.12.12、torch2.14.0+xpu、triton-xpu3.8.0、
  Transformers5.16.1、sentence-transformers6.0.1、huggingface-hub1.29.0。
- uv sync退出0，66包安装成功，uv.lock固定完整依赖；uv pip check无依赖冲突。
- torch/triton-xpu来自PyTorch官方XPU索引，其余包来自PyPI。没有安装CUDA。
- 模型从既有Docker模型卷只读复制至tmp/xpu/models，复用锁定版本并验证逐文件哈希，
  没有重复下载模型，没有修改原始模型卷。权重哈希与CPU验收报告相同。
- 未替换宿主全局Python、ml/uv.lock或CPU Docker镜像。

安装初次解析失败：triton-xpu默认源仅找到旧版本；在官方XPU源确认存在3.8.0的Windows
cp312 wheel后，将其列为明确直接依赖并绑定官方索引，重新解析/安装成功。
下载/安装期间提前进行的递归语法检查误遍历了虚拟环境，已停止该检查进程；安装完成后
改为仅检查两个测试文件，py_compile退出0，依赖完整性检查通过。

## 首次实测结果（旧驱动）

| 检查 | 结果 |
|---|---|
| 安装前设备测试 | 缺少torch，收集失败；未向全局Python安装依赖 |
| 初版设备测试 | 1 passed in 9.87s，识别Arc130T，XPU逐元素平方/求和/autograd正确 |
| 扩充设备测试 | 1 passed、1 failed in 3.49s；仅16×16的Linear前向已复现同一错误 |
| 两模型XPU测试 | 2 failed in 46.63s，均在第一个注意力投影Linear前向失败 |
| 同安装环境CPU对照 | 2 passed in 24.57s，两模型输入与配置不变，仅NLP_DEVICE=cpu |

GPU错误原文：

```text
RuntimeError: could not make an engine with allocator
torch.nn.functional.linear(...)
```

失败在基础GPU线性计算路径，尚未进入正式训练。小线性层亦失败，说明不是仅因模型
规模、评论数据、标注或下载缺失。CPU对照通过进一步排除这次合成测试/模型加载的通用错误。
现有证据定位到XPU底层运行时/驱动兼容路径，但不足以断言旧驱动是唯一根因。

## 首次CPU对照（旧驱动阶段，不是GPU加速结果）

同一Windows XPU版PyTorch运行CPU、8线程、FP32、eager attention，2次预热+5次计时。

- DistilBERT batch8、固定128token：训练步骤中位0.914237秒，推理中位0.220672秒；
  主干参数更新，loss与梯度有限。计时不含加载、tokenization、设备搬运和断言。
- MiniLM：24条合成句子，batch8，输出24×384；encode中位0.029708秒，
  包含tokenization及返回CPU，不含模型加载；有限且归一化正确。
- CPU进程累计峰值工作集2,146,328,576 bytes，约2.00GiB；不是整机内存，
  也不是两个模型独立内存测量。报告tmp/xpu/reports/cpu-*.json。
- 尚无成功GPU模型报告，不能提供加速倍数或GPU训练内存结论。

## 当时的驱动更新门禁（已由用户完成）

Intel针对PyTorch2.14的[Windows前置条件指南](https://www.intel.com/content/www/us/en/developer/articles/tool/pytorch-prerequisites-for-intel-gpu/2-14.html)
建议32.0.101.8801或更新版本。本机驱动更旧，优先更新驱动后复测。
[官方驱动下载页](https://www.intel.com/content/www/us/en/download/785597/intel-arc-graphics-windows.html)
当前提供32.0.101.8991 WHQL，支持Arc130T/225H。通用驱动可能替换OEM定制驱动，
安装前检查厂商提示；若提示不兼容或要求强制覆盖则停止，不使用清洁卸载/DDU绕过限制。
驱动更新可能要求管理员确认和重启，必须由用户确认并操作，已安装的Python环境无需重装。

更新后先运行ml/xpu/README.md中的test_device.py，完整通过后再跑两模型测试和CPU/GPU比较。
模型测试显式local_files_only/offline，不设置系统级断网；CPU Docker离线验收不受影响。
本记录只说明 XPU 环境的运行结果，数据清洗和项目汇报进度见各自文档。

## 更新驱动后的复测：2026-09-03约13:00

用户报告“已经全部安装完毕”并附驱动截图。Get-CimInstance Win32_VideoController
实测DriverVersion=32.0.101.8991；不是只依据截图判断运行成功。
本轮未修改测试代码、依赖锁或模型。沿用ml/xpu/README.md中的命令顺序执行：

1. `pytest ml/xpu/test_device.py -q -s`：2 passed in 3.41s；原失败的线性层及反向传播通过。
2. `NLP_DEVICE=xpu`运行test_models.py：2 passed in 13.90s。
3. `NLP_DEVICE=cpu`运行同一test_models.py：2 passed in 13.76s。
4. `uv pip check --python ml/xpu/.venv/Scripts/python.exe`：66包依赖兼容。

以上NLP_DEVICE为环境变量说明，不是PowerShell赋值语法；完整命令见ml/xpu/README.md。
先前engine with allocator错误不再出现。证据支持这次驱动更新解决了已复现的兼容问题，
不意味着所有XPU算子、精度和优化模式都已测试。

### 同条件小基准

同一Windows环境和PyTorch2.14.0+xpu，CPU8线程，FP32、eager attention；
DistilBERT batch8、固定128token、AdamW foreach=False；两边均2次预热+5次计时，
GPU同步计时。MiniLM为24条合成句子、batch8。CPU/XPU先后运行，不并发竞争。

| 指标（中位数） | CPU | Intel XPU | CPU耗时/XPU耗时 |
|---|---:|---:|---:|
| DistilBERT训练一步 | 0.764021秒 | 0.207934秒 | 3.67 |
| DistilBERT推理一批 | 0.180392秒 | 0.045897秒 | 3.93 |
| MiniLM encode 24句 | 0.026105秒 | 0.022980秒 | 1.14 |

这是预加载后的短测试，不是全流程端到端耗时。MiniLM仅数毫秒差异，5次样本不足以保证
真实负载始终加速。训练采用合成标签和随机分类头，seed相同也不保证CPU/XPU dropout
随机序列一致，因此loss轨迹不同不作为错误；此次并未执行正式模型精度评估。
MiniLM前三条句向量跨设备最大绝对差约1.155e-7；两边向量有限且归一化正确。

### 内存与使用边界

- DistilBERT GPU分配器峰值allocated=1,282,674,176 bytes（约1.195GiB）；
  reserved=1,631,584,256 bytes（约1.520GiB）。
- MiniLM GPU分配器峰值allocated=94,133,248 bytes；reserved=1,642,070,016 bytes，
  包含同进程前一个模型留下的缓存，不能视为MiniLM独立占用。
- Windows测试进程累计峰值工作集：CPU2,080,739,328 bytes（约1.94GiB）；
  XPU5,080,625,152 bytes（约4.73GiB）。它们与GPU分配器统计有不同口径，不应相加。
- 新报告保存于tmp/xpu/reports/cpu-*.json和xpu-*.json，旧CPU诊断报告已按说明被本次
  覆盖；上述旧阶段结果仍保存在本文历史部分。没有保存业务训练checkpoint。
- Windows原生GPU进程不受Docker/WSL的容器内存限额约束。正式训练仍与Spark全量作业错峰。

结论：XPU基础环境现已验收，本机可以用Intel GPU继续开发和训练验证；CPU环境保留。
本轮无需再要求用户重启或重装环境。正式训练前仍需真实样本、较长运行、批次大小、质量
评估及计划中的10,000句性能基准；AMP、torch.compile、OpenVINO未在本轮验证。
