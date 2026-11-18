# TestPilot 登录演示服务

供 TestPilot 执行器联调。Python 3.9+ 标准库即可运行。服务只监听本机 127.0.0.1:8010，平台和演示服务请在同一台开发机运行。演示账户只用于本地测试，默认用户名为 demo-user；密码通过环境变量设置。单个服务进程共用一个临时 token，重启后旧 token 失效。

## Windows PowerShell 启动

从仓库根目录运行。示例密码仅用于本地演示。

```powershell
$env:DEMO_USERNAME = 'demo-user'
$env:DEMO_PASSWORD = 'local-demo-only'
python demo_service/server.py
```

保持窗口打开。另开 PowerShell，在同一仓库根目录运行以下命令。脚本会发出四个真实 HTTP 请求，遇到第一个不符合预期的结果即返回非零退出码。停止服务按 Ctrl+C。

```powershell
$env:DEMO_USERNAME = 'demo-user'
$env:DEMO_PASSWORD = 'local-demo-only'
python demo_service/smoke_test.py
```

## 周兴宇对接用例

服务根地址为 `http://127.0.0.1:8010`。登录请求使用 JSON 字段 username、password。成功响应中的 token 是字符串；将其作为后续请求的 Authorization: Bearer 值。登录准备失败时，执行器应把依赖该步骤的主测试记为 BLOCKED。独立的错误密码用例预期 401，实际符合即 PASS。

```powershell
$base = 'http://127.0.0.1:8010'
$payload = @{username=$env:DEMO_USERNAME; password=$env:DEMO_PASSWORD} | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri "$base/auth/login" -ContentType 'application/json' -Body $payload
Invoke-RestMethod -Uri "$base/me" -Headers @{Authorization="Bearer $($login.token)"} | ConvertTo-Json -Depth 3
```

| 实测请求 | 实际 HTTP 状态 | 已检查的响应内容 |
|---|---|---|
| POST /auth/login，正确凭证 | 200 | token 为非空字符串 |
| POST /auth/login，错误密码 | 401 | code 为 INVALID_CREDENTIALS |
| GET /me，使用本次登录的 token | 200 | user.id 为 demo-user |
| GET /me，无 Authorization | 401 | code 为 UNAUTHORIZED |

以上四项已于 2026-11-18 在 Windows 上启动独立服务进程并通过 smoke_test.py 验证。本次交付范围是被测演示服务，平台执行器联调和 Agent 模型接入另行验证。
