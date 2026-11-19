# 项目 ZIP 导入与接口登记

负责人曾炜毅。对接林彦羽的上传和需求页，以及郭泽强的需求澄清与生成。本文描述后端契约和可复现样本。

## 调用顺序

`P` 表示 `/api/projects/{project_id}`。先用已有 `POST /api/projects` 创建项目。错误延用 `{ "detail": "原因" }`。

| 请求 | 成功状态和用途 |
| --- | --- |
| `POST P/imports?filename=sample.zip` | `201`。请求体是 ZIP 原始字节，类型为 `application/zip` 或 `application/octet-stream`。返回导入清单。 |
| `GET P/imports/{import_id}` | `200`。读取清单和已确认接口，可在需求页刷新后用 `source.import_id` 恢复。 |
| `POST P/imports/{import_id}/preview` | `200`。传 `{path,start?,end?}`，返回 `{import_id,path,start,end,total_chars,text}`。 |
| `POST P/imports/{import_id}/confirm-endpoints` | `200`。传 `{candidate_ids:[...]}`，返回 `{project_id,import_id,endpoints:[{candidate_id,endpoint}]}`。 |
| `POST P/requirements` | `201`。传 `{text,source?}`，保存需求 v1。来源结构为 `{import_id,path,start,end}`。 |

浏览器上传可以通过现有 `/api` 开发代理执行：

```js
const response = await fetch(`/api/projects/${projectId}/imports?filename=${encodeURIComponent(file.name)}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/zip' },
  body: file,
})
const manifest = await response.json()
if (!response.ok) throw new Error(manifest.detail)
```

### 导入清单和接口选择

以下是图书目录样本的返回结构示意。每次上传都会生成新的 `id`，`candidate_id` 在当前导入内有效。用确切返回值调用确认接口。

```json
{
  "id": "导入记录ID",
  "project_id": "当前项目ID",
  "filename": "book-catalog.zip",
  "documents": [{"path":"docs/requirements.md","size":180}],
  "endpoint_candidates": [{
    "candidate_id":"1", "source_path":"api/openapi.json",
    "method":"GET", "path":"/books", "summary":"按书名查找图书",
    "requires_manual_registration":false,
    "parameters":[{"name":"q","in":"query","required":false,"type":"string","description":"待查询的书名"}],
    "responses":[{"status":"200","description":"成功返回图书列表"}]
  }],
  "needs_manual_endpoints": false,
  "warnings": [],
  "confirmed_endpoints": []
}
```

上传后需求列表和接口列表保持原状态。勾选可直接登记的候选并发送 `{"candidate_ids":["1"]}`，返回：

```json
{
  "project_id": "当前项目ID",
  "import_id": "导入记录ID",
  "endpoints": [{"candidate_id":"1","endpoint":{"id":"持久化接口ID","method":"GET","path":"/books","version":1}}]
}
```

相同项目内同一方法和相对路径复用已有端点及版本，包括先前手工登记的记录。对同一候选重复确认安全。确认列表中任一项无效时，整组返回错误。手工登记沿用 `POST P/endpoints`，例如 `{"method":"GET","path":"/rooms"}`。

OpenAPI 3 JSON 识别 GET、POST、PUT、PATCH、DELETE、HEAD 和 OPTIONS。候选保留来源路径、摘要、常用参数与响应说明，支持 `#/components/parameters/…` 和 `#/components/responses/…` 的单层本地引用。说明每项最多 240 字，参数和响应说明各最多 32 项。模板路径（如 `/rooms/{id}`）会显示为候选并标记 `requires_manual_registration: true`，操作者需要填写具体路径。服务器 URL、完整 Schema、默认值和示例均不进入候选。无 OpenAPI 时显示 `needs_manual_endpoints: true` 和手工登记提示。YAML 与需要展开的外部引用由操作者手工处理。

### 需求来源和片段

预览传 `{"path":"docs/requirements.md"}` 会返回前 16,000 个 Unicode 码点。长文档可传 `{"path":"docs/requirements.md","start":16000,"end":20000}` 预览另一段，或改选更短的文档。`start` 从 0 起，`end` 不包含在片段内。前端根据 JavaScript 字符偏移构造范围时，用 `Array.from(text)` 换算码点，UTF-8 BOM 已移除，换行保留。

保存时从预览复制 `import_id/path/start/end` 到 `source`，将用户确认或编辑后的正文作为 `text`。手输、单独导入 MD/TXT 可只发 `text`。刷新 `GET P/requirements` 会返回已保存正文及可选 `source`。现有 `PATCH P/requirements/{id}` 仍传 `{text}` 并递增版本，导入来源随需求保留。来源指向原始文档片段，正文可以包含用户编辑和补充答案。

郭泽强可从项目仓库 `get_requirement(project_id, requirement_id, expected_version=...)` 校验版本，再调用 `get_requirement_source(project_id, requirement_id)` 获取选定范围。用 `preview_import_document(project_id, import_id, path, start, end)` 读取原始片段，用 `get_import(project_id, import_id)` 的 `confirmed_endpoints` 将候选说明与持久化端点关联。来源为空时继续使用已保存需求。向模型传递的材料应限制在已选片段和确认接口中的必要说明。

### 限额和错误

| 状态 | 处理 |
| --- | --- |
| `413` | ZIP 请求体最多 8 MiB，最多 512 个条目，声明展开合计最多 48 MiB。读取正文时逐块检查实际字节，单文件最多 1 MiB。候选最多 256 条。 |
| `422` | ZIP 损坏、非法路径、链接、加密、非 UTF-8 文件名、选中文档正文编码无效、片段范围或候选项无效。改选文件或按提示重新打包。 |
| `404` | 当前项目找不到导入记录，或选定文件不在该导入的文档列表内。重新从当前项目选择。 |
| `415` | 请求类型不受支持。发送原始 ZIP 字节。 |

支持 Stored 和 Deflate，正文使用 UTF-8 或 UTF-8 BOM。服务器在 ZIP 内读取选定文档和 JSON，并保留 ZIP 以便重新预览。文件始终留在 ZIP 内，路径不会映射到服务器文件系统，包中程序不会被加载。延迟读取的文档在预览时才检验正文编码与校验和。非法上传不会创建导入记录，选中文档读取失败不会新增需求，确认失败不会写入部分端点。旧数据库启动时自动补齐新表。

## 联调材料

两套通用样本位于 [样本目录](../backend/tests/fixtures/project_import)。图书目录有 Markdown 和 OpenAPI，教室预约查询只有 TXT，走手工登记。两套样本用于 API 验收，正式项目需收到资料后另测。

从仓库根目录启动本机后端，使用独立 SQLite 文件，再执行实测：

```powershell
$env:TESTPILOT_DATABASE = 'backend/data/project-import-acceptance.sqlite3'
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

另一个终端进入同一仓库根目录：

```powershell
.venv\Scripts\python backend/scripts/verify_project_imports.py --output-dir artifacts/project-import
.venv\Scripts\python -m pytest backend/tests/test_project_imports.py -q
```

脚本输出 `book-catalog.zip`、`room-schedule.zip`、`http-evidence.json`。只生成上传样本时传 `--samples-only`。

协议参考 [Python ZIP 读取](https://docs.python.org/3.13/library/zipfile.html) 和 [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html)。
