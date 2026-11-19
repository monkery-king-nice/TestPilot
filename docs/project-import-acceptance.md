# 项目 ZIP 导入与执行回归

负责人为沈冠宇。两套样本沿用 `backend/tests/fixtures/project_import` 的需求和接口资料。样本服务仅监听回环地址，可单独启动。

| 样本 | ZIP 内材料 | 接口 | 服务响应 |
| --- | --- | --- | --- |
| 图书目录 | `docs/requirements.md`、`api/openapi.json` | `GET /books`，确认候选后登记 | 省略 `limit` 时最多返回一本，响应包含 `service` |
| 教室预约 | UTF-8 文本 `需求.txt` | `GET /rooms`，手工登记 | 样本当天设为节假日，HTTP 200 返回 `slots: []` 和 `service` |

## 自动回归

在仓库根目录运行。Python 3.11+，依赖安装在本地虚拟环境。每次运行用独立的临时 SQLite 和随机空闲端口。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements-lock.txt -r backend/requirements-dev.txt
$env:PYTHONUTF8 = '1'
.venv\Scripts\python -m pytest backend/tests/test_project_import_acceptance.py -q --basetemp artifacts/import-acceptance
.venv\Scripts\python backend/scripts/verify_cases_reports.py --output-dir artifacts/legacy-demo
```

`artifacts/import-acceptance` 下的测试目录包含两份 ZIP、运行 JSON、HTML 报告和反例记录。旧登录 demo 的四类结果和报告在 `artifacts/legacy-demo`。模型替身只用于澄清和生成断言，执行器通过 HTTP 请求样本服务。缺密钥测试验证了真实模型客户端的配置错误。

| 检查 | 预期 |
| --- | --- |
| 上传、预览、保存、重新读取 | 两个项目各自保存来源和需求，A 确认 OpenAPI 候选，B 手工登记 |
| 澄清与补充 | 追问引用选中原文，v2 保存答案后可以生成候选，基于旧版本修改或调用 Agent 返回 409 |
| 人工确认与隔离 | 未确认或过期用例返回 422，混用其他项目的导入、需求或接口被拒绝 |
| 按项目发送 HTTP | A 只请求图书服务，B 只请求预约服务。测试服务日志和响应标记对应 |
| 目标切换 | 旧环境版本返回 409，重新确认当前环境后可以执行。旧报告重下载与原报告字节一致 |
| 报告与脱敏 | 批次、项目 ID、需求版本和冻结目标一致，密码和响应 token 不出现在证据 |
| 反例 | 坏包返回 422，缺文档可手输，未配模型返回 502，故意错断言记 FAIL，目标停机记 ERROR |

## 页面手工复现

生成上传文件，在两个独立终端运行样本服务。

```powershell
.venv\Scripts\python backend/scripts/verify_project_imports.py --samples-only --output-dir artifacts/acceptance-zips
python backend/scripts/acceptance_sample_service.py book-catalog --port 8121
python backend/scripts/acceptance_sample_service.py room-schedule --port 8122
```

1. 按 README 启动真实页面。新建两个项目，分别选择对应的 ZIP，再选包内需求并保存为 v1。图书项目确认 `GET /books` 候选，预约项目手工登记 `GET /rooms`。
2. 配置「项目本地服务」。图书项目使用 `book-catalog` 和 `http://127.0.0.1:8121`，预约项目使用 `room-schedule` 和 `http://127.0.0.1:8122`。样本默认无需填写凭据。
3. 为图书项目确认一条状态码等于 200 的 v1 用例并运行，下载报告。补充“未传 limit 时最多返回 1 本图书。”并保存为 v2。旧用例直到复核、更新版本并重新确认才可执行。新用例可断言 `books` 等于 `["软件工程"]`。
4. 为预约项目补充“节假日返回 200 和空时段列表。”，断言 `slots` 等于 `[]`。可复制并确认一条故意错断言的用例，将预期改为 `["09:00"]`。该反例应展示实际空列表。
5. 可用另一端口再启动一份图书服务并设置新服务标识。重新执行后，对照旧批次 HTML 的需求版本、目标地址和批次 ID。停止预约服务后再次运行，核对连接故障。
6. 正式项目按同样步骤记录原始文件名、启动方式、需求 v1/v2、服务日志、实测用例和批次 ID。真实 DeepSeek 需在启动 TestPilot 时配置本机密钥。
