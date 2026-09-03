# 环境配置说明

## 1. 环境用来做什么

项目环境分为数据处理、数据存储、后端、前端和文本分析五部分。

| 部分 | 组件 | 作用 |
|---|---|---|
| 数据处理 | Spark 4.1.2、Python 3.12.12、Java 21 | 清洗 213 万条评论，生成统计与分析结果 |
| 数据存储 | Parquet、MongoDB 8.0.29 | Parquet 保存批量数据，MongoDB 为页面提供查询数据 |
| 后端 | FastAPI、PyMongo | 接收页面请求并查询 MongoDB |
| 前端 | Vue、Vite、ECharts | 展示商品问题、需求、趋势和评论原文 |
| 文本分析 | PyTorch、Transformers、sentence-transformers | 识别评论主题、需求和语义相似内容 |

Docker Desktop 和 WSL 2 负责运行 Linux 容器。项目依赖写在 Dockerfile、Compose 文件和锁文件中，其他成员不需要分别安装 Spark、MongoDB、Java 和各类 Python 包。

## 2. Spark 为什么有两个 Worker

Spark 环境包含一个 Master、两个 Worker 和一个按需启动的 Driver。

```text
Driver 提交任务
       ↓
Master 分配计算
   ↙       ↘
Worker 1   Worker 2
```

- Driver 读取清洗程序并提交作业。
- Master 负责调度任务。
- 两个 Worker 分担数据分区的计算。
- 这四个进程运行在同一台电脑的不同容器中。

Spark 管理页面：

- Master：http://localhost:8080
- Worker 1：http://localhost:8081
- Worker 2：http://localhost:8082

## 3. 数据保存在哪里

```text
data/bronze  →  data/silver  →  data/gold  →  MongoDB  →  FastAPI  →  Vue
原始数据        清洗明细        分析结果       页面查询      接口       展示
```

- `data/bronze/` 保存下载的原始 gzip 文件和来源清单。
- `data/silver/` 保存字段统一、质量标记和商品关联后的 Parquet。
- `data/gold/` 用于保存问题、需求和趋势等分析结果。
- MongoDB 保存前端需要快速查询的 Gold 结果和评论证据索引。

Bronze、Silver 和 Gold 是数据处理阶段的名称。Parquet 适合 Spark 批量读写，MongoDB 适合后端按商品、时间和问题查询。

## 4. 第一次启动

前提：Docker Desktop 已启动，并使用 WSL 2 Linux containers。命令在项目根目录执行。

构建 Spark 镜像：

```powershell
docker compose -f infra/compose.yaml build spark-master
```

启动 Spark 和 MongoDB：

```powershell
docker compose -f infra/compose.yaml up -d --wait --wait-timeout 180
docker compose -f infra/compose.yaml ps
```

`ps` 应显示 MongoDB、Spark Master 和两个 Spark Worker。

启动后端和前端：

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web up -d --build --wait --wait-timeout 120 backend frontend
```

打开以下地址：

- 前端：http://localhost:5173
- 后端健康接口：http://localhost:8000/api/v1/health
- 接口文档：http://localhost:8000/docs

## 5. 运行数据清洗

运行 10,000 条固定随机样本：

```powershell
powershell -ExecutionPolicy Bypass -File pipelines/run_silver.ps1 -Mode sample
```

运行全量清洗：

```powershell
powershell -ExecutionPolicy Bypass -File pipelines/run_silver.ps1 -Mode full
```

脚本依次完成原始文件校验、稳定行号登记、字段解析、UTC 时间转换、缺失与重复标记、商品元数据关联和 Silver Parquet 写入。每次运行使用独立的 `processing_run_id`，质量统计写入对应批次目录。

本次全量批次位于：

```text
data/silver/silver-full-20260903T154909-6c310067/
```

## 6. 运行 NLP 环境

CPU 环境通过单独的按需容器运行：

```powershell
docker compose -f infra/compose.nlp.yaml --profile ml run --rm nlp-check
```

Intel GPU 环境位于 `ml/xpu/`，用于本机模型推理和训练测试。使用方法见 [ml/xpu/README.md](../ml/xpu/README.md)。Spark 全量作业和模型训练错开运行，避免同时占用大量内存。

## 7. 停止环境

停止后端和前端：

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web stop frontend backend
```

停止全部基础服务：

```powershell
docker compose -f infra/compose.yaml down
```

MongoDB 数据和 Spark 检查结果保存在 Docker volumes 中，执行 `down` 后仍会保留。

## 8. 项目分工

项目按四块推进：

| 分工 | 工作内容 |
|---|---|
| 数据平台与存储 | Spark 清洗、Parquet 分层、MongoDB 数据组织和运行记录 |
| NLP 与数据挖掘 | 评论主题、质量问题、需求识别和趋势计算 |
| 后端 API | FastAPI 接口、查询逻辑和结果追踪 |
| 前端与可视化 | Vue 页面、ECharts 图表、商品下钻和评论证据展示 |

四块初版分工已经确定。
