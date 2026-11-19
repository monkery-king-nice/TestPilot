# 沈冠宇：用例、预检、人工检查记录与 HTML 报告

## 已实现的内容

- 保存、列表、单条读取、完整编辑用例；编辑递增版本并保留旧版本。
- 用例返回 `id/version/status/confirmed_version/confirmed_at/reasons`。结构合法但内容不完整的草稿可保存为 `NEEDS_INFO`；校验通过为 `READY`；确认后为 `CONFIRMED`。
- 确认和执行共用 `_checked_snapshot` 与 `validate_draft`：校验需求和接口归属、版本、预期依据、断言、前序变量来源与环境变量配置。
- 需求、接口版本变化，或已确认用例的引用失效，在读取、确认和执行预检时识别 `NEEDS_REVIEW`。编辑已确认用例后也需重新确认；复核时应更新绑定的需求/接口版本，再确认最新用例版本。
- 执行预检按请求顺序返回冻结的用例、需求原文和接口快照；任何一条失败都拒绝整批，不创建运行批次，不发送目标请求。环境只检查已配置键，快照不含运行时环境值。
- 接通已合入的真实执行器。应用生命周期中初始化、恢复批次并关闭后台 worker；未改动执行器算法。
- 报告只读已结束批次的冻结快照、统计与脱敏执行证据，转义全部动态文本，可直接下载并用浏览器打开。历史报告不会随当前用例、需求或环境修改而重写。
- 人工检查清单、通过条件和证据按用例版本单独追加保存；不把人工填写的 PASS 当作自动执行结果。

## 从仓库根目录运行

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

接口文档：`http://127.0.0.1:8000/docs`。基础数据、用例和执行结果共用 `TESTPILOT_DATABASE` 指定的 SQLite 文件，默认 `backend/data/testpilot.sqlite3`。`DEMO_BASE_URL` 默认 `http://127.0.0.1:8010`；演示服务的启动方式见仓库 `demo_service/README.md`。真实执行需要先配置该项目的演示环境。

自动化测试及独立进程 HTTP 验收：

```powershell
$env:PYTHONUTF8 = '1'
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m ruff check backend/app/modules/cases backend/app/modules/reports backend/app/main.py backend/tests/cases backend/scripts/verify_cases_reports.py
.venv\Scripts\python backend/scripts/verify_cases_reports.py --output-dir artifacts/cases-reports
```

最后一条命令在随机本机端口启动独立 Uvicorn 进程和团队演示服务，用临时数据库运行验收，正常结束后关闭服务。无需预先启动8000/8010端口，不修改现有演示库，不需要模型密钥。

产出 `acceptance.json`、`success-report.html`、`outcomes-report.html`。文件含实际请求的脱敏结果和断言差异，不含临时环境密码及登录 token。`artifacts/` 已由仓库忽略规则排除。

## 接口

P = `/api/projects/{project_id}`。创建返回201，读取/修改/确认返回200。错误为字符串 `detail`。

| 方法与路径 | 请求 / 行为 |
|---|---|
| `GET P/cases` | 直接返回用例数组，附校验原因 |
| `POST P/cases` | `CaseDraft`，保存一次候选，初始version=1 |
| `GET P/cases/{id}` | 读取单条并重新检查引用版本 |
| `PATCH P/cases/{id}` | 完整 `CaseDraft`，每次version+1；不接受客户端指定状态 |
| `POST P/cases/{id}/confirm` | `{ "version": 1 }`，记录人工确认；版本不一致409，不完整422，依赖过期409 |
| `POST P/runs` | `{ "cases": [{ "id": "用例ID", "version": 1 }] }`，202；整批1–20条，预检失败422，运行互斥409 |
| `GET P/runs/{run_id}` | 读取真实执行结果，四类数量为PASS/FAIL/ERROR/BLOCKED |
| `GET P/runs/{run_id}/report` | HTML附件；批次未结束409，不存在或跨项目404 |
| `POST P/cases/{id}/manual-checks` | `{ "version": 1, "items": [{ "check": "页面登录按钮", "pass_condition": "点击后显示结果", "outcome": "NOT_CHECKED", "evidence": "" }] }` |
| `GET P/cases/{id}/manual-checks` | 历次人工记录数组，含记录时间、用例版本和当时用例内容 |

人工记录 `outcome` 为 `PASS/FAIL/NOT_CHECKED`；已检查项目必须填写证据。按旧用例版本提交返回409，不覆盖旧记录。不包含文件上传接口，`evidence` 为文字描述或证据路径/链接。

### CaseDraft 示例（给 Agent 和前端）

下列三个ID必须替换成当前项目实际创建的需求和端点ID，版本应与实际一致。请求体只传这些业务字段；不要把用例返回的id/status/reasons直接原样作为编辑请求。

```json
{
  "title": "登录后获取本人信息",
  "requirement_id": "实际需求ID",
  "requirement_version": 1,
  "expected_basis": "已确认需求：正确密码登录返回200和token，本人编号为demo-user",
  "steps": [
    {
      "name": "login", "phase": "setup",
      "endpoint_id": "实际登录端点ID", "endpoint_version": 1,
      "headers": {},
      "body": {"username": "{{env.username}}", "password": "{{env.password}}"},
      "assertions": [{"type": "status", "expected": 200}, {"type": "nonempty_string", "path": "token"}],
      "extract": {"token": "token"}
    },
    {
      "name": "me", "phase": "test",
      "endpoint_id": "实际本人信息端点ID", "endpoint_version": 1,
      "headers": {"Authorization": "Bearer {{steps.login.token}}"}, "body": null,
      "assertions": [
        {"type": "status", "expected": 200},
        {"type": "json_equals", "path": "user.id", "expected": "demo-user"},
        {"type": "elapsed_ms_lte", "expected": 3000}
      ],
      "extract": {}
    }
  ]
}
```

每例1–5步，至少一个test；setup必须在test前。变量仅支持 `{{env.<key>}}` 和 `{{steps.<前序步骤名>.<提取变量>}}`；不支持表达式或用户脚本。字段路径为 `user.id` 这样的点分隔对象键，不支持 `$.user.id`、数组下标或表达式。断言预期值为静态JSON值，不展开变量。`json_equals` 可以显式比较null，但不能省略expected。

### 执行器预检签名（给执行模块）

```python
from app.modules.cases.service import CaseService
from app.modules.runs.models import CaseRef

# 主应用已绑定为 app.state.cases_service，并直接传给 RunService。
snapshots: list[dict] = cases_service.preflight(
    project_id, [CaseRef(id=case_id, version=version)]
)
```

失败抛 `runs.dependencies.PreflightRejected`，其 `reasons: list[str]` 为逐条可读原因。成功快照包含 `case_id/title/version/status/confirmed_version/confirmed_at/requirement_id/requirement_version/expected_basis/steps/requirement/endpoints`。

报告读取同一个 `app.state.run_service.get_frozen_snapshot(project_id, run_id)` 和 `get_run()`，没有从当前用例表重建历史依据。确认只保证资料与结构齐全，预期业务含义仍由用户人工确认。

## 已验证与尚待团队联调

本次在Python3.13、Windows本机验证：新增28项测试通过；全仓库89项测试通过；本模块和共享入口的Ruff检查通过。独立进程真实HTTP验收8项通过：未确认拦截、缺断言拦截、未定义变量拦截、登录查询成功、四类结果、人工清单保存、需求过期拦截、历史报告字节一致。

真实演示结果：成功登录与查询为PASS；错误密码且预期401也为PASS；人为设置不匹配用户编号为FAIL；准备登录失败后主步骤为BLOCKED；运行时提取不存在字段为ERROR。后两种异常均保留实际错误阶段。全部结果使用团队真实执行器和本机演示服务，没有把测试替身算作真实执行。

尚待：前端分支与这些真实API联调；Agent后续generate接口产出的候选按本示例落库。真实模型接入/定制效果评估不属于此模块，本次没有调用模型。公共契约暂无端点编辑路由，因此接口版本失效通过数据库版本变更进行自动化验证；需求变更失效已通过真实PATCH请求验证。人工记录接口已验证，具体页面人工检查需由实际操作者填写证据。

## 站会展示与证据

1. 运行上面的HTTP验收脚本，展示终端8项检查结果及 `acceptance.json`。
2. 打开 `success-report.html` 展示需求版本、用例版本、断言和脱敏证据。
3. 打开 `outcomes-report.html` 展示四类统计、FAIL差异以及BLOCKED主步骤未发送请求。
4. 接口文档中可展示 `GET P/cases` 的 `NEEDS_INFO/NEEDS_REVIEW` 和对应原因。

保存终端实际输出、两份HTML和acceptance.json；站会如需截图，请截本人实际运行的界面。

## 第二阶段验收：用例过期与历史报告

从仓库根目录运行。脚本会启动独立后端与本地演示服务，使用临时数据库和一次性测试凭证。

```powershell
$env:PYTHONUTF8 = '1'
.venv\Scripts\python backend/scripts/verify_cases_reports.py --output-dir artifacts/phase2-review-history
```

1. 创建需求 v1，确认用例 v1，运行批次 A。打开 `success-report.html`，检查登录和查询两步均为 200，批次为 PASS。
2. 更新同一需求到 v2，重新读取旧用例。预期返回 `NEEDS_REVIEW` 和需求版本过期原因。把另一条已确认用例排在旧用例前提交，预期整批返回 422，演示服务收到 0 次请求。
3. 更新同一用例的需求版本、预期依据和断言，保存为 v2 并确认。即使 v2 已确认，提交 v1 的版本号仍会返回 422，演示服务收到 0 次请求。提交 v2 后，批次 B 的两步均为 200，结果为 PASS。
4. 对照 `review-A-redownload.html` 和 `review-B.html`。再次下载的 A 仍显示原批次 ID、需求 v1、用例 v1、原预期依据和原结果。B 显示新批次 ID、需求 v2、用例 v2 和新预期依据。脚本核对报告可见字段和批次结果，不比较报告生成时间。

`acceptance.json` 记录了项目、需求、用例和 A/B 批次 ID、版本、预期依据、步骤 HTTP 状态及两次拒绝响应。数据库会随脚本退出清除，复测时会生成新的 ID。

以合入 PR #11 的 `7ccc4e5` 为基线，本机真实 HTTP 已验证上述流程。另在 `VITE_USE_MOCK=false` 的独立项目中确认，页面会显示旧用例待复核和过期原因，采用新需求版本并重新确认后可从执行页运行 v2，结果为 PASS。共享验收环境仍待队友复测。
