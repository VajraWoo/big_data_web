# 第一周 Web 环境验收 — 2026-09-03

结论：Web基础环境已通过本轮验收；不是商家业务系统，也不是第一周全部完成。
规约：`specs/001-merchant-review-insights/web-environment.md`。

## 版本与运行边界

- 后端：Python3.12.12、FastAPI0.141.1、PyMongo4.17.0、Uvicorn0.52.4；
  pyproject.toml/uv.lock 固定直接和传递依赖。
- 前端：Node24.12.0、Vue3.5.38、Vite8.2.2、ECharts6.1.0、TypeScript5.9.3；
  package-lock.json 固定依赖，Windows和Linux容器均安装、测试、构建成功。
- 测试：pytest9.1.1、httpx0.28.1、Vitest4.1.11、Vue Test Utils2.4.6、jsdom29.0.1、
  Playwright1.62.0 / Chromium151.0.7922.34。
- backend/frontend均非root运行，主机只发布127.0.0.1:8000/5173。
- MongoDB无主机端口，frontend不能直接接入database网络；后端仅调用ping，不读取评论。
- 后端512MiB、前端1GiB；包含按需Spark Driver的所有容器内存上限合计18GiB。
  这是配额上限，不是常驻消耗或性能基准；不与NLP训练同时满载运行。

## 测试先行与结果

实现前：后端 pytest 因 app 模块不存在失败；前端 Vitest 因 App.vue 不存在失败。
实现后：

| 检查 | 本轮实测 |
|---|---|
| `python -m unittest discover -s infra/tests -v` | 7通过（含原5项基础设施检查） |
| 后端容器 `pytest -q -o cache_dir=/tmp/pytest-cache` | 3通过 |
| 前端 `npm run test:unit` | Windows与Linux容器均3通过 |
| 前端 `npm run build` | Windows与Docker构建均通过，包含vue-tsc类型检查 |
| `npm run test:e2e` | 3通过，13.4秒 |
| 生产bundle预览浏览器验证 | 2通过，2.7秒 |
| `npm audit --json` | 执行时生产+开发依赖报告0条漏洞，不代表永久安全保证 |

真实浏览器测试包括：

1. 浏览器→Vite /api代理→FastAPI→真实MongoDB，返回200：
   `{"service":"ok","mongodb":"ok","active_run":null}`。
2. 暂停本项目MongoDB，后端返回503与`mongodb=unavailable`，页面显示数据库连接异常；
   finally恢复MongoDB，点击重试后显示连接正常。未删除数据或数据卷。
3. 单独模拟网络请求失败，页面显示无法连接后端，恢复请求并重试成功。
4. 桌面与390px窄屏截图已查看，无横向溢出；正常流程无浏览器pageerror。
5. 生产构建在4173临时预览，连接与请求失败恢复两项通过；预览进程已自动关闭。

## 准确命令

仓库根目录，Docker Desktop运行中：

```powershell
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web build backend frontend
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web up -d --wait --wait-timeout 120 backend frontend
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web exec -T backend pytest -q -o cache_dir=/tmp/pytest-cache
docker compose -f infra/compose.yaml -f infra/compose.web.yaml --profile web exec -T frontend npm run test:unit
python -m unittest discover -s infra/tests -v
```

frontend目录中：

```powershell
npm ci
npm run test:unit
npm run build
npx playwright install chromium
npm run test:e2e
```

生产预览验证在单独PowerShell进程设置 `WEB_PREVIEW=1` 与
`WEB_BASE_URL=http://127.0.0.1:4173`，运行 `npm run test:e2e -- environment.spec.ts`。
e2e数据库异常用例会短暂停止本项目MongoDB，只有没有其他作业使用它时才运行。

## 修正及已知提醒

- jsdom30.0.1和Vue Test Utils2.5.0的部分传递依赖要求Node24.15+；
  固定jsdom29.0.1、Vue Test Utils2.4.6后，无engine不兼容警告，未升级系统Node。
- 测试依赖的glob10.5.0安装时有上游弃用提醒；npm audit当前0条漏洞。
- Starlette TestClient对httpx和AnyIO别名有2条弃用提醒，测试均通过；未隐藏提醒，
  后续升级测试栈时处理，不是服务运行失败。
- 已配置开发源码挂载、Uvicorn reload与Vite轮询监听；修改依赖清单需要重新构建镜像。
- 本机开发数据库仍无账号，只在隔离网络用于健康ping；正式业务数据接入/部署前补认证。
- 当前缺少业务接口、业务页面、NLP环境和真实Silver清洗；不把环境检查页当成业务成果。
- 原始数据未改动，本轮未git提交或推送。先前基础环境变更仍保留在工作区。
