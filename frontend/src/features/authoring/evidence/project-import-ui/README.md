# 项目 ZIP 与需求补充页面交接

基线 main 为 4cdb389，初版功能提交为 9dc1797，复审修复提交为 667749a。实测日期为 2026-11-19，Windows、Node 24.14.0、Python 3.13、pytest 8.4.2、Edge。后端依赖按 backend/requirements.txt 安装。

## 实现与边界

需求页接通 ZIP 二进制上传、文档片段预览、候选接口确认、单独导入 MD/TXT、手工需求和接口登记。上传、保存需求和接口登记分别显示状态。保存后 URL 记录当前需求，刷新恢复正文、版本和 ZIP 来源。

逐条追问旁可填写答案、预览完整补充并保存为新版本。原文、引用、问题和答案通过现有需求文本持久化，ZIP 来源通过 source 持久化。澄清及候选生成传已保存需求的 ID 和版本。

为防止两人同时修改时旧答案覆盖新版本，本 PR 补充可选 expected_version，服务端在同一写事务中核对，不匹配返回 409。旧客户端省略字段仍兼容。已在曾炜毅的 [PR #18](https://github.com/monkery-king-nice/TestPilot/pull/18#issuecomment-7009879736) 列出契约影响，需后端负责人一并评审。

ZIP、预览、登记和需求保存均请求真实 FastAPI，写入独立 SQLite。浏览器回归使用 projectImport.testserver.py 的明确模型替身，验证 UI 和版本传递。正式项目资料及真实 DeepSeek 效果仍待队长验收。

## 正常操作与结果

| 页面操作 | 实际结果 |
|---|---|
| 新建项目，上传 book-catalog.zip | 展示包名、文档和候选接口，未创建需求或登记接口 |
| 勾选候选，确认登记 | 持久化接口 ID 和版本，重复点击只发一次确认请求 |
| 选择 docs/requirements.md，预览并作为新需求 | 显示原文和片段来源 |
| 保存并刷新 | 同一需求 v1 和 source 恢复 |
| 检查缺项、输入答案、预览、保存补充 | 保存为 v2，刷新后正文包含引用、问题与答案，source 保留 |
| 进入测试用例页，生成候选 | 请求携带 requirement_version=2，候选留待人工保存确认 |
| 上传无 OpenAPI 的 room-schedule.zip | 选择 TXT，手工登记 GET /rooms 后可继续 |

## 反例结果

- 取消文件选择不修改原文，取消替换保留未保存输入。
- 坏 ZIP 不修改已有需求，40 MiB 超限在上传前提示并保留原文。
- 前后端上传上限均为 40 MiB。后端回归接受恰好 40 MiB 的有效 ZIP，增加一个字节返回 413，未多建导入记录。
- 约 32.7 MiB 的合成 ZIP 经浏览器上传成功，可预览 docs/requirements.md。其大小和合成标记记录在 handoff.json。评审提到的正式原包尚未取得，本次结果属于合成大包回归，原包验收待补。
- 包内无需求文档时可手工录入，长文档可选择合法的 16000 字符以内片段。
- 另一客户端已更新需求后，旧答案保存返回 409。原文和答案保持可见，用户取消加载最新需求后仍保留答案。
- 在多个需求中保存新的片段后刷新，仍回到刚保存的需求。
- 原有 MD/TXT 文件导入浏览器回归通过。
- 未保存答案时点击用例页，关闭提示保留答案；选择保存后离开，用例页读取 v2；选择放弃后才离开。
- 刷新时取消浏览器提示可保留答案。版本冲突导致保存失败时继续留在需求页并保留答案。

## 复现命令

以下命令在仓库根目录执行。使用项目支持的 Python 3.11+，本次为 Python 3.13。

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
.venv/Scripts/python -m pytest backend/tests/test_projects.py backend/tests/test_project_imports.py backend/tests/test_requirement_update_version.py backend/app/modules/agent/test_project_context.py -q
```

实际为 55 passed，保留现有 TestClient 弃用提示。前端从 frontend 目录执行，实际为 3 项 Node 测试通过，类型检查和构建通过，构建有现有的大文件体积提示。

```powershell
cd frontend
npm ci
node --test src/features/authoring/*.test.js
npm run typecheck
npm run build
```

从仓库根目录创建样本并启动明确使用模型替身的浏览器测试后端。

```powershell
$samples = Join-Path $env:TEMP 'testpilot-project-ui-samples'
.venv/Scripts/python frontend/src/features/authoring/projectImport.testserver.py --samples-dir $samples
$env:TESTPILOT_DATABASE = Join-Path $env:TEMP 'testpilot-project-ui.sqlite3'
.venv/Scripts/python frontend/src/features/authoring/projectImport.testserver.py
```

在另一个终端启动真实接口模式前端。

```powershell
cd frontend
$env:VITE_USE_MOCK = 'false'
npm run dev -- --port 5178 --strictPort
```

浏览器脚本使用已安装的 Edge，playwright-core 安装在临时目录。从仓库根目录运行。

```powershell
$tools = Join-Path $env:TEMP 'testpilot-ui-browser'
npm install --prefix $tools playwright-core
$env:NODE_PATH = Join-Path $tools 'node_modules'
$env:SAMPLE_DIR = Join-Path $env:TEMP 'testpilot-project-ui-samples'
$env:EVIDENCE_DIR = Join-Path $env:TEMP 'testpilot-project-ui-evidence'
node frontend/src/features/authoring/projectImport.browser.cjs
node frontend/src/features/authoring/requirementImport.browser.cjs
```

两个浏览器脚本均输出 PASS。正式验收请改用常规后端入口 app.main:app 和实际模型配置，按上方页面操作执行。

## 交接记录

完整项目 ID、导入 ID、需求 ID、v1/v2、source 和请求记录在 [handoff.json](handoff.json)。这些 ID 属于本机独立数据库，跨电脑请运行脚本重建样本。

- [ZIP 和文档预览](01-zip-document-preview.png)
- [答案与补充预览](02-answers-preview.png)
- [刷新后的 v2 和来源](03-saved-v2-source.png)
- [过期答案拦截](04-stale-answer-preserved.png)
- [长文档与上传超限](05-limits-preserve-source.png)
- [32.7 MiB 合成 ZIP 上传和文档预览](06-large-zip-preview.png)

郭泽强负责真实模型和正式项目验收及最终合并，沈冠宇可沿用两版需求做用例复核。陈睿涛的环境与执行页面继续使用已确认用例衔接。
