# Windows 真实模式启动、排障及第二人复现

负责人：曾炜毅；范围是根README、启动脚本及配套验收，不修改页面或业务API。

## 推荐入口

从仓库根目录运行 `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/start.ps1 -Check`。
检查Python、Node.js、npm、现有依赖和5173/8000/8010端口；该模式不安装依赖，不创建或修改数据库。
首次正常启动会在仓库创建`.venv`，按后端requirements与约束文件安装，在frontend运行`npm ci --no-audit --no-fund`，随后运行已有`npm run dev`及两项Python服务。
这是本地开发服务，全部监听127.0.0.1。脚本不会安装系统软件、更改系统执行策略或结束原有进程。
`-ExecutionPolicy Bypass`仅用于当前PowerShell进程加载仓库脚本，没有执行`Set-ExecutionPolicy`。

先在本次PowerShell终端安全设置`DEMO_PASSWORD`，命令见根README；也可在交互启动提示中隐藏输入。
平台“环境配置”使用`DEMO_USERNAME`（未设置时为demo-user）及刚设置的密码，不要将密码写进需求或用例。
按Enter或Ctrl+C停止本次服务；后端有正常关闭机会，Windows Job负责收回本次npm/Vite子进程。保留数据库，下一次可用相同文件继续。

## 常见问题

| 提示或现象 | 处理方法 |
|---|---|
| Python未找到/版本过低 | 安装Python 3.11+并勾选PATH，重新打开终端；多个版本时用`-Python python`指定已选中的解释器 |
| Node.js未找到/版本过低 | 安装带npm的Node.js，重新打开PowerShell后先运行`node --version`、`npm.cmd --version`，再运行`-Check` |
| npm未找到或CLI缺失 | 修复Node.js安装并保留npm组件，重新打开终端；脚本绕过npm.ps1，避免依赖其执行策略 |
| Port 8000/8010/5173 occupied | 用`Get-NetTCPConnection -LocalPort 8000`等命令查看OwningProcess，再用`Get-Process -Id <实际PID>`核对。若是自己上次启动的服务，回原终端停止；他人进程请先协调，不按端口批量结束 |
| 安装失败 | 检查网络和包源后重新运行；程序保留现有数据库，错误码非零。不要删除SQLite来修复依赖问题 |
| -SkipInstall提示缺依赖 | 去掉该参数运行一次；或按下面手动命令补依赖 |
| 健康检查失败/服务提前退出 | 查看同终端上方错误；本次其他子服务会清理。修复依赖、端口或配置后重试，成功访问地址以`[READY]`为准 |
| 页面出现固定“接口测试演示项目”及样例ID | 核对终端输出为REAL，并使用5173端口的真实页面；手动启动时确认`VITE_USE_MOCK=false`后重启Vite |
| 缺少模型密钥/模型功能502 | 用`-NoModel`完成手工确认、执行和报告；要调用模型，按README设置环境变量并省略`-NoModel`重启。无需重建数据库 |
| 演示服务首页404或/me返回401 | 这是正常未鉴权响应；正确登录后再调用/me。启动入口以401及UNAUTHORIZED核对演示服务健康，不输出token |

## 手动三终端启动

先在仓库根目录建立后端虚拟环境：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements.txt -c backend/requirements-lock.txt
```

终端一运行登录演示服务：

```powershell
$env:DEMO_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host '本地演示密码' -AsSecureString)).Password
.venv\Scripts\python demo_service/server.py
```

终端二运行平台API；默认可在无模型配置时启动，模型功能返回502，其他功能照常：

```powershell
$env:DEMO_BASE_URL = 'http://127.0.0.1:8010'
$env:TESTPILOT_DATABASE = 'backend/data/testpilot.sqlite3'
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

终端三从仓库根目录进入frontend，运行真实模式：

```powershell
cd frontend
npm.cmd ci --no-audit --no-fund
$env:VITE_USE_MOCK = 'false'
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

实际访问地址为`http://127.0.0.1:5173/projects`，开发代理访问8000的`/api`。
纯前端自测可把第三终端`VITE_USE_MOCK`设为`true`后重新运行dev；该模式无需API，但数据来自样例，不作为真实验收。
手动模式由操作者在三个原终端各按Ctrl+C停止。

## 第二人空库复现步骤

交给两名前端及另一位实际操作的同学，使用自己的独立检出和新库，不复制他人的数据库。

1. 记录当前`git rev-parse HEAD`与`python --version`、`node --version`、`npm.cmd --version`，按根README先运行`-Check`。
2. 运行`-Database backend/data/second-person.sqlite3 -NoModel`；若该文件已使用过，另选未使用过的新文件名，不删除原库。
3. 打开真实项目页，确认空列表；创建个人测试项目，保存一条需求。记录project_id、requirement_id、version及正文，刷新确认还在。
4. 在启动终端按Enter停止，使用相同Database参数加`-SkipInstall`重新启动；回到项目页，核对相同ID及正文。
5. 无模型时，可用API文档保存/确认手工CaseDraft；配置演示环境后执行并下载同一run_id的报告。`backend/scripts/verify_cases_reports.py`提供完整可运行的手工用例来源。
6. 回传第一处遇到的问题及下面的脱敏记录；不要传数据库、模型输入中的私密内容、凭证、密钥或token。

| 回传项 | 由实际操作者填写 |
|---|---|
| 同学/测试日期 | |
| Git提交与系统/工具版本 | |
| 模式 | REAL，VITE_USE_MOCK=false；模型禁用/真实模型（不填密钥） |
| 首次启动命令与结果 | |
| project_id、requirement_id、version | |
| 保存的非敏感正文、重启后是否一致 | |
| 如执行：case_id/version、run_id、报告批次ID | |
| 第一处问题/没有遇到问题 | |
| 脱敏截图或错误文字 | |

## 实测记录

详见[第二阶段交付说明](phase2-startup-handover.md)与[机器可读验收记录](evidence/phase2-startup.json)。
当前已执行的独立目录复现和第二位同学的独立操作分别记录，第二人部分等待实际回传。
