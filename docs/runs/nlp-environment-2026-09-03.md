# NLP 基础环境验收：2026-09-03

范围：第一周环境搭建，不是正式训练或真实评论处理。按照NLP增量规约先写验收、
再搭建环境，最后运行真实CPU计算。没有改变Bronze、生成Silver/Gold或推送Git。

## 环境与来源

本机Intel Core Ultra 5 225H、32GB物理内存，WSL上限20GB。
Linux/amd64容器，Python3.12.12，torch2.14.0+cpu，Transformers5.16.1，
sentence-transformers6.0.1，huggingface-hub1.29.0；全部依赖见ml/uv.lock。
CPU容器限制12GiB/8CPU，下载前确认Spark两Worker存活、活动应用0、已用核心0。
未安装CUDA或修改Windows全局Python；未安装或验证OpenVINO/IntelGPU后端。

模型来源与固定revision：

- [DistilBERT官方模型仓库](https://huggingface.co/distilbert/distilbert-base-uncased)：
  `12040accade4e8a0f71eabdb258fecc2e7e948be`。
- [MiniLM官方模型仓库](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)：
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`。

两者模型卡标注Apache-2.0。明确下载文件列表见ml/model-lock.json，权重采用safetensors；
加载禁止远程代码。下载文件总字节分别为268,672,802和91,578,415（含配置等文件，
不等同Docker卷总占用）。逐文件摘要保存在模型卷download-manifest.json并由测试复核。

权重文件实测SHA-256：

```text
DistilBERT 5e3f1108e3cb34ee048634875d8482665b65ac713291a7e32396fb18f6ff0063
MiniLM    53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db
```

## 可复现命令与结果

仓库根目录、Docker Desktop运行、普通PowerShell：

```powershell
docker compose -f infra/compose.nlp.yaml --profile ml build nlp-check
docker compose -f infra/compose.nlp.yaml --profile ml run --rm nlp-download
docker compose -f infra/compose.nlp.yaml --profile ml run --rm nlp-check
python -m unittest discover -s infra/tests -v
```

- 构建及下载：退出码0；没有要求额外安装主机环境。
- 负向验证：配置文件尚未创建时配置测试失败；模型下载前运行checksums用例，
  因`/models/download-manifest.json`缺失明确失败，1 failed、2 deselected，退出码1。
  这是预期负向结果，不把缺失模型误判为网络故障。
- 下载后完整离线验证：`3 passed in 9.62s`，退出码0。
- 基础设施配置回归：9项通过，退出码0。

离线验收采用`network_mode: none`、HF_HUB_OFFLINE=1、TRANSFORMERS_OFFLINE=1，
模型卷只读，未挂载真实评论。不是仅设置缓存后仍允许访问网络的测试。

| 检查 | 实际证据 |
|---|---|
| 模型完整性 | 两个模型所有指定文件的字节数、SHA-256及锁定revision一致 |
| DistilBERT训练链路 | CPU、seed42、合成文本batch2，前向/反向/AdamW一步后主干权重改变；loss=0.6793224215507507且梯度有限 |
| DistilBERT推理链路 | 更新后切换eval/no_grad，输出有限数值；该用例0.613秒 |
| MiniLM句向量 | 3个合成英文句子输出3×384矩阵；向量有限且L2范数约1；该用例0.088秒 |
| 进程内存 | 两次报告的累计进程峰值RSS均为1,737,192 KiB，约1.66 GiB |

耗时含各用例的加载/计算，但不含镜像构建、下载和全部测试启动；内存是同一pytest进程的
累计峰值，不是两个模型各自独立测量，也不是整个Docker内存。不能据此推算正式训练资源。

DistilBERT加载时报告原预训练词表预测头UNEXPECTED、新分类头MISSING，是更换任务头的
预期提示。随机分类头和任意合成标签只验证机械流程，不代表商品情感识别有效。
没有开展正式微调、模型评估、1万句性能基准或真实评论标注。

## 持久化与收尾

模型位于`big-data-web-nlp_models`，不进入Git；后续本机离线验收不用重新下载。
报告位于`big-data-web-nlp_reports`的distilbert.json、minilm.json；重复验收覆盖本次
专用诊断报告，不覆盖原始数据或训练checkpoint。不要删除这些卷或运行全局prune。

按需容器均已正常退出并移除，模型缓存保留。收尾检查：原6个Web/Spark/MongoDB服务
全部healthy，后端返回`{"service":"ok","mongodb":"ok","active_run":null}`。

第一周仍需真实小样本规则验证、同一管道全量基础清洗与Silver质量报告、商品群画像、
初版分工和教师确认材料；MongoDB Spark Connector接入也仍待验证。
