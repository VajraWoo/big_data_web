# Spark—MongoDB 连接器环境验收记录

2026-09-03 本轮从原 Spark 共享输出卷读取并留存已有机器报告，没有重新运行连接器验收。
原路径：`/opt/spark/work-dir/connector/595cace4674f4caeb18b003f02c86d74.json`。
报告副本：[机器证据](evidence/connector-595cace4674f4caeb18b003f02c86d74.json)。

| 项目 | 报告记录 |
|---|---|
| 状态 / 应用 ID | PASS / app-20260903051538-0000 |
| Spark / Python / Java | 4.1.2 / 3.12.12 / 21.0.12 |
| MongoDB / Connector / Java Driver | 8.0.29 / 11.1.0 / 5.1.4 |
| 执行主机 | spark-worker-1、spark-worker-2，同一物理机 |
| 写入 / 重放后行数 | 256 / 256 |
| 写分区 / null 正文 | 8 / 86 |
| round_trip_equal | true |
| BSON 类型 | long、double、bool、array、object、date、string |
| 诊断集合 | environment_checks.connector_595cace4674f4caeb18b003f02c86d74 |

JAR 摘要在上述 JSON 中逐项保留。读取命令：

```powershell
docker compose -f infra/compose.yaml exec -T spark-master cat /opt/spark/work-dir/connector/595cace4674f4caeb18b003f02c86d74.json
```

本轮另做容器轻量存活检查，Spark Master、双 Worker、MongoDB、前后端均 healthy。
本轮未直接查询诊断集合，也未重跑十万条环境计算或 GPU 基准。
Unicode、UTC及嵌套数据检查的细则由既有验收脚本定义，机器报告记录 round_trip_equal 与类型通过。
这只是合成连接器环境验收，不代表真实 Silver、百万级数据库吞吐、认证或生产权限验收。
