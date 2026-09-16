# 家电评论洞察平台

本项目从大规模家电评论中提取可追溯的商品洞察，并以商品、主题、情感、趋势、原文证据和产品改进建议的形式提供给 Web 端。截至 2026-09-09，T007–T011 数据链已经全部完成，正式后端和前端已接入。

## 正式数据链

| 阶段 | 状态 | 正式结果 |
|---|---|---|
| T001–T006 | 完成 | Spark 完成原始清洗、关联与 Silver；正式范围为 139 个商品、116,728 条评论 |
| T007 | 完成并冻结 | Qwen3.5-4B 从完整 `text_raw` 提取 350,656 条有效 insight |
| T008 | 完成并冻结 | 315,400 条 `current_product` candidate 经 category 分组、community discovery 和人工审核，形成 4,992 个一级 cluster、887 个 category-level taxonomy theme |
| T009 | 完成并冻结 | 230,278 条 `mapped_by_cluster`，85,122 条 `unmapped_no_cluster`；未聚类 insight 不强制分类 |
| T010 | 完成并冻结 | DuckDB 生成 139 个商品、15,852 条 `product × taxonomy × sentiment` 记录、116,328 条月度趋势和 222,069 条主题评论证据 |
| T011 | 完成并清洗 | 7,747 个负面触发组离线生成建议；纠正 13 个假负面组后，正式保留 7,734 条产品改进建议 |

T010 的 `15,852` 是商品、taxonomy 和 sentiment 的组合记录数，不是 taxonomy 数；taxonomy 仍为 887。Spark 是前期大规模清洗技术，正式 T010 聚合使用 DuckDB。

## 任务与代码导航

| 阶段 | 正式代码 | 主要产物 |
|---|---|---|
| T001–T006 | [`pipelines/foundation/`](pipelines/foundation/) | Silver 数据、139 个商品与 116,728 条评论的正式范围 |
| T007 | [`pipelines/t007/`](pipelines/t007/) | 350,656 条有效 insight |
| T008 | [`pipelines/t008/`](pipelines/t008/) | 4,992 个一级 cluster、887 个 taxonomy theme |
| T009 | [`pipelines/t009/`](pipelines/t009/) | 230,278 条已映射、85,122 条未聚类记录 |
| T010 | [`pipelines/t010/`](pipelines/t010/) | DuckDB 商品主题、趋势与评论证据 Gold |
| T011 | [`pipelines/t011/`](pipelines/t011/) | 7,734 条纠正后的改进建议 |

完整的数据流、代码职责和阶段边界见 [`pipelines/README.md`](pipelines/README.md)。未进入最终方案的实验代码统一位于 [`historical_experiments/`](historical_experiments/)。

## T011 与 polarity correction

T011 的生成单位是 `parent_asin + taxonomy_id`：一个商品的一个负面 taxonomy theme 最多生成一条改进建议。输入来自 T009 的 `mapped_by_cluster` insight，negative 用作触发和主要证据，mixed 只作同组补充证据。生成使用冻结的 `Qwen/Qwen3.5-4B` revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`、NVIDIA/Linux vLLM 和 RTX 4090 离线完成；API 请求不会触发模型。

全量质量检查确认 13 个 `product × taxonomy` 组应为 positive。冻结的 T009/T010 文件没有重跑或改写，后端通过 `t010-polarity-overrides-20260909-v1.json` 应用展示层修正：negative 查询剔除、positive 查询按 positive 处理，T011 不显示对应改进建议。

正式文件：

- `data/gold/t011-final-corrected-20260909-v1.ndjson`
- `data/gold/t010-polarity-overrides-20260909-v1.json`

## 当前 Web 功能

- 从 139 个正式商品中搜索和选择商品；
- 查看正面与负面主题排行、评论数量和占比；
- 默认展示前 8 个主题，并支持“查看全部 / 收起”；
- 查看主题月度趋势和真实评论证据；
- 在负面主题详情抽屉中查看对应 T011 产品改进建议；
- 正面主题不显示改进建议；
- 商品标题使用简化展示，原始完整 title 仍保留在数据中。

## 技术栈与运行边界

- 数据清洗：Spark 4.1.2、Parquet；
- 确定性映射与正式聚合：Python、DuckDB；
- 离线语义生成：Qwen3.5-4B、vLLM、RTX 4090；
- 后端：FastAPI、`GoldInsightsRepository`；
- 前端：Vue 3、TypeScript、Vite、ECharts。

正式应用只读 Gold，不在线调用模型，也不在 API 请求中启动 Spark。

## 正式目录

```text
data/gold/                              冻结数据和正式验证元数据
pipelines/                              T001–T011 按阶段组织的正式数据处理代码
backend_generated/backend/              正式 FastAPI 后端
frontend_story_dashboard/frontend/      正式 Vue 前端
specs/001-merchant-review-insights/     当前 SDD 规格、计划、任务和数据模型
infra/                                  Spark、MongoDB 和历史环境配置
docs/                                   运行证据与验收记录
```

## 一键启动

Windows 环境安装 Python 3.12 和 Node.js 24.x 后，在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

脚本会检查正式 Gold 文件，按需创建后端虚拟环境、安装依赖，随后启动 FastAPI 和 Vue，并打开 `http://127.0.0.1:5173`。按 `Ctrl+C` 可同时停止前后端。首次运行需要联网安装依赖，后续可使用 `-SkipInstall` 跳过依赖检查：

```powershell
.\start.ps1 -SkipInstall
```

正式应用只读取仓库内已经生成的 T010/T011 Gold，不会启动 Spark、DuckDB 聚合作业或模型推理。运行日志写入 `.tmp/runtime/`。

## 启动后端

```powershell
Set-Location D:\CS_Projects\big_data_web\backend_generated
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
```

默认地址：`http://127.0.0.1:8000`。

## 启动前端

```powershell
Set-Location D:\CS_Projects\big_data_web\frontend_story_dashboard\frontend
npm.cmd run dev
```
