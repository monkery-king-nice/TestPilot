# TestPilot
智测领航 TestPilot：面向基础开发者的智能软件测试平台，2026秋软件工程实践团队项目。

本分支交付曾炜毅负责的 **后端：项目基础与数据（FR-01、02、03 的 Alpha 约定部分）**。
项目、需求、接口登记、环境配置可独立运行；已接入主分支现有的需求澄清模块，使用真实需求数据库读取原文。
执行器代码已在主分支合入，待用例预检模块就绪后接入公共入口；用例确认和报告由其他成员实现，完整链路仍需联调。需求澄清的真实模型配置见 [Agent说明](backend/app/modules/agent/README.md)，未配置密钥时该接口返回502，基础数据接口仍可用。

## 启动后端

Python 3.11+；本机使用 Python 3.13 验证。以下命令均在仓库根目录运行。

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

在浏览器打开 [交互式接口文档](http://127.0.0.1:8000/docs)，或请求 `GET /api/projects`。
默认数据库为 `backend/data/testpilot.sqlite3`，首次启动自动建表，停止/重启保留数据。
该路径固定相对于仓库根目录；如需使用其他库，在启动前设置 `$env:TESTPILOT_DATABASE = 'D:\testpilot-data\app.sqlite3'`。

Linux/macOS：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

## 创建项目、需求和两个接口

保持服务运行，在另一个 PowerShell 窗口从仓库根目录执行。
以下只使用一次性演示凭证；发送 JSON 时显式采用 UTF-8，以兼容 Windows PowerShell。

```powershell
$api = 'http://127.0.0.1:8000/api/projects'
$body = [Text.Encoding]::UTF8.GetBytes('{"name":"TestPilot演示项目"}')
$project = Invoke-RestMethod -Method Post -Uri $api -ContentType 'application/json; charset=utf-8' -Body $body
$p = "$api/$($project.id)"
$body = [Text.Encoding]::UTF8.GetBytes('{"text":"系统支持登录并返回用户信息"}')
$requirement = Invoke-RestMethod -Method Post -Uri "$p/requirements" -ContentType 'application/json; charset=utf-8' -Body $body
Invoke-RestMethod -Method Post -Uri "$p/endpoints" -ContentType 'application/json' -Body '{"method":"POST","path":"/auth/login"}'
Invoke-RestMethod -Method Post -Uri "$p/endpoints" -ContentType 'application/json' -Body '{"method":"GET","path":"/me"}'
Invoke-RestMethod -Method Put -Uri "$p/environment" -ContentType 'application/json' -Body '{"target":"demo","secrets":{"username":"demo-user","password":"local-demo-only"}}'
Invoke-RestMethod -Uri "$p/environment"
```

创建项目返回 `201` 和 `{"id":"实际UUID","name":"TestPilot演示项目"}`；创建需求和端点同样返回 `201`。
环境读取和写入响应均只有 `{"target":"demo","configured_keys":["password","username"]}`，不会回传值。
未配置环境时 GET 返回 `configured_keys: []`，执行器内部读取会明确拒绝未配置环境。

## 验证

```powershell
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check backend/app/core backend/app/modules/projects backend/app/main.py backend/scripts backend/tests
.venv\Scripts\python backend/scripts/verify_project_data.py --output docs/evidence/project-data-http.json
```

最后一项会启动两个独立后端进程，使用临时数据库验证真实 HTTP 调用及进程重启。
不需要事先启动8000端口，不改动你的演示数据库，不调用外部模型或被测服务。
已保存的实测结果见 [验收证据](docs/evidence/project-data-http.json)。

## 队友对接

- [Alpha v1 接口约定](docs/api-alpha.md)：路径、字段、状态码和全组约定。
- [数据库及模块接入说明](docs/backend-integration.md)：共享连接、事务、项目校验、版本查询、Agent 和执行器适配。
- [个人交付说明](docs/曾炜毅-后端交付说明.md)：职责、验证结果、站会演示、待联调项。

前端通过 `/api` 请求；Vite 开发代理指向 `http://127.0.0.1:8000`。
演示服务另行运行，见 [演示服务说明](demo_service/README.md)。执行目标配置为服务端环境变量 `DEMO_BASE_URL`，默认 `http://127.0.0.1:8010`；公开 API 只接受 `target: "demo"`。

当前是本机开发版，没有用户登录/权限体系。项目归属校验用于阻止跨项目引用，不代表用户身份认证。
环境值仅供服务端读取，保存在本地 SQLite 文件中；数据库、`.env`、日志和真实凭证不得提交。配置示例见 [backend/.env.example](backend/.env.example)，需在终端设置，程序不会自动读取该文件。
