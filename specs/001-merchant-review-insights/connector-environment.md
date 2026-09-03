# 第一周 Spark—MongoDB 连接器验收

2026-09-03，用户授权补齐最后的数据接入环境环节；不实施真实评论清洗或业务Gold。
沿用Spark4.1.2/Scala2.13、Java21、MongoDB8.0.29。
MongoDB官方兼容表确认Connector11.1.0支持Spark4.0+及MongoDB4.2+。

## 验收与任务

- [x] C001：先写配置/真实读写测试，记录未安装连接器时的失败。
- [x] C002：Connector11.1.0及MongoDB Java Driver5.1.4固定版本和SHA-256，烘焙进
  Driver/Worker共用镜像，运行不依赖Maven在线下载。
- [x] C003：Driver及两个Worker均能连接MongoDB，数据库不发布主机端口；前端不直接访问数据库。
- [x] C004：256条合成记录分区写入独立诊断集合，Spark读回核对数值、Unicode、数组、
  嵌套对象、UTC毫秒时间和null；Java Mongo客户端独立检查BSON类型和数量。
- [x] C005：按_id重放同一批，数量不翻倍；报告包含版本、应用ID、参与Worker、集合和检查结果。
- [x] C006：回归原Spark计算/Parquet和Web健康检查，更新环境说明，区分环境完成与第一周完成。

实际证据：docs/runs/connector-environment-2026-09-03.md；连接器PASS，配置11项通过，
新镜像Spark10万合成记录/Parquet回归PASS，后端3项通过，Web真实数据库健康检查正常。

## 实施边界

MongoDB增加项目default网络连接，使真实executor可直连；保留database网络给后端。
Worker仍只接一张default网络，避免曾出现的多网卡Spark RPC歧义。MongoDB无主机端口，
但不再宣称仅在internal database网络可达：项目Spark网络成员也可以访问它。
这仍为无认证的本机开发配置，不能原样用于多人服务器/公网。

更新同一个Spark派生镜像至v2，基础镜像及Python不变；增加5个JAR（connector、sync、core、
bson、bson-record-codec），不安装可选AWS/Kotlin等依赖。源码和配置入Git，二进制不入Git。
镜像构建时通过HTTPS从Maven Central取包并校验SHA-256；构建前下载副本已核对Central SHA1，
其SHA-256由本地计算锁定，不能冒称官方提供了SHA-256文件。

每次生成environment_checks.connector_<随机UUID>集合，保留诊断证据；只append并按_id
replace/upsert本次合成数据，不drop/overwrite任何集合。实际评论、Bronze和原诊断数据不改动。
暂不测试身份认证、生产权限、CDC/流式处理或百万级MongoDB吞吐。

依据：
- https://www.mongodb.com/docs/spark-connector/current/
- https://www.mongodb.com/docs/spark-connector/current/batch-mode/batch-write-config/
- https://repo.maven.apache.org/maven2/org/mongodb/spark/mongo-spark-connector_2.13/11.1.0/mongo-spark-connector_2.13-11.1.0.pom
