# 第二阶段需求文件导入验收

基线为 main 的 b97845c，功能与测试代码提交为 c6fca31。测试日期为 2026-11-19。

## 实测环境

- Windows，Node 24.14.0，Python 3.13，Edge 无界面浏览器。
- 独立 Python 3.13 虚拟环境按 backend/requirements.txt 安装，FastAPI 0.163.2、Pydantic 2.14.3、Uvicorn 0.54.0、httpx 0.28.1。
- VITE_USE_MOCK=false，真实 FastAPI 与独立 SQLite 文件，使用此次验收项目。

## 运行

先在仓库根目录启动独立测试数据库的后端。

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
$env:TESTPILOT_DATABASE = Join-Path $env:TEMP 'testpilot-phase2-import.sqlite3'
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

另一个终端启动前端。

```powershell
cd frontend
npm ci
$env:VITE_USE_MOCK = 'false'
npm run dev -- --port 5178 --strictPort
```

Node 24 环境中，从 frontend 目录运行解码与校验测试、类型检查和构建。

```powershell
node --test src/features/authoring/model.test.js src/features/authoring/requirementFile.test.js
npm run typecheck
npm run build
```

从仓库根目录运行真实浏览器验收。playwright-core 安装在临时目录，Edge 使用本机安装路径，EDGE_PATH 可覆盖默认位置。

```powershell
$toolDir = Join-Path $env:TEMP 'testpilot-import-browser'
npm install --prefix $toolDir playwright-core
$env:NODE_PATH = Join-Path $toolDir 'node_modules'
$env:FRONTEND_URL = 'http://127.0.0.1:5178'
$env:EVIDENCE_DIR = Join-Path $env:TEMP 'testpilot-import-evidence'
node frontend/src/features/authoring/requirementImport.browser.cjs
```

## 预期与实际

| 操作 | 实际 |
|---|---|
| 导入中文多行 Markdown，含 UTF-8 BOM | 编辑框显示原文，导入后 API 需求列表为空，保存和模型请求均为零 |
| 修改 Markdown，再手动保存与刷新 | 保存为 v1，页面与数据库原文一致 |
| 在未保存输入上导入 TXT，先取消再确认替换 | 取消保留原稿，确认后才替换编辑框 |
| 保存多行 TXT 并刷新 | 同一 requirement_id 升到 v2，API 返回完整 CRLF、空行与末尾空白 |
| 导入错误扩展名、空白、非法 UTF-8、16001 字符 | 错误可见，原稿不变 |
| 16000 中文或补充平面字符的边界 | 解码校验通过 |
| 基础验证 | 2 项 Node 测试通过，类型检查与生产构建通过 |

构建保留现有的大文件体积提示。浏览器验收输出为 PASS，写入需求共两次，模型请求为零。

## 交接给沈冠宇和郭泽强

原文、project_id、requirement_id 和两个版本见 [handoff.json](handoff.json)。该组 ID 属于此次本机独立数据库，跨电脑请运行脚本创建自己的项目。

可直接选择 [sample.md](sample.md) 和 [sample.txt](sample.txt) 复现。前者带 BOM，后者保留 CRLF。

- [Markdown 导入预览](01-markdown-preview.png)
- [TXT 保存刷新后的 v2](02-txt-saved-v2.png)
- [无效文件保留原稿](03-invalid-preserves-source.png)

本次覆盖 AC-02 文件录入。需求条目编号、来源定位、真实模型生成效果及用例变更复核由后续共同验收记录。
