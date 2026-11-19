# 项目需求澄清与用例生成联调

先保存当前需求，再将返回的 `id` 和 `version` 传给 Agent。调用方应绑定两者，避免用户切换或补充需求后显示旧结果。

```json
{"requirement_id":"已保存需求的 ID","requirement_version":2}
```

- `POST /api/projects/{project_id}/agent/clarify` 返回 `status` 和 `questions`。每条保留 `quote`、`question`。当引用只出现在所选原始片段时，增带 `source_path`。
- 用户回答后，页面把问答和正文合并成需求文本，沿用 `PATCH /api/projects/{project_id}/requirements/{id}` 保存。成功后，以返回的新版本调用澄清与生成。
- `POST /api/projects/{project_id}/agent/generate` 返回 `drafts`。用户审查并手动确认，生成接口本身不会保存或执行用例。
- `409` 表示需求版本变更，页面重新读取当前需求，由用户决定重试。`422` 的 `detail` 可能是缺少端点或缺少可验证的预期，页面可引导继续补充。

已有客户端只传 `requirement_id` 时仍可调用，服务端使用请求开始时的已保存版本。手工需求沿用已登记的接口，有 ZIP 来源时另附所选片段的前 4,000 个字符及已确认接口的有限说明。接口凭据保留在本机环境。
