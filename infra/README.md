# 第一周数据环境

这是 Spark/MongoDB 的单机开发环境说明，同时提供已实现的基础 Silver 清洗入口；商家 Web 业务尚未实现。
验收要求见 `specs/001-merchant-review-insights/environment.md`；实际结果见 `docs/runs/`。

## 前提

- Docker Desktop 已启动，使用 Linux containers / WSL2。
- 当前开发机 32GB 内存，WSL 配置 memory=20GB；D 盘预留至少 50GiB。
- 原始文件按 manifest 放在 `data/bronze/amazon_reviews_2023/appliances/`。
- 构建时访问 Docker Hub、GHCR、GitHub Python 分发和Maven Central；运行验收不需公网下载。
- 命令均从仓库根目录运行。普通 PowerShell 即可，不需要管理员权限。

## 启动

```powershell
docker compose -f infra/compose.yaml build spark-master
docker compose -f infra/compose.yaml up -d --wait --wait-timeout 180
docker compose -f infra/compose.yaml ps
```

三个 Spark 常驻服务和按需Driver使用同一项目v2镜像。底图固定 Spark 4.1.2、Java21；Dockerfile
固定 uv 0.12.9 安装 Python3.12.12，不依赖主机 Python/Java。所有 FROM 均带 digest。
基础服务期望显示四个 healthy 容器，不会自动启动 Driver、训练模型或清洗评论。

本机 UI：Master http://localhost:8080 ，Worker1 http://localhost:8081 ，
Worker2 http://localhost:8082 。它们是 Spark 管理页面，不是商家 Web 应用。

## 可重复验收

```powershell
# 主机静态配置验收仅需 Python 标准库，不需要安装 pytest/PySpark。
python -m unittest discover -s infra/tests -v

# 集群、Python/Java版本、原始文件 hash、两个 Worker 实际计算、Parquet 回读。
docker compose -f infra/compose.yaml --profile tools run --rm spark-driver

# 数据库写入，然后重启验证持久化。
docker compose -f infra/compose.yaml exec -T -e CHECK_MODE=write mongodb mongosh --quiet /checks/mongo_smoke.js
docker compose -f infra/compose.yaml restart mongodb
docker compose -f infra/compose.yaml up -d --wait --wait-timeout 60 mongodb
docker compose -f infra/compose.yaml exec -T mongodb mongosh --quiet /checks/mongo_smoke.js
```

Spark 最终输出 `ENVIRONMENT_RESULT=..."status": "PASS"...`，记录两台执行器主机名、
application ID、Python/Java/Spark 版本和十万条合成数据总和 4,999,950,000。
100,000 是小型环境负载，不是数据规模结论；此测试没有进行真实评论清洗。
每次测试输出到 `big-data-web_spark-check-output` 卷下不同 UUID 路径，不覆盖此前结果。
MongoDB 的 `environment_checks.checks` 只保存一个有明确标记的诊断文档，不含真实评论。

资源：Master0.5GiB、两个 Worker 各5GiB、Driver3GiB、MongoDB3GiB，总上限16.5GiB；
常驻 CPU 配额9.5，按需 Driver1。Worker 宣告4GiB，Executor heap3GiB，保留进程开销。
这是上限而非启动即占满。CPU压力高时先停止空闲 Worker，不与模型训练同时运行。

## 安全边界与数据位置

- 原始数据只读挂载，测试验证 hash；本轮不移动或改写原始 gzip。
- MongoDB 用 named volume 持久化，不映射到 Windows NTFS 数据目录。
- 数据库无主机端口，仅连接本项目database和default网络；本阶段未配置账号。
- Spark Master/Worker 只接一个项目 bridge 网络，避免多网卡地址歧义；UI 只发布到
  127.0.0.1。MongoDB保留internal database网络供后端访问，另接default网络供Worker
  直接读写；Driver可访问两张网络。前端仅接web网络，不能直连数据库。
- 不得将这套无认证配置直接用于共享服务器/公网。应用接入前再补最小权限账号与密钥。
- 不需要额外装 VMware、Windows MongoDB、Windows Spark 或改系统 Java。

## 停止与排查

```powershell
docker compose -f infra/compose.yaml logs --tail 100
docker compose -f infra/compose.yaml down
```

`down` 停止并移除本项目容器/网络，保留 MongoDB 与测试输出卷；不要加 `-v`。
原始文件不会被删除。不要为排查本项目运行全局 Docker prune。

若旧终端找不到 docker，先重新打开 PowerShell。当前电脑安装于
`C:\Users\31407\AppData\Local\Programs\DockerDesktop\resources\bin`；该路径是本机信息，
不是队友必须使用的安装位置。

## Web 环境（第一周已配置）

在仓库根目录执行，普通PowerShell即可：

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web up -d --build --wait --wait-timeout 120 backend frontend
```

访问 http://localhost:5173 查看环境检查页；http://localhost:8000/api/v1/health 是真实
数据库健康检查，http://localhost:8000/docs 是接口文档（文档UI的第三方静态资源需要网络）。
前端开发服务器代理 /api 至后端，浏览器不直接访问数据库，不配置宽泛跨域。
只实现健康检查，不实现商家业务。数据/接口异常不显示虚假的连接正常。

后端使用backend/uv.lock，前端使用frontend/package-lock.json；镜像固定Python3.12.12
与Node24.12.0。源码挂载支持开发更新；改依赖、配置或Dockerfile后重新构建。
日常不必在Windows另装后端依赖。早期生成的backend/.venv是Linux测试环境，不在Windows
直接使用，也不提交Git；正式运行使用容器自己的/app/.venv。

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web exec -T backend pytest -q -o cache_dir=/tmp/pytest-cache
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web exec -T frontend npm run test:unit
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web exec -T frontend npm run build
```

浏览器验收在frontend目录运行 `npm ci`、`npx playwright install chromium`、
`npm run test:e2e`。注意：其中一个用例会短暂停止MongoDB再恢复，不能与数据作业同时执行。
生产构建验证不等于生产部署；Vite开发/预览服务器都不能作为正式公网服务。

只停止Web、保留Spark和数据库：

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web stop frontend backend
```

若要关闭全部服务，使用完整配置运行 `docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web down`，
仍不加-v。不要在Web运行时只用基础配置down，以免遗漏服务。

## NLP 环境（第一周已配置）

独立按需容器，不随Web或Spark常驻启动。模型已下载的本机可直接运行：

```powershell
docker compose -f infra/compose.nlp.yaml --profile ml run --rm nlp-check
```

验收容器禁用网络，模型只读，完成后自动退出。CPU推理、一次反向参数更新、
MiniLM句向量和文件校验已通过。首次构建与下载步骤见 [NLP说明](../ml/README.md)，
实测结果见 [验收记录](../docs/runs/nlp-environment-2026-09-03.md)。
容器上限12GiB/8CPU，不与Spark全量作业同时运行；这是环境检查而非正式训练。

## Spark—MongoDB连接器（第一周已配置）

v2 Spark镜像包含Connector11.1.0（Scala2.13）和Java Driver5.1.4及其必需依赖，
每个JAR的SHA-256固定于infra/spark/connector-jars.sha256，构建和验收均检查。
无需额外安装Windows版Spark/MongoDB，不需要在每次提交任务时用--packages联网下载。

仓库根目录运行（Web配置也包含在内，避免已有Web服务被提示为orphan；不删除任何服务）：

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web up -d --wait --wait-timeout 180
docker compose -f infra/compose.yaml -f infra/compose.web.yaml -f infra/compose.connector.yaml --profile web --profile tools run --rm spark-driver
```

首次使用或镜像改变前，先运行本页开头的`build spark-master`。
验收输出`CONNECTOR_RESULT=..."status":"PASS"...`（JSON可能带空格）。
256条合成数据、8个写分区，检查逐字段读回相等、UTC毫秒时间、BSON类型、86条null正文，
再按相同_id重放，确认总数仍为256。两个Worker均独立验证到MongoDB的网络连接。

每次保留environment_checks.connector_<UUID>诊断集合和
spark-check-output卷connector/<UUID>.json；不drop、不overwrite，不导入真实评论。
读回采用明确schema和SinglePartitionPartitioner，仅用于小型验收，不作为全量读取的性能配置。
出现CaseInsensitiveStringMap重复键警告时，本次数据检查仍全部通过，详见验收记录；
这不是认证、生产权限、CDC或百万级吞吐验收。

## 第一周仍需完成

CPU NLP环境最小验证已完成；独立Windows XPU环境在用户更新驱动至32.0.101.8991后，
线性层及两模型验收通过，见../ml/xpu/README.md；OpenVINO未配置，不影响CPU/XPU环境。
真实评论小样本与同管道全量基础清洗已完成，见[Silver记录](../docs/runs/silver-cleaning-2026-09-03.md)。
语言、NLP适用性及高级质量算法仍待评估。
MongoDB Spark Connector基础接入已通过验收，当前计划内的本机基础环境已就绪。
业务Gold、正式模型训练和商家页面
属于后续功能开发，不在已完成范围内。

## 第一周 Silver 清洗入口

既有镜像无需重建。仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File pipelines/run_silver.ps1 -Mode sample
powershell -ExecutionPolicy Bypass -File pipelines/run_silver.ps1 -Mode full
```

入口使用 compose.silver.yaml 为全部 Spark 节点增加一致的 `/pipelines:ro` 和 `/data/silver`
挂载，Bronze 仍只读，资源配置不变。第一次可能为增加挂载重建容器，不重建镜像、不删除卷。
每次自动生成独立 processing_run_id；已存在的批次拒绝覆盖。成功状态为 passed_basic_silver，
要同时检查 quality.json 的数量去向和实际 Spark 证据，不把退出码当成全部验收。
Silver 数据、编号中间文件、Parquet 和事件日志位于 data/silver/（不提交 Git）；小型证据在 docs/runs/evidence/。

抽样使用固定种子20260903、跨完整文件的无放回行号抽样，不是文件头10,000条。
样本和全量使用同一清洗代码；语言、近似重复、评分文本一致性和正式准入阈值仍待评估。
完整说明见 [增量规约](../specs/001-merchant-review-insights/silver-cleaning.md)。

仅当规则/实现变化或需要核实可复现性时，比较已有两批结果；不需要日常反复重跑：

```powershell
powershell -ExecutionPolicy Bypass -File pipelines/run_silver.ps1 -Mode replay -LeftRunId <第一批ID> -RightRunId <第二批ID> -SkipStart
```

样本与全量比较需加 `-Subset`，只比较规范化行内容；重复分组大小取决于数据总体，不能要求
样本和全量的最终重复计数相同。输出单独的回放验收 JSON，不修改既有批次。
