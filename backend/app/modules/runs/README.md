# 确定性测试执行模块（周兴宇）

实现 Alpha FR-06、07、08：运行 API、单批互斥、整批预检、冻结快照、单后台worker顺序执行、变量提取、四类结果、证据脱敏和中断恢复。只向服务端配置的 `DEMO_BASE_URL` 发请求；`httpx` 禁用自动跳转，默认超时 3 秒。

## 从仓库根目录运行（Windows PowerShell）

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python -m pytest backend/tests/runs -q
```

测试会启动郭泽强分支中的真实 `demo_service`，并分别验证：成功登录与 `/me`、业务断言 FAIL、准备失败 BLOCKED、错误密码预期 401 为 PASS；超时使用明确的 `httpx.MockTransport` 替身，不计为真实演示请求。

## 步骤变量的类型规则

- 整个字段只包含一个变量时，保留提取值的原始 JSON 类型。例如上一步提取数字 `42`，下一步字段 `"id": "{{steps.login.id}}"` 发送的是 JSON 数字 `42`，不是字符串 `"42"`；布尔值、对象、数组和 `null` 同样保留类型。
- 变量嵌入其他文字时按字符串处理。例如 `"Authorization": "Bearer {{steps.login.token}}"` 会生成 `Bearer <token>`。
- 嵌入字符串的变量必须是字符串、数字或布尔值；对象和数组应通过整字段引用传递，避免被隐式转换为不明确的字符串。

## 第二阶段：四类运行结果证据

从仓库根目录运行开发者自测。脚本使用两个独立临时 SQLite 数据库，平台 API 使用 TestClient，被测登录服务使用真实本机 HTTP；不调用模型，不修改共享演示库。

```powershell
.venv\Scripts\python backend/tests/runs/phase2_evidence.py verify --output-dir artifacts/phase2-run-outcomes
```

输出 `evidence.json`，逐项保存项目、需求版本、用例版本、批次、步骤状态、断言差异和演示服务请求记录。FAIL 的 `user.id` 预期被**人为**写成 `different-user`；BLOCKED 的准备登录**人为**使用错误密码；ERROR 使用单独启动后又停止的本机实例，不与共享正常服务混用。

| 场景 | 预期与实际核对点 |
|---|---|
| PASS | 错误密码是被测行为，登录实际 401，`code=INVALID_CREDENTIALS`，计数 PASS=1 |
| FAIL | 登录和 `/me` 均为 200，`me.error_stage=assertion`，保存用户编号不匹配的脱敏差异 |
| BLOCKED | 准备登录实际 401，主步骤 `error_stage=setup_failed`，请求日志只有登录、没有 `/me` |
| ERROR | 停止实例导致 `error_stage=connection`、HTTP 状态为 null，计数 ERROR=1 |

已有 `test_timeout_becomes_error_with_evidence` 仍单独记录 `httpx.MockTransport` 超时替身，不把它算作停止实例的真实连接证据。

### 给共同验收准备草稿

先按根 README 启动真实模式，并在当前终端设置 `DEMO_PASSWORD`。以下命令只创建独立项目、环境以及 PASS／FAIL／BLOCKED 三个草稿，**不自动确认、不自动执行**：

```powershell
.venv\Scripts\python backend/tests/runs/phase2_evidence.py prepare --api-base http://127.0.0.1:8000
```

`artifacts/phase2-run-outcomes/preparation.json` 保存交接 ID 和后续人工步骤。请逐条复核并人工确认；由郭泽强在共享验收页最终点击执行，优先把 FAIL 的 `run_id/case_id/case_version` 和脱敏差异交给失败分析与页面、报告负责人。共享环境的最终批次、真实 DeepSeek 分析和浏览器人工点击不在开发者自测中冒充完成。

## 公共后端合入前的独立演示

先在一个 PowerShell 窗口启动团队演示服务：

```powershell
$env:DEMO_USERNAME = 'demo-user'
$env:DEMO_PASSWORD = 'local-demo-only'
.venv\Scripts\python demo_service/server.py
```

另开窗口启动本模块的临时宿主页（仅含 runs 路由和四个固定已确认用例）：

```powershell
$env:DEMO_USERNAME = 'demo-user'
$env:DEMO_PASSWORD = 'local-demo-only'
.venv\Scripts\python -m uvicorn app.modules.runs.standalone:app --app-dir backend --host 127.0.0.1 --port 8000
```

创建成功批次并读取冻结结果：

```powershell
$body = @{cases = @(@{id = 'case-login-me'; version = 1})} | ConvertTo-Json -Depth 4
$run = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/projects/standalone-project/runs' -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/projects/standalone-project/runs/$($run.run_id)" | ConvertTo-Json -Depth 10
```

将 `case-login-me` 换成 `case-business-fail`、`case-setup-blocked` 或 `case-invalid-login` 可复现 FAIL、BLOCKED 或预期 401 的 PASS。站会建议保留成功批次与 `case-setup-blocked` 的完整 RunDetail JSON；重点展示 `counts`、逐步 `http_status`、`assertion_diffs`、`error_stage` 和脱敏后的 summary。数据库默认写入已被 Git 忽略的 `backend/data/`。

## 与其他模块的交接

### 沈冠宇：统一预检适配器

`RunDependencies.preflight(project_id, cases)` 接收有序的 `CaseRef(id, version)`，整批失败时抛出 `PreflightRejected([原因...])`，成功时按请求顺序返回冻结字典。预检必须先检查项目归属、CONFIRMED 状态、用例/需求/端点版本、1–20 条用例、每例 1–5 步、变量来源和断言可求值。执行器在创建批次前调用一次，失败不会创建批次或发送目标请求。

每个冻结字典至少需要：

```json
{
  "case_id": "case-1",
  "title": "登录后获取本人信息",
  "version": 1,
  "requirement_id": "req-1",
  "requirement_version": 2,
  "expected_basis": "已确认需求原文",
  "requirement": {"id": "req-1", "version": 2, "text": "需求原文"},
  "steps": [{"name": "login", "phase": "setup", "endpoint_id": "ep-login", "endpoint_version": 1, "headers": {}, "body": {}, "assertions": [{"type": "status", "expected": 200}], "extract": {"token": "token"}}],
  "endpoints": {"ep-login": {"id": "ep-login", "method": "POST", "path": "/auth/login", "version": 1}}
}
```

### 曾炜毅：内部环境读取适配器

`RunDependencies.read_environment(project_id, "demo")` 返回仅服务端可见的 `{username, password}` 字符串映射。不要调用公开 environment GET，也不要把环境值写入 runs 表或日志。目标 URL 只来自服务端 `RunSettings`，不由用例传入。

### 陈睿涛、沈冠宇、郭泽强：结果与快照读取

- 前端轮询 `GET /api/projects/{project_id}/runs/{run_id}`，响应严格为 RunDetail。
- 报告和 AI 分析可调用 `RunService.get_run(project_id, run_id)` 获取同一份脱敏冻结结果。
- 报告另用 `RunService.get_frozen_snapshot(project_id, run_id)` 读取需求依据、版本和端点快照；该内部接口不经过 HTTP。

生产后端合入时，由 `backend/app/main.py` 注册 `runs.router`，并将真实适配器构造为 `app.state.run_service`；`standalone.py` 仅用于公共模块未合入时的演示，不应作为生产入口。

## 尚未联调项

真实 `modules/cases` 预检、真实项目/环境数据库函数、HTML 报告和 AI 分析尚未合并，当前使用明确标注的测试替身。演示服务的 PASS/FAIL/BLOCKED 是真实 HTTP 验证；超时、禁止跳转和单批冲突使用可控本地替身验证。
