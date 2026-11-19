# Alpha v1 接口约定与当前实现状态

本文件保留六人开发包中的共同契约。当前分支包含项目基础与数据、需求澄清，以及沈冠宇负责的用例/确认/复核/报告模块，并通过真实用例预检接通已合入的执行器，不代表全组路由均已合入。
本文件是本分支交接版本，尚待全组联调冻结；后续共同修改需同步调用方。

## 本分支可调用接口

P = `/api/projects/{project_id}`。

| 方法 | 路由 | 状态与响应 |
|---|---|---|
| GET | `/api/projects` | 200，`[{id,name}]` |
| POST | `/api/projects` | 201，`{id,name}` |
| GET | `P/requirements` | 200，`[{id,text,version}]` |
| POST | `P/requirements` | 201，`{id,text,version:1}` |
| PATCH | `P/requirements/{id}` | 200，`{id,text,version:上一版本+1}` |
| GET | `P/endpoints` | 200，`[{id,method,path,version}]` |
| POST | `P/endpoints` | 201，`{id,method,path,version:1}` |
| GET | `P/environment` | 200，`{target,service_id,base_url,configured_keys:[...]}` |
| PUT | `P/environment` | 200，同GET，不回传环境值 |
| GET | `/api/health` | 200，`{status:"ok"}` |
| POST | `P/agent/clarify` | 请求`{requirement_id}`，读取真实需求库，返回`{status,questions}`；缺模型配置或模型调用失败502 |
| POST | `P/agent/generate` | 请求 `{requirement_id}`，返回 `{drafts:[CaseDraft]}`。资料不足返回 422。通过用例接口另行保存和确认。 |
| POST | `P/runs/{run_id}/analysis` | 请求 `{case_id}`，返回 `{category,reason,evidence,suggestion}`。分析已结束批次中的非 PASS 结果。 |

- 创建请求字段与下文共同契约相同，输入严格校验，拒绝多余字段。
- 项目名1–100字符；需求正文1–16000字符且不能全空白，保留原文空白和换行。
- 所有id为UUID字符串，需求和接口初始version为1。
- 端点只接受HTTP方法GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS（统一转大写），相对路径1–2048字符；拒绝完整URL、双斜线主机、目录跳转、反斜线、片段和控制字符。
- 环境PUT完整替换。原请求 `{target:"demo",secrets:{username,password}}` 不变；本地服务使用 `{target:"local",service_id,base_url,secrets:{username,password}}`。`local` 只接受带显式端口的回环 HTTP(S) 根地址，不允许用户凭证、查询或片段。secrets必须同时提供非空username、password，各不超过4096字符。公开响应仅含非敏感目标和字段名，排序为password、username。
- 项目存在且未配置环境时，GET environment返回空configured_keys；创建运行批次返回422且不回退默认demo，内部read_environment也会拒绝执行。
- 无项目/不存在或跨项目需求：404；字段不合法：422；内部版本不匹配：409；SQLite冲突409，数据库暂不可用503；其他内部错误500。错误始终为字符串detail，不回显原始输入。
- 需求历史版本与端点版本通过内部函数查询，见[接入说明](backend-integration.md)。Alpha共同契约未约定项目修改、删除及端点修改，本分支未增加这些路由。
- 需求变更后保存新版本；用例模块在读取、确认和执行预检时识别NEEDS_REVIEW，不修改历史运行快照。

## 用例、执行与报告（本分支新增接通）

`GET/POST P/cases`、`GET/PATCH P/cases/{id}`、`POST P/cases/{id}/confirm`、`POST P/runs`、`GET P/runs/{run_id}`、`GET P/runs/{run_id}/report` 均已注册。输入遵循下方共同契约；用例输出增加 `confirmed_version/confirmed_at/reasons` 供前端展示确认记录和逐条原因。PATCH接受完整CaseDraft，不接受客户端设置状态。`GET/POST P/cases/{id}/manual-checks` 单独保存按版本关联的人工清单和证据，不混入自动执行统计。

字段样例、错误码、预检签名和实测情况见[用例模块交付说明](../backend/app/modules/cases/README.md)。报告仅供已结束批次下载；进行中409，不存在或跨项目404。

## Agent 生成与分析

生成使用当前需求文本和项目登记的端点。失败分析只读取已保存的步骤状态、错误阶段和脱敏断言差异。模型调用失败返回 502，原有运行结果和报告仍可读取。
输入、输出及状态约定见下文原始公共契约。

## 六人共用的 Alpha v1 接口约定

项目是智测领航 TestPilot，帮助基础开发者把模糊需求变成有依据、可复核的测试。当前从零开发。技术栈为 Vue 3 + Element Plus、FastAPI、SQLite、httpx。下述接口为本次冲刺建议冻结的实现约定。课程依据：[选题博客](https://www.cnblogs.com/yesx/p/23432327) · [Alpha 作业要求](https://edu.cnblogs.com/campus/fzu/2026-01SoftwareEngineeringandSoftwareEngineeringPractice/homework/16793)。

**共同演示**：从“系统支持登录并返回用户信息”开始。资料缺失时，Agent 引用需求原文提问。用户补充：POST /auth/login 的 body 使用 username、password，成功返回 200 和非空 token；错误密码返回 401 和 code=INVALID_CREDENTIALS。GET /me 使用 Bearer token，返回 200 和 user.id=demo-user，耗时上限 3000 ms。只向团队自己的演示服务发请求。演示服务与平台 API 分开启动。成功登录 → 查本人信息两步是一条用例。错误密码且预期 401 是另一条可以 PASS 的用例。准备阶段没拿到 token 时，主步骤标记 BLOCKED。真实值偏离已确认预期时保留 FAIL，Agent 只能解释结果。

**路径与数据**：以下 P 代表 /api/projects/{project_id}，所有 id 为字符串，version 为从 1 开始的整数。单资源返回对象，列表直接返回 JSON 数组；错误统一为 {"detail":"给用户看的原因"}。创建返回 201，创建运行批次返回 202。服务端按项目校验所有引用。前端通过 /api 访问，开发代理指向 127.0.0.1:8000，演示服务默认 127.0.0.1:8010。以下请求和响应字段供六方共同使用：

| 提供者 | 路由 | 请求与响应 |
|---|---|---|
| 曾炜毅 | GET/POST /api/projects | 创建传 {name}，返回 {id,name} |
| 曾炜毅 | GET/POST P/requirements，PATCH P/requirements/{id} | 创建或修改传 {text}，返回 {id,text,version}；每次修改版本加一 |
| 曾炜毅 | GET/POST P/endpoints | 创建传 {method,path}，返回 {id,method,path,version}；path 是相对演示服务的路径 |
| 曾炜毅、周兴宇 | GET/PUT P/environment | demo 写入 {target:"demo",secrets:{username,password}}；local 另传 service_id、base_url。读取仅返回非敏感 {target,service_id,base_url,configured_keys}；仅服务端执行器能读取环境值 |
| 郭泽强 | POST P/agent/clarify | 传 {requirement_id}，返回 {status:"NEEDS_INFO"或"READY",questions:[{quote,question}]}；用户补充答案由前端 PATCH 需求 |
| 郭泽强 | POST P/agent/generate | 传 {requirement_id}，返回 {drafts:[CaseDraft]}。资料不足返回 422 和原因；Agent 只产出候选 |
| 沈冠宇 | GET/POST P/cases，PATCH P/cases/{id}，POST P/cases/{id}/confirm | POST/PATCH 传 CaseDraft，返回含 id、version、status 的用例；confirm 传 {version}；前端将选中的候选 POST 一次保存 |
| 周兴宇 | POST P/runs，GET P/runs/{run_id} | 点击执行后传 {cases:[{id,version}]}，返回 {run_id,status:"QUEUED"}；GET 返回下述 RunDetail |
| 郭泽强 | POST P/runs/{run_id}/analysis | 传 {case_id}，仅分析已保存的脱敏结果，返回 {category,reason,evidence:[字符串],suggestion} |
| 沈冠宇 | GET P/runs/{run_id}/report | 返回可下载的 text/html，基于运行快照，直接用浏览器打开或下载 |

CaseDraft 形状见下。样例中的 req-1、ep-login、ep-me 必须替换为实际创建的 ID。绑定 endpoint_id 后服务端查找 method/path。变量只支持 env.<key> 和 steps.<步骤名>.<变量> 两类引用，字段路径仅支持以点分隔的对象键。不要执行表达式或用户脚本。

```json
{
  "title":"登录后获取本人信息",
  "requirement_id":"req-1","requirement_version":2,
  "expected_basis":"已确认需求：返回本人编号 demo-user",
  "steps":[
    {"name":"login","phase":"setup","endpoint_id":"ep-login","endpoint_version":1,
     "headers":{},"body":{"username":"{{env.username}}","password":"{{env.password}}"},
     "assertions":[{"type":"status","expected":200},{"type":"nonempty_string","path":"token"}],
     "extract":{"token":"token"}},
    {"name":"me","phase":"test","endpoint_id":"ep-me","endpoint_version":1,
     "headers":{"Authorization":"Bearer {{steps.login.token}}"},"body":null,
     "assertions":[{"type":"status","expected":200},{"type":"json_equals","path":"user.id","expected":"demo-user"},{"type":"elapsed_ms_lte","expected":3000}],
     "extract":{}}
  ]
}
```

用例状态 DRAFT、NEEDS_INFO、READY、CONFIRMED、NEEDS_REVIEW。执行前由沈冠宇提供同一个预检入口给确认服务和执行器调用。整批 1–20 条，每例 1–5 步。过期版本、未确认、未配置项目环境或引用失效拒绝整批并返回原因，不发请求。同时只允许一个运行中批次，冲突返回 409。RunDetail 包含 run_id、status、target、counts（PASS/FAIL/ERROR/BLOCKED 四个键，初始均为 0）、results 数组。新批次的 target 为 {kind,service_id,base_url}，在创建时冻结；旧数据库无目标批次为 null 并保留 demo 行为。每条已结束结果为 {case_id,title,outcome,steps:[{name,phase,http_status,elapsed_ms,request_summary,response_summary,assertion_diffs,error_stage}]}。summary 为脱敏字符串，diffs 为字符串数组，不可用的标量用 null。批次状态 QUEUED/RUNNING/COMPLETED/INTERRUPTED，结束时四类数量总和等于所选用例数。内部冻结快照顶层同样含 target，报告与 AI 分析读取同一份冻结证据，不读取项目当前环境覆盖历史目标。

**并行开发**：先看当前仓库、已有分支和接口文档。各自在下文指定目录开发。未合入的依赖用清楚标记的测试替身，联调时切到真实 API；真实演示和测试替身分别记录。共用文件由负责人合并，接口变更先和调用方确认。勿提交 .env、API key、密码、token、含敏感信息的日志。每人提交代码时附启动命令、实测步骤、实际输出和未完成项。
