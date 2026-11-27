# 气象站课堂演示

在仓库根目录打开两个 PowerShell 窗口。第一窗口打包要手工上传的文档，并保持观测站服务运行。

```powershell
Compress-Archive -LiteralPath .\examples\station\station.md -DestinationPath "$env:TEMP\TestPilot-station.zip" -Force
py -3 -m http.server 18089 --bind 127.0.0.1 --directory docs/public-sample
```

第二窗口启动 TestPilot。首次使用会安装依赖。

```powershell
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'DeepSeek Key' -AsSecureString)).Password
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -NoDemo
```

1. 打开 `http://127.0.0.1:5173`，新建项目“观测站”。手工上传第一窗口生成的 ZIP，选 station.md，预览、作为需求原文并保存。
2. 手工登记 GET /reading.json。点击“检查缺项”，检查发送资料并同意，展示模型提出的真实问题。
3. 将本轮需求写清并保存为新版本。“本次只测正常读取。在本机测试环境中，无需登录，使用 GET /reading.json，不传查询参数、请求头或请求体。响应为 HTTP 200，JSON 对象的 unit 字段等于字符串 C。”
4. 到用例页按新版本生成候选。逐条检查 HTTP 200 和 unit 等于 C，确认要演示的用例。需要对照时手工另建一条相同步骤的用例，将单位预期设为 F，保存并确认。保留原先预期 C 的用例。
5. 环境选择“项目本地服务”，填 station、http://127.0.0.1:18089，勾选无需登录并保存。执行页选择两条已确认用例，由正式验收人点击执行。
6. 让体验者解释为什么同是 HTTP 200 会得到两个结果。打开失败分析，核对要发给模型的证据后同意，下载本批 HTML 报告。课后在两个窗口分别按 Ctrl+C 停止服务。

如果演讲当天模型不可用，使用已确认用例展示执行，并打开博客内的真实模型返回记录。公开样本也可以在第一窗口运行期间访问 http://127.0.0.1:18089 ，在浏览器直接比较两种单位。
