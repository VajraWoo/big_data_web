# 第一周 NLP 运行环境

本目录安装并验证CPU深度学习环境，不包含已经训练好的商品情感/需求分类器。
操作从仓库根目录执行，普通PowerShell即可，Docker Desktop保持运行。

## 构建、下载、离线验证

```powershell
docker compose -f infra/compose.nlp.yaml --profile ml build nlp-check
docker compose -f infra/compose.nlp.yaml --profile ml run --rm nlp-download
docker compose -f infra/compose.nlp.yaml --profile ml run --rm nlp-check
```

前两步需要联网（Docker Hub/GHCR/PyPI/PyTorch/Hugging Face）。第三步的容器禁用网络，
设置HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE，验证权重已经完整保存在本地。
没有模型文件时应失败，不能把缺少文件的离线失败当网络故障。

环境：Python3.12.12、torch2.14.0+cpu、transformers5.16.1、
sentence-transformers6.0.1、huggingface-hub1.29.0。直接依赖与传递依赖由uv.lock固定。
Torch只从官方CPU索引安装，没有CUDA，也不修改Windows的Python环境。

模型来源与revision见model-lock.json，均按模型卡标注Apache-2.0：

- distilbert/distilbert-base-uncased：预训练语言模型，后续需要对我们的任务训练分类头。
- sentence-transformers/all-MiniLM-L6-v2：将英文文本编码为384维句向量，不直接输出情感标签。

只下载指定safetensors、tokenizer、配置和模型卡，加载时trust_remote_code=False。
不下载或执行模型仓库的Python脚本；不把任意远程仓库代码装进项目。

## 验收内容

1. 对比固定revision与下载后完整文件SHA-256。
2. DistilBERT加载预训练主干，新建随机分类头；两条合成英文文本、任意测试标签，
   在CPU完成一次前向、反向和AdamW更新，检查有限loss/梯度与主干参数变化。
3. MiniLM对三条合成英文文本生成3×384有限、归一化向量。

出现“分类头新初始化，需要训练”的提醒是预期现象。一次更新证明训练链路可用，
不证明模型已经会判断商品情感或需求，也不能直接推算全量训练耗时。
本轮无真实评论输入、不生成业务标签、不保存正式模型checkpoint。

## 数据位置与资源

- `big-data-web-nlp_models`：模型缓存与download-manifest.json；验收时只读挂载。
- `big-data-web-nlp_reports`：最近一次DistilBERT/MiniLM环境检查JSON报告。
- 模型权重在Docker named volume中，不进入Git，不必每次重新下载。
- 容器按需启动，完成后--rm自动退出；不映射端口，内存上限12GiB、CPU配额8。
- 不与Spark全量作业/正式训练并发运行；空闲Web服务和数据库可保持运行。
- 原CPU验收不包含GPU/OpenVINO；后续已在[xpu/](xpu/README.md)单独安装Windows XPU，
  用户更新驱动到32.0.101.8991后，张量、线性层和两模型测试全部通过；
  DistilBERT小基准训练步骤GPU约为CPU的3.67倍速度，非正式训练耗时保证。OpenVINO未安装。

重复运行只更新本目录专用卷中的环境报告；不触碰Bronze/Silver或数据库。
不要运行带-v的down或全局prune，否则可能丢失缓存，需要重新下载。
通过环境验证后，第一周仍须完成真实评论规则验证、全量基础清洗和质量报告。
