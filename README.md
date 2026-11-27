# TestPilot

智测领航：面向基础开发者的智能软件测试平台。当前 main 已接通项目、需求、用例确认、真实执行、HTML 报告和 Agent 接口。

[Beta 冲刺记录与运行证据](docs/beta-sprint-blog.md) · [公开体验样本源文件](docs/public-sample/index.html)

## Windows 推荐启动（真实模式）

需要 Python 3.11+、Node.js 18+ 和 npm 8+，首次安装依赖需要网络。以下命令在仓库根目录的 PowerShell 运行，无需激活虚拟环境。

```powershell
# 只检查版本、依赖及端口，不安装、不启动服务
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -Check

# 设置本次登录演示服务的密码，输入时不回显；环境页面使用同一值
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host '本地演示密码' -AsSecureString)).Password

# 安装依赖，启动 Vue、平台 API 和登录演示服务；先跳过模型也能验收
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -NoModel
```

成功后访问：

- **真实页面**：[项目列表](http://127.0.0.1:5173/projects)。新库显示“暂无项目”，可以创建自己的项目。
- **平台 API**：[接口文档](http://127.0.0.1:8000/docs)，[健康检查](http://127.0.0.1:8000/api/health)。
- **被测登录服务**：`http://127.0.0.1:8010`；这是测试目标，首页404属于正常情况。

启动入口显式设置 `VITE_USE_MOCK=false`，复用 `npm ci`、仓库现有的 `npm run dev` 和后端配置。启动完成前会检查 API、演示服务及前端代理。
在启动终端按 Enter 或 Ctrl+C 停止本次服务，SQLite 数据保留。每台电脑各自保存本机数据库，跨电脑传递复现步骤及脱敏证据。

### 下次启动及独立空库

```powershell
# 已安装依赖时跳过重复安装；DEMO_PASSWORD仍需在当前终端设置
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -SkipInstall -NoModel

# 用另一个文件做独立测试，保留原数据库
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -Database backend/data/repro.sqlite3 -NoModel
```

默认数据库为 `backend/data/testpilot.sqlite3`；可通过 `-Database` 或 `TESTPILOT_DATABASE` 指定，仓库相对路径不会随终端所在目录变化。首次建库，后续启动直接使用原文件。
多个 Python 版本并存时，可传 `-Python python`，也可传目标 Python 可执行文件。启动检查失败会显示具体修复方法，不会自动结束占用端口的进程。

### 使用真实模型或跳过模型

运行带 `-NoModel` 的入口时，模型调用明确禁用，页面仍连接真实后端。可手动录入/保存/确认用例，再执行和下载报告；点击模型功能会返回配置错误，按提示补配置后重新启动即可。

要使用真实 DeepSeek，在启动前将密钥设为当前终端环境变量，启动命令省略 `-NoModel`：

```powershell
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'DeepSeek API Key' -AsSecureString)).Password
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -SkipInstall
```

密钥不会写入文件或命令参数。其他模型兼容配置见 [Agent说明](backend/app/modules/agent/README.md)。
纯前端模拟演示由 `VITE_USE_MOCK=true` 控制，样例数据不写入真实 SQLite，不能算真实模式验收；具体切换和手动三终端启动见 [Windows启动与排障](docs/windows-start.md)。

## 完整实测演示（推荐路径）

仓库自带一个「被测小游戏」示例，clone 下来就能把「上传项目 → 功能追问 → 生成用例 → 执行 → 报告」完整走一遍，不用自己另外准备项目。详见 [示例项目说明](examples/arrow-game/README.md) 与 [从空白到 5 PASS 的操作清单](docs/quickstart-demo.md)。

每台电脑各自需要准备（仓库无法代劳）：Python 3.11+、Node.js 18+、npm 8+，首次启动需联网装依赖；想让平台自动追问和生成用例，需要自己的 DeepSeek API Key；端口 5173、8000、18085 要空闲。没有 Key 也能启动、手动写用例并执行，加 `-NoModel` 即可。

**终端 1 —— 起被测小游戏**（仓库根目录）：

```powershell
python examples/arrow-game/arrow_game_http.py examples/arrow-game/一箭又一箭_测试需求简版.zip --port 18085
```

**终端 2 —— 起平台**：

```powershell
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'DeepSeek API Key' -AsSecureString)).Password
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -NoDemo
```

第二次启动可加 `-SkipInstall`。`-NoDemo` 跳过平台自带的 8010 登录演示服务，因此不用设 `DEMO_PASSWORD`；它只影响启动脚本，不改数据库和页面。不带 `-NoDemo` 时行为与原来完全一致。看到 `[READY] frontend: http://127.0.0.1:5173/projects` 后打开网页即可。

若提示 `Node.js was not found`，先确认 `node -v` 能执行；装在非标准位置时，把该目录临时加进 `$env:Path` 再启动。

## 复现及验证

[Windows启动与排障](docs/windows-start.md) 包含手动步骤、故障处理、空库保存/重启流程和第二人回传表。
[第二阶段启动交付说明](docs/phase2-startup-handover.md) 记录基线、实测结果及待验证项。

```powershell
# 启动诊断测试，仅使用Python标准库
python -m unittest discover -s scripts/tests -v

# 在独立源码目录、新虚拟环境和新SQLite中验收三服务，首次需要安装依赖
python scripts/verify_startup.py --output docs/evidence/phase2-startup.json

# 后端原有回归测试
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

启动验收脚本需要 Windows，先检查5173、8000、8010端口是否空闲。验证真实 Vite 代理、项目/需求持久化、无模型执行和报告、原端口占用进程保留及缺少 Node 的提示；不会向外部模型发请求。

## 模块文档

- [Alpha接口约定](docs/api-alpha.md)：请求字段、状态码及当前功能边界。
- [数据库与模块接入](docs/backend-integration.md)：连接、事务、项目归属及版本查询。
- [用例/预检/报告](backend/app/modules/cases/README.md)、[执行器](backend/app/modules/runs/README.md)。
- [前端说明](frontend/README.md)、[演示服务说明](demo_service/README.md)。

当前是本机开发版，没有多用户身份认证。环境配置公开响应仅返回字段名，实际值保存在本机 SQLite 中；数据库、`.env`、密钥、密码和 token 均不得提交。后端配置示例见 [backend/.env.example](backend/.env.example)。
