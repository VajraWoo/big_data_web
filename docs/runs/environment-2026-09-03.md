# 第一周基础设施验收 — 2026-09-03

结论：本轮 ENV-01～07 通过。范围仅限 Spark/MongoDB 基础设施，不代表 Silver、Web、
NLP、Gold 或第一周全部完成。所有结果来自本轮真实命令输出；失败与修正如实保留。

## 实测环境

| 项目 | 实测值 |
|---|---|
| Docker Engine / Compose | 29.7.2 / 5.5.0 |
| WSL memory 配置 / Docker 可见字节 | 20GB / 20,971,667,456 |
| 物理机 | Intel Core Ultra 5 225H，约32GB，14逻辑CPU |
| Spark | 4.1.2，单物理机 Standalone，1 Master + 2 Worker |
| Python / Java | 3.12.12 / 21.0.12 |
| MongoDB | 8.0.29 |
| Spark 构建输出 config digest | sha256:da1f5c8cbcd2be9c2f7afc5aa146bafae8c6532fd8c0776140f9e066e276838a |

官方镜像 digest：

- Spark：`sha256:8924a12c1365c5d2e02cfac93954a51a9f55aeb5ef4632a39331692fc1164422`
- uv：`sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff`
- MongoDB：`sha256:02a0cc7939f5ed38f30f9bc714ef5f682d49baf9350c54acf302ce833087fe8a`

## 验收命令与结果

均在仓库根目录、Docker Desktop 运行时执行。旧代理终端通过仅本进程 PATH 指向已安装
Docker bin，未修改 Windows 全局 PATH，也未改主机 Java/Python。

1. `python -m unittest discover -s infra/tests -v`：5 项通过。
   检查镜像锁定、只读 Bronze、单网卡 Spark、隔离数据库、localhost 端口和资源上限。
2. `docker compose -f infra/compose.yaml build spark-master`：成功构建统一项目镜像。
3. `docker compose -f infra/compose.yaml up -d --wait --wait-timeout 180`：4 个服务 healthy。
4. `docker compose -f infra/compose.yaml --profile tools run --rm spark-driver`：退出码0，PASS。
5. 数据库写入命令：
   `docker compose -f infra/compose.yaml exec -T -e CHECK_MODE=write mongodb mongosh --quiet /checks/mongo_smoke.js`：PASS。
6. `docker compose -f infra/compose.yaml restart mongodb` 后等待健康，再执行：
   `docker compose -f infra/compose.yaml exec -T mongodb mongosh --quiet /checks/mongo_smoke.js`：PASS。
   后续网络修正中又执行不带 -v 的 down/up 重建容器，读取相同诊断文档仍 PASS。
7. `Invoke-RestMethod http://localhost:8080/json/`：ALIVE，aliveworkers=2，cores=8。
   三个管理页面 localhost:8080、8081、8082 均 HTTP200。
8. `docker inspect big-data-web-spark-master-1 --format '{{json .Mounts}}'`：Bronze 挂载 RW=false。

Spark 输出摘要（机器原始字段值）：

```json
{
  "status": "PASS",
  "application_id": "app-20260903032245-0000",
  "spark": "4.1.2",
  "python": "3.12.12",
  "java": "21.0.12",
  "worker_hosts": ["spark-worker-1", "spark-worker-2"],
  "executor_hosts": ["spark-worker-1", "spark-worker-2"],
  "rows": 100000,
  "partitions": 16,
  "sum": 4999950000,
  "parquet_path": "/opt/spark/work-dir/environment/796c876c064b4f1ab5324156134cdd34"
}
```

作业验证内容：每个 Python executor 分区读取两份 Bronze 的首条 JSON；Driver 流式验证
两份完整文件 SHA-256；16 个分区分别汇总后只 collect 16 条分区摘要，不 collect 全量明细。
合成 id=0～99,999 的数量与总和在 Parquet 写入前后均一致。两份 Bronze hash 与 manifest 一致：

- reviews：`150f209befceaa6f837abc997065b2d251034bbbda19bebc4ad56dac779730c2`
- metadata：`5a94cffb9ec3be23e42b99643fcab5f48160b3c7a53835451c4457aadcdf9365`

执行完后的瞬时空闲内存（不是峰值/性能基准）：Master153.1MiB，Worker1 192MiB，
Worker2 202MiB，MongoDB191.4MiB。Driver 已随 --rm 退出。常驻4容器保留运行。

## 失败与修正记录

- 最初没有 Compose 文件：配置验收失败，之后创建配置并通过，未伪造测试先行证据。
- 规划4.1.3对应官方镜像标签 API 404：改为同系列官方4.1.2并锁digest，同步设计。
- Windows端 `docker manifest inspect` 访问 registry 超时，但 daemon 的 pull 成功；
  未据此更改系统代理或镜像源。
- 官方 Spark 底图 Python3.10.12，`hashlib.file_digest` 缺失使验收失败；
  通过固定 uv 与 Python3.12.12 的 Dockerfile解决，并实测 Driver/Executor 全链路通过。
- internal-only 网络不发布 UI；接双网络后 Master 监听与 DNS 地址不一致，
  Worker connection refused，aliveworkers=0。回归检查先失败，随后将 Master/Worker
  统一单网络、数据库另隔离；最终两个执行器真实参与任务、UI 可达。
- Spark 提示 native-hadoop library 不存在并使用 Java fallback；本轮 Parquet 实测通过，
  不将其包装为已安装完整 Hadoop/HDFS。

## 边界与后续

- 只验证环境；100,000条为合成验收负载，不是下载的真实评论子集。
- 真实数据小样本清洗与正式 Silver 还未实施。
- MongoDB 此阶段没有账号，不发布主机端口，限本机开发；应用接入前要补认证和最小权限。
- 没有启动全量Spark、训练深度模型或搭建Web；相关依赖和Connector尚未安装/验收。
- 未修改原始数据、未删除数据卷、未推送本轮变更到GitHub。
- 环境规约与操作说明已新增；此前完整提示词历史仍待整理，不以本轮记录替代。
