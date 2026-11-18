# 确定性测试执行模块（周兴宇）

实现 Alpha FR-06、07、08：运行 API、单批互斥、整批预检、冻结快照、单后台worker顺序执行、变量提取、四类结果、证据脱敏和中断恢复。只向服务端配置的 `DEMO_BASE_URL` 发请求；`httpx` 禁用自动跳转，默认超时 3 秒。

## 从仓库根目录运行（Windows PowerShell）

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python -m pytest backend/tests/runs -q
```

测试会启动郭泽强分支中的真实 `demo_service`，并分别验证：成功登录与 `/me`、业务断言 FAIL、准备失败 BLOCKED、错误密码预期 401 为 PASS；超时使用明确的 `httpx.MockTransport` 替身，不计为真实演示请求。

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
