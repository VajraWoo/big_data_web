# 第一周环境实施规约与任务

日期：2026-09-03。上位需求与设计：`spec.md`、`plan.md`；本文件只细化其基础设施部分。
不生成或执行完整业务 tasks.md，不越过教师选题确认门禁。

## 需求与验收

作为项目成员，我需要从版本化配置启动相同的数据处理环境，不依赖 Windows 的 Java/Python。

- ENV-01：Compose 启动 Spark 1 Master、2 Worker，二者均注册并参与 Python 作业。
- ENV-02：固定 Spark/Java/Python 镜像与 MongoDB 镜像 digest；不使用 latest。
- ENV-03：计算 100,000 条合成记录的聚合结果，写入并读回 Parquet；这不是 Silver 清洗。
- ENV-04：Driver 与两个 Worker 可读取相同 Bronze 文件，挂载只读；验证两份 SHA-256。
- ENV-05：MongoDB ping、写入、读取通过，重启服务后同一测试文档仍存在。
- ENV-06：所有公开管理 UI 只绑定 127.0.0.1；数据库与 Spark RPC 不发布到主机；
  容器网络与数据卷限于本项目，每个常驻服务有内存/CPU 上限和健康检查。
- ENV-07：记录准确命令、结果、版本、局限；失败检查返回非零状态。

## 实施设计与变更依据

官方 Docker Hub API 查询 4.1.3-scala2.13-java21-python3-ubuntu 返回 404。
改用官方已发布的 4.1.2-scala2.13-java21-python3-ubuntu，固定 manifest digest；
这是版本可获取性修正，不取消任何 Spark/ML/双 Worker 能力。Python 小版本从容器实测。
MongoDB 固定 8.0.29 与 digest。后续 MongoDB Spark Connector 与 NLP/Web 依赖
在其实现阶段单独锁定和测试，本次不声称它们已就绪。

镜像实测补充：官方 Spark 镜像自带 Python 3.10.12，与项目 3.12 要求不符。
使用 `infra/spark/Dockerfile` 在该固定底图上安装 uv 0.12.9 管理的 Python 3.12.12，
Driver 与 Worker 使用同一解释器。基础镜像与 uv 镜像均锁 digest。
Docker internal 网络实测不发布主机 UI 端口；双网卡又导致 Spark RPC 绑定与解析地址
不一致。最终 Master/Worker 只接一个项目 bridge 网络，只发布 127.0.0.1 的管理端口。
MongoDB 单独接 internal database 网络、不发布端口；Driver 可访问两个网络。

来源：https://hub.docker.com/_/spark 、https://hub.docker.com/_/mongo 。

资源：WSL 已由用户设置 memory=20GB；Master 512 MiB，两个 Worker 各 5 GiB/4 CPU，
每 Worker 对 Spark 宣告 4 GiB（给进程开销留余量）；Driver 容器 3 GiB/1 CPU，
JVM heap 2 GiB；MongoDB 3 GiB/1 CPU，WiredTiger cache 1 GiB。
按需启动 Driver，不与模型训练同时运行。最大容器预算合计 16.5 GiB。

数据库不发布端口，使用项目私有 internal 网络；第一周无身份认证，仅用于单机开发，
不得在多人服务器/公网原样部署，应用接入前补充账号、权限和密钥管理。
Spark 管理 UI 只绑定本机，禁止将其开放至局域网/公网。镜像更新需重新验收。
Bronze 只读 bind mount；环境测试输出、MongoDB 数据用不同 named volume。
测试只生成合成数据与明确标记的环境检查文档，不导入真实评论到数据库。

## 执行任务

- [x] E001 在 `infra/tests/test_compose.py` 定义配置验收，并记录配置不存在时的失败。
- [x] E002 在 `infra/compose.yaml` 固定镜像、网络、端口、挂载、资源和健康检查。
- [x] E003 在 `infra/tests/spark_smoke.py`、`infra/tests/mongo_smoke.js` 定义可复跑验收。
- [x] E004 启动服务并执行 ENV-01～06，结果保存至 `docs/runs/environment-2026-09-03.md`。
- [x] E005 在 `infra/README.md` 写启动、验证、停止命令，同步根 README 与版本变更。

顺序：E001 → E002 → E003 → E004 → E005。仅环境就绪不等于小样本清洗或第一周完成。

## 后续连接器增量（2026-09-03）

上述内容为首次基础设施验收历史。连接器增量见connector-environment.md：v2镜像固定
Connector11.1.0/Java Driver5.1.4和5个JAR的SHA-256；实际读写及新镜像回归通过。
为使executor直连MongoDB，MongoDB现同时连接default与internal database网络，无主机端口；
Master/Worker仍单网络，前端仍无法直连。原“MongoDB单独接database”描述不再是最新拓扑。
Web、CPU NLP、Intel XPU及连接器均已有独立验收记录，本机基础环境阶段完成，清洗尚未完成。
