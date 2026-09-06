# 文本画像环境安装与运行

在项目根目录使用 PowerShell 执行。依赖装在 Docker 的 Spark 镜像内；主机需要已经安装的
Docker Desktop。模型下载还需要 Windows 自带的 curl.exe。

1. 下载并验证语言模型：`powershell -ExecutionPolicy Bypass -File pipelines/download_language_model.ps1`
2. 构建运行环境：`docker compose -f infra/compose.yaml build spark-master`
   同时将已锁定 MiniLM 的 `tokenizer.json` 放入 `data/models/minilm/tokenizer.json`。
   本机已从 `tmp/xpu/models/minilm/tokenizer.json` 复用，SHA-256 为
   `be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037`。
3. 样本验证：`powershell -ExecutionPolicy Bypass -File pipelines/run_text_profile.ps1 -Mode sample`
4. 全量运行：`powershell -ExecutionPolicy Bypass -File pipelines/run_text_profile.ps1 -Mode full`

模型为 fastText 官方 `lid.176.bin`，131,266,198 字节，许可 CC-BY-SA-3.0；来源、大小与
SHA-256 保存于 `pipelines/language-model-lock.json`。下载器验证通过后复用已有文件。
模型存于忽略目录 `data/models/fasttext/`，以只读方式挂载到 Spark 节点。

任务读取已有全量 Silver 批次，写入独立 `data/silver/text-profile-*` 目录。`report.json`
保存语言分布、英文长度分位数、月度统计和候选阈值覆盖；`product_coverage` 保存商品首末
月份、活跃月份及最长内部断档。统计单词为正则口径，句子为标点启发式，需注意缩写和小数。

当前 0.8 置信度和 5 个字母仅是画像候选，输出资格不是正式模型准入承诺。报告明确保留
待人工校准状态。当前同时统计已缓存 MiniLM tokenizer 的全量 token 长度；其他候选模型
的 tokenizer 比较和正式 NLP 选型仍为后续步骤。
