# 第一周 Web 环境增量规约

2026-09-03。细化 spec.md/plan.md 的 Web 环境部分，不启动商家业务开发。
用户原文：“那现在先搭建web环境吧。”

**文档性质**：第一周 Web 环境验收历史记录，不是当前产品功能规格。其后正式 FastAPI
后端和 Vue 前端已接入 T010/T011 Gold；现行接口和页面要求以 `spec.md`、`plan.md`、
`data-model.md` 和 `contracts/openapi.yaml` 为准。

## 需求与验收

- WEB-ENV-01：Python3.12、FastAPI、PyMongo 依赖锁定，后端可启动。
- WEB-ENV-02：`GET /api/v1/health` 遵循既有 Health 契约：正常200，数据库不可达503；
  不向客户端暴露连接串/异常细节。active_run=null，明确尚无发布的分析批次。
- WEB-ENV-03：Vue/TypeScript/Vite/ECharts依赖锁定，开发页可访问，类型检查和生产构建通过。
- WEB-ENV-04：检查页实际请求后端，显示连接成功、数据库异常、请求失败，并支持重试；
  明确是环境检查而非商家分析界面，不生成伪业务图表。
- WEB-ENV-05：真实浏览器验证前端→代理→FastAPI→MongoDB；验证断连与恢复。
- WEB-ENV-06：服务只发布localhost端口，源码可热更新，停止Web不影响数据库持久化。

## 设计

第一周旧 `backend/` 使用 pyproject.toml + uv.lock；该实现已退出正式代码。
FastAPI0.141.1、PyMongo4.17.0、Uvicorn0.52.4；pytest9.1.1、httpx0.28.1。
AsyncMongoClient 在应用 lifespan 创建并关闭；健康检查仅发ping，不读写评论或Gold。
测试以依赖替换覆盖异常；另对真实数据库做HTTP联通测试。暂不提供业务接口。

第一周旧 `frontend/` 使用 package-lock.json。Node24.12.0、Vue3.5.38、Vite8.2.2、ECharts6.1.0、
TypeScript5.9.3；Vitest和Playwright验证。开发/预览的 /api 请求代理至后端，无宽泛CORS。
Docker 前端是开发服务器，不宣称生产部署；生产 bundle 在本轮完成构建与预览验证。

原 `infra/compose.web.yaml` 已归档至 `historical_experiments/first_week_web_environment/`，当时的 web profile 只增加旧 backend/frontend。
backend接web与internal database网络，frontend只接web；端口127.0.0.1:8000/5173。
后端512MiB、前端1GiB，均1CPU。保持原Spark服务配置，不启动其作业。
延续本机开发数据库无账号且不发布端口的边界：本轮只做健康ping；正式业务数据接入前
必须补认证和最小权限，不能把本轮检查页部署到公网。

## 任务与证据

- [x] W001 创建依赖清单与测试，取得未实现时的失败证据。
- [x] W002 实现backend/app/main.py与frontend/src/App.vue的环境检查功能。
- [x] W003 锁依赖、配置镜像、Compose和热更新；运行单元测试、类型检查及构建。
- [x] W004 实测浏览器、真实数据库连通和断连恢复，记录docs/runs/web-environment-2026-09-03.md。
- [x] W005 更新infra/README.md、根README和第一周剩余清单。

在当次 Web 环境验收结束时，NLP 环境和全量基础清洗仍属后续工作；两者后来均已完成，
并继续完成了 T007–T011 与正式 Web 集成。
