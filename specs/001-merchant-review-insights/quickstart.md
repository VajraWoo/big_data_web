# Quickstart：新版处理链

## 已有数据

```powershell
python -m pipelines.scope_filter_job --silver-root data/silver/silver-full-20260903T154909-6c310067 --sentiment-root data/gold/sentiment-20260905T202327/sentiment --output data/gold/scope-filter-20260906-v3
```

预期：139个整机商品、13类、116,728条正式评论。该目录已存在时不得覆盖；当前结果直接复用。

## XPU环境

```powershell
uv run --project ml/xpu --frozen pytest ml/xpu/test_device.py -q -s
```

必须显示Intel Arc 130T并通过；失败时停止，不回退CPU。

## 后续正式命令

正式范围导出、切句和ABSA句界分块：

```powershell
python -m pipelines.nlp_input_job --scope-root data/gold/scope-filter-20260906-v3 --silver-root data/silver/silver-full-20260903T154909-6c310067 --sentiment-root data/gold/sentiment-20260905T202327/sentiment --output data/gold/nlp-input-20260906-v1
```

修订后的明确建议重算、评价主题、改进需求和新版Gold脚本尚未实现。实现后必须在本文件补充可直接复制的完整PowerShell命令；在此之前不得使用旧`ml/run_demands.ps1`、旧`pipelines/run_topics.ps1`或受旧NLI判定污染的主题结果作为新版Gold。

ABSA正式分片与结果汇总：

```powershell
python -m pipelines.prepare_absa_input_job --nlp-input data/gold/nlp-input-20260906-v1 --output data/gold/absa-input-20260906-v1 --shard-count 24
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
ml/xpu/.venv/Scripts/python.exe ml/xpu/run_absa.py --input-dir data/gold/absa-input-20260906-v1 --output data/gold/absa-20260906-v1 --model-path C:/Users/31407/.cache/huggingface/hub/models--yangheng--deberta-v3-base-end2end-absa/snapshots/23e6d43431a5f96d8a7b7b9721d59bbda30cc63d --batch-size 16 --max-length 256 --stride 32
python -m pipelines.finalize_absa_job --shard-root data/gold/absa-20260906-v1 --output data/gold/absa-final-20260906-v1
```

固定NLI模型的单次1,024句XPU检查：

```powershell
ml/xpu/.venv/Scripts/python.exe ml/xpu/check_nli.py --model-path C:/Users/31407/.cache/huggingface/hub/models--cross-encoder--nli-MiniLM2-L6-H768/snapshots/b95119ce93d3e065de6214e38cd4a97b0f2f2c6d --input tmp/xpu/nli-benchmark-sentences.json --output tmp/xpu/reports/xpu-nli-minilm2.json --batch-size 32 --max-length 256
```

以下命令已经生成全部句子的三分类分数，保留为可复用的历史运行证据；不得重复执行XPU推理。其旧汇总使用了错误的`entailment > contradiction`规则，不得作为新版明确建议结果：

```powershell
ml/xpu/.venv/Scripts/python.exe ml/xpu/run_nli.py --input-dir data/gold/absa-input-20260906-v1 --output data/gold/nli-20260906-v1 --model-path C:/Users/31407/.cache/huggingface/hub/models--cross-encoder--nli-MiniLM2-L6-H768/snapshots/b95119ce93d3e065de6214e38cd4a97b0f2f2c6d --batch-size 32 --max-length 256 --stride 32
python -m pipelines.finalize_nli_job --shard-root data/gold/nli-20260906-v1 --output data/gold/nli-final-20260906-v1
```

T009下一步只复用已有三分类分数，在CPU上按新规则重算明确建议；不加载模型、不重复执行XPU推理，并写入新目录保留旧结果：

```powershell
python -m pipelines.reclassify_suggestions_job --input data/gold/nli-final-20260906-v1/sentence_nli.parquet --output data/gold/nli-final-20260906-v2
```

该命令准备完成但尚未执行。执行并通过数量对账后，才能把新版明确建议交给T010。

## Web环境

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml up -d --build
Invoke-RestMethod http://localhost:8000/api/v1/health
```

验证目标：选择正式商品；分开查看正负评价主题和改进需求；查看数量与趋势；下钻原文；当某维度没有合格主题时显示已完成的空结果，而不是fallback主题。
