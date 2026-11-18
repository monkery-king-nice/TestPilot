# 需求澄清 · 给林彦羽和曾炜毅

用户录入需求，点击“检查缺项”。页面展示每一条 quote（原文）和 question（追问）。用户补充并保存新需求后，再调用同一个接口。READY 表示当前分析未提出追问；执行测试还需要人工确认用例。

## 林彦羽：今天即可对接

从分支仓库根目录用 PowerShell 运行。两个预置需求只用于前端联调，在终端和 /docs 中明确标记。这个独立服务使用 8011 端口。生产后端使用下文的 router。

```powershell
python -m pip install fastapi uvicorn httpx
python -m uvicorn backend.app.modules.agent.preview:app --host 127.0.0.1 --port 8011
```

在另一个窗口调用：
```powershell
$url = 'http://127.0.0.1:8011/api/projects/demo/agent/clarify'
Invoke-RestMethod -Method Post $url -ContentType 'application/json' -Body '{"requirement_id":"req-1"}' | ConvertTo-Json -Depth 5
Invoke-RestMethod -Method Post $url -ContentType 'application/json' -Body '{"requirement_id":"req-2"}' | ConvertTo-Json -Depth 5
```

req-1 的原文为“登录后显示我的信息”，样例返回 NEEDS_INFO 和三个追问，分别涉及登录输入、用户字段与判定依据、错误密码。req-2 补充这些约定，样例返回 {"status":"READY","questions":[]}。完整输入和预置回答在同目录 examples.json。核心模块会拒绝不在原文中的 quote。Vue 开发代理可将本模块的请求转发到 8011。

## 曾炜毅：合入共享后端

在 FastAPI 的 app 初始化时调用 app.include_router(build_router(load_text))。从本目录 router.py 导入 build_router。提供同步函数 load_text(project_id, requirement_id)，按两个 ID 同时查库，返回当前需求原文，查不到返回 None。接口为 POST /api/projects/{project_id}/agent/clarify，请求体仅需 requirement_id。找不到需求返回 404，空文本或超过 16000 字符返回 422，模型配置、网络或输出错误返回 502 和 detail。

## 郭泽强：真实模型验证

正常后端默认调用真实模型。配置 TESTPILOT_MODEL_URL（完整的 Chat Completions 兼容端点）、TESTPILOT_MODEL（团队选定的模型名），需鉴权时在本机设置 TESTPILOT_MODEL_KEY。只传需求正文，不传环境里的演示凭证。不要把密钥写入仓库。

```powershell
python -m backend.app.modules.agent.demo --live
python -m backend.app.modules.agent.demo --live --text "订单支付后给用户发通知"
```

无配置时上述命令报错退出。若用真实模型启动预览服务，先设 $env:TESTPILOT_PREVIEW_MODE='live'，再启动 uvicorn。未设置时预览服务返回固定样例。命令行不加 --live 可运行两组预置样例。

## 验证

```powershell
python -m unittest backend.app.modules.agent.test_clarify backend.app.modules.agent.test_router -v
```

测试覆盖引用校验、缺项状态、空输入、接口成功响应、项目隔离和模型错误。固定样例和测试替身不能计作真实模型评估。
