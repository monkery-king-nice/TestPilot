# 确定性测试执行模块（周兴宇）

实现 Alpha FR-06、07、08：运行 API、单批互斥、整批预检、冻结快照、单后台worker顺序执行、变量提取、四类结果、证据脱敏和中断恢复。原 `demo` 批次仍使用服务端 `DEMO_BASE_URL`；`local` 批次使用操作者为当前项目明确配置的回环 HTTP(S) 地址。`httpx` 禁用自动跳转和环境代理，默认超时 3 秒。

## 项目级测试服务与冻结目标

环境 PUT 在原 `secrets` 外增加两个可空字段。原演示请求不变：

```json
{"target":"demo","secrets":{"username":"demo-user","password":"本机填写"}}
```

项目本地服务请求：

```json
{
  "target":"local",
  "service_id":"service-b",
  "base_url":"http://127.0.0.1:18082",
  "secrets":{"username":"本机填写","password":"本机填写"}
}
```

`local` 仅允许 `http/https` 的 `127.0.0.1`、`localhost`、`::1`，必须显式端口且只能是根地址；拒绝用户凭证、查询、片段、空白和控制字符。接口登记仍只收相对路径。环境 GET/PUT 返回 `target/service_id/base_url/environment_version/configured_keys`，绝不返回 username、password。首次保存的版本为 1，此后每次完整保存都递增版本，包括目标地址或凭据变化；旧数据库迁移后已有环境从版本 1 开始。

创建批次时通过 `RunDependencies.read_execution_target(project_id)` 读取项目目标，并冻结非敏感快照：

```json
{"kind":"local","service_id":"service-b","base_url":"http://127.0.0.1:18082","environment_version":1}
```

- `RunDetail.target` 和内部 `get_frozen_snapshot()` 顶层 `target` 均返回该快照；历史报告应从这里读取，不读取项目当前环境。
- 新批次缺环境、目标缺字段、环境版本无效或目标类型无效时在创建前返回 422，不创建批次、不发请求，也不回退到 demo。
- 执行开始前只调用一次内部 `read_environment(project_id, kind, expected_version)`，在同一连接校验目标与版本并读取凭据，整个批次复用这一次读取的内存值。
- 创建后、执行前若环境被重新保存，目标和版本不再与冻结值匹配，整批直接结束为 ERROR，所有步骤记录 `error_stage=environment_changed`，提示重新预检并创建批次；不会向旧地址或新地址发送任何请求，也不会把 A 的凭据发给 B。
- 密钥不写入运行快照、报告或证据；配置变更的提示也不包含环境值。仅旧数据库中 `target_json` 为 NULL 的历史批次保留原 demo 执行行为，其公开 `target` 为 null。
- 跨项目读取批次返回 404；停机记录 `error_stage=connection`，HTTP 状态为 null。

给陈睿涛、沈冠宇的字段契约即 `target.kind/service_id/base_url/environment_version`；预检错误沿用 `{"detail":"原因"}`，目标缺失为 422，环境变更与停机属于已结束批次的 ERROR，不是预检 422。

## 双本地服务真实验证

```powershell
.venv\Scripts\python backend/tests/runs/project_target_evidence.py --output-dir artifacts/project-target-run-outcomes
```

脚本启动两个不同端口、返回不同 `user.id` 的真实本机 HTTP 服务，并使用独立临时 SQLite。PASS 选择 B 时，B 收到 `POST /auth/login`、`GET /me`，A 请求数为 0；FAIL 是项目 A 的人为错误 `user.id` 断言；ERROR 来自单独启动后停止的第三个实例。还验证缺环境 422 且不产生运行记录、跨项目 404，以及修改当前环境后历史目标仍为原快照。输出 `evidence.json` 不含密码或 token。正式项目和共享最终批次仍由郭泽强亲自执行。

另运行 `.venv\Scripts\python -m pytest backend/tests/runs/test_target_freezing.py::test_environment_change_never_sends_a_credentials_to_b -q`。该回归让 A、B 使用不同账号密码，在创建 B 的版本 1 批次后切换到 A 的版本 2 配置；旧批次必须以 `environment_changed` 停止，A／B 请求数均为 0，公开结果与冻结快照均不含双方凭据。

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

### 项目模块：内部目标与环境读取适配器

`RunDependencies.read_execution_target(project_id)` 返回当前项目的 `{target,service_id,base_url,environment_version}`；缺少配置时抛出 `PreflightRejected`。`RunDependencies.read_environment(project_id, kind, expected_version)` 在同一连接校验目标和冻结版本，并返回仅服务端可见的 `{username,password}` 字符串映射，kind 为 `demo` 或 `local`。每次执行只读取一次并复用内存值；版本变化抛出 `EnvironmentChanged`，不得改读新配置。不要调用公开 environment GET，也不要把环境值写入 runs 表或日志。demo URL 来自服务端 `RunSettings`，local URL 来自项目环境；用例只能提供相对路径。

### 陈睿涛、沈冠宇、郭泽强：结果与快照读取

- 前端轮询 `GET /api/projects/{project_id}/runs/{run_id}`，响应严格为 RunDetail，含可空 `target`。
- 报告和 AI 分析可调用 `RunService.get_run(project_id, run_id)` 获取同一份脱敏冻结结果。
- 报告另用 `RunService.get_frozen_snapshot(project_id, run_id)` 读取需求依据、版本、端点和顶层目标快照；该内部接口不经过 HTTP。配置变更后仍须读取这里的 `target`，不得替换为项目当前环境。

生产后端已由 `backend/app/main.py` 注册真实项目、用例、执行和报告路由；`standalone.py` 仅用于保留独立登录演示。

## 尚未联调项

真实项目 ZIP、正式项目名称和启动方式仍待队长提供；前端环境配置、历史目标展示与正式页面操作由陈睿涛和郭泽强联调。当前分支的 PASS/FAIL/停机 ERROR 是真实本机 HTTP 验证，不冒充正式项目验收；超时、禁止跳转和单批冲突继续使用可控本地替身验证。
