# Quickstart Validation Guide

本文件描述实现完成后如何证明四层链路满足规约；它不是安装脚本，也不包含业务实现。

## 1. Prerequisites

- Windows 11，Docker Desktop 使用 WSL 2 backend；Docker/WSL 建议上限 20–22 GiB、
  10 个逻辑 CPU、4–8 GiB swap；D 盘至少保留 50 GiB。
- Git、`uv`、Node.js 24 LTS。Java/Python/Spark/MongoDB 由容器固定，主机已有版本不作为
  可复现环境依据。
- 原始文件位于 `data/bronze/amazon_reviews_2023/appliances/`，并包含 `manifest.json`。
- 不提交原始数据、模型权重、`.env`、数据库卷或全量运行日志。

环境预检（实现基础设施后）：

```powershell
docker version
docker compose version
uv --version
node --version
git status --short
```

Expected: Docker Engine/Compose 可用，Node 为 24.x；若 Docker/WSL 未安装，先完成环境任务，
不要在 Windows 主机上临时拼装不一致的 Spark/MongoDB 服务。

## 2. Verify source integrity

```powershell
uv run python scripts/verify_manifest.py `
  --manifest data/bronze/amazon_reviews_2023/appliances/manifest.json
```

Expected:

- reviews 文件 2,128,605 行、metadata 文件 94,327 行；
- reviews SHA-256 为
  `150F209BEFCEAA6F837ABC997065B2D251034BBBDA19BEBC4AD56DAC779730C2`；
- metadata SHA-256 为
  `5A94CFFB9EC3BE23E42B99643FCAB5F48160B3C7A53835451C4457AADCDF9365`；
- 任一不匹配时非零退出，不生成下游数据。

## 3. Fast tests before full data

```powershell
uv sync --frozen
npm --prefix frontend ci
uv run pytest pipelines/tests backend/tests ml/tests -m "not full_data" -q
npm --prefix frontend run test:unit
docker compose -f infra/compose.yaml --profile test up --build --abort-on-container-exit
```

Expected: 小型 fixture 在 `local[2]` 验证解析失败、空正文、非法评分、元数据关联失败、父子
商品、精确/近重复、缺月、证据不足和批次失败；真实 MongoDB 集成测试验证索引、BSON 和
API 契约。测试不得依赖全量 Bronze 才能运行。

## 4. Start pseudo-distributed Spark and run the full pipeline

```powershell
docker compose -f infra/compose.yaml --profile spark up -d --build
docker compose -f infra/compose.yaml --profile spark run --rm spark-driver `
  python -m pipelines.run --release amazon-reviews-2023-appliances-v1 --stage through-general-gold
```

Expected:

- Spark UI 显示 1 Master、2 Workers 和实际 Stage/Task 分发；
- 报告必须写“单主机伪分布式”，不得写成物理多节点集群；
- 2,128,605 条评论均有 Silver 去向，接受、标记、排除、关联失败相加可核对；
- Silver/通用 Gold 分区 Parquet 生成，`analysis_runs` 记录 application ID、输入 hash、行数、
  规则版本、耗时和资源；
- 作业中不存在百万级无界 `collect()`/`toPandas()`。

运行完成后通过质量门禁：

```powershell
uv run python -m pipelines.validate_run --run-id <RUN_ID> --require-stage general-gold
```

## 5. Calibrate scope and thresholds

```powershell
uv run python -m pipelines.calibrate product-groups --run-id <RUN_ID>
uv run python -m pipelines.calibrate eligibility --run-id <RUN_ID>
uv run python -m pipelines.calibrate priority --run-id <RUN_ID>
uv run python -m pipelines.backtest alerts --run-id <RUN_ID>
```

Expected:

- 商品群选择报告比较全部候选的规模、语义一致性、元数据可识别性和代表性；至少两个群组
  从 `candidate` 转为 `selected`，未选群组有排除理由；
- 每类正式准入参数至少 3 个候选，报告覆盖量、区间/稳定性、误报或回测指标和预声明选择
  规则；50/10 只有在胜出后才能成为正式值；
- 预警注入 5/10/15 个百分点恶化并报告召回、稳定对照误报和延迟。

## 6. Train and evaluate NLP

避免与全量 Spark 同时争抢内存：

```powershell
docker compose -f infra/compose.yaml --profile spark down
docker compose -f infra/compose.yaml --profile ml run --rm ml-trainer `
  python -m ml.training.run --config ml/configs/aspect_sentiment.yaml
docker compose -f infra/compose.yaml --profile ml run --rm ml-trainer `
  python -m ml.training.run --config ml/configs/explicit_demand.yaml
uv run python -m ml.evaluation.compare --include-baseline --run-id <RUN_ID>
```

Expected:

- 切分按父商品和重复簇隔离，独立测试集不参与弱监督训练；
- 属性倾向 Macro-F1 ≥ 0.75；明确需求 precision ≥ 0.75、recall ≥ 0.60；
- 同时报告 Spark 简单基线、错误类型、分层结果、吞吐和资源；
- OpenVINO/Intel GPU/INT8 仅在 10,000 句基准更快且精度损失在批准界限内时启用；
- 隐含需求若实现，始终以 `implicit_experimental` 单独评价。

模型通过后生成精细 Gold：

```powershell
docker compose -f infra/compose.yaml --profile spark up -d
docker compose -f infra/compose.yaml --profile spark run --rm spark-driver `
  python -m pipelines.run --run-id <RUN_ID> --stage fine-gold
```

## 7. Publish Gold and start the Web app

```powershell
docker compose -f infra/compose.yaml --profile app up -d --build
uv run python -m pipelines.publish --run-id <RUN_ID> --target mongodb
Invoke-RestMethod http://localhost:8000/api/v1/health
```

Expected: 只有完整验证的 run 被原子切换为 active；API 返回数据批次，不在请求中触发 Spark。
接口必须与 [OpenAPI contract](contracts/openapi.yaml) 一致。

打开 `http://localhost:5173`，按以下路径验收：

1. 选择公开品牌/店铺组合，看到“非所有权证明”的声明和组合概况；
2. 下钻商品群与父商品，查看评论量、平均评分、低评分率、正文可用率；
3. 打开问题排名，核对原始计数、区间、分项、参数版本和至少 3 条支持/反例；
4. 查看明确需求主题；实验性隐含需求位于独立区域且不进入正式排名；
5. 查看趋势和预警的基线、近期窗口、样本量、最小效应与触发原因；
6. 选择数据不足商品，页面明确显示 `insufficient`，不出现伪精确排名或空图；
7. 从任一结论跳转到批次、模型评价和原始证据。

## 8. Contract, E2E, performance and audit acceptance

```powershell
uv run pytest backend/tests/contract backend/tests/integration -q
npm --prefix frontend run test:e2e -- --project=chromium
uv run python scripts/check_openapi.py specs/001-merchant-review-insights/contracts/openapi.yaml
uv run python scripts/benchmark_api.py --base-url http://localhost:8000 --percentile 95
uv run python scripts/audit_trace.py --sample-conclusions 20
```

Expected:

- 四个核心操作 p95 < 3 秒；
- 正式问题、需求、预警 100% 含样本量、时间、计算依据、区间/置信度和至少 3 条证据；
- 抽样结论均可追到 active run、数据发布、规则/参数/模型版本和 Silver `review_id`；
- 5 名模拟用户可按 SC-006 执行限时可用性测试；
- 全量运行日志、模型卡、校准报告、提示词和已知限制进入最终材料索引。

## 9. Shutdown

```powershell
docker compose -f infra/compose.yaml --profile app --profile spark --profile ml --profile test down
```

不附带 `-v`：MongoDB named volume 是可恢复测试数据。只有明确决定销毁本地 Gold 后才单独
执行卷删除，并先记录将删除的确切卷名。
