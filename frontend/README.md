# TestPilot 前端

负责人：陈睿涛（前端：环境、执行与结果）。范围 FR-03、07、08、09、10 的页面，核心目录 `frontend/src/features/runs/`。

技术栈：Vue 3 + TypeScript + Element Plus + Vite，开发代理 `/api` → `127.0.0.1:8000`。

林彦羽负责第一阶段的项目入口、需求和用例页面。演示模式下，编辑页和执行页各用一套样例，编辑页新增的用例不会同步到执行页。

## 目录结构

```
frontend/
├── vite.config.ts                 # 开发服务器与 /api 代理
├── index.html
└── src/
    ├── main.ts / App.vue          # 最小应用外壳（与林彦羽的 authoring 合并）
    ├── router/index.ts            # 路由（项目、需求、用例、环境、执行与详情）
    ├── api/
    │   ├── types.ts               # 共享类型（RunDetail / CaseDraft / Analysis 等）
    │   ├── client.ts              # fetch 封装 + 统一错误 {"detail":...}
    │   ├── config.ts              # USE_MOCK 开关
    │   └── runs.ts                # 环境/用例/运行/分析/报告 API
    ├── mocks/
    │   ├── runDetail.samples.ts   # 四类状态 RunDetail 示例（联调统一样例）
    │   └── mockAdapter.ts         # 内置 Mock 适配层（无后端时独立演示）
    └── features/runs/
        ├── index.ts / routes.ts   # 路由与注册说明（给林彦羽）
        ├── EnvironmentView.vue    # 环境页：配置凭证，保存后仅显示字段名
        ├── RunListView.vue        # 执行页：已确认用例+版本，目标/条数/执行按钮
        ├── RunDetailView.vue      # 详情页：轮询、四类统计、逐步骤差异、下载
        ├── components/            # OutcomeStats / StepResultTable / CaseResultCard / AnalysisPanel
        ├── composables/           # useEnvironment / useRunPolling
        └── outcomes.ts            # PASS/FAIL/ERROR/BLOCKED 展示元数据
```

## 启动命令（从仓库根目录）

```bash
cd frontend
npm ci               # 首次
npm run dev          # 开发服务器 http://127.0.0.1:5173
```

生产构建与类型检查：

```bash
npm run build        # 产物 frontend/dist
npm run typecheck    # vue-tsc --noEmit
npm test             # 评审样例 + 失败分析乱序 + 执行页目标/运行前检查
npm run test:analysis  # 仅失败分析乱序回归（A→B 切换 / 同用例重试）
npm run test:runs      # 仅目标文案、需求版本汇总与运行前检查
```

## Mock 模式与真实联调

- **默认（开发模式）**：`USE_MOCK = true`，使用 `src/mocks/mockAdapter.ts`，无需后端即可演示完整流程。
- **切真实后端**：在 `frontend/.env.local` 写入 `VITE_USE_MOCK=false`，前端经 `/api` 代理到 `127.0.0.1:8000`。

Mock 运行进度按时间推进：发起运行后 `QUEUED → RUNNING → COMPLETED`，用于演示轮询与刷新恢复。

## 演示步骤（实测）

1. 打开 `http://127.0.0.1:5173`，在项目列表选择「接口测试演示项目」。
2. 进入「环境配置」：输入用户名/密码 → 保存 → 页面只显示已配置字段名 `username`、`password`（不显示值）。
3. 进入「执行与结果」：看到 5 条已确认用例及版本 → 点击「执行所选」→ 跳转运行详情。
4. 详情页轮询：状态依次「排队中 → 运行中 → 已完成」，最终展示四类统计
   `PASS 2 / FAIL 1 / ERROR 1 / BLOCKED 1`。
5. 展开 FAIL/ERROR/BLOCKED 用例，可看到每步 HTTP 状态、耗时、脱敏摘要、断言差异、错误阶段；点击「AI 失败分析」查看原因/证据/建议。
6. 点击「下载 HTML 报告」，得到 `testpilot-report-<run_id>.html`，可直接用浏览器打开。
7. 刷新详情页：从后端（Mock）恢复运行状态；终态停止轮询。

## 验收对照

- ✅ 从确认执行到查看详情和下载：RunListView → RunDetailView → 下载 HTML。
- ✅ 准备失败显示 BLOCKED：样例 `未配置凭证时登录被阻断`（setup 未通过，主步骤 BLOCKED）。
- ✅ 模型不可用时结果和下载仍可用：报告/结果来自冻结快照，不依赖 Agent。
- ✅ 四类状态结果页样例：`src/mocks/runDetail.samples.ts`。

## 未完成 / 待联调项

- **测试环境目标（第三阶段）**：环境页支持 `demo`（团队演示服务）与 `local`（项目已启动的本地服务，需 `service_id` + 回环 `base_url`）；保存后显示目标、服务标识、地址与环境版本。RunDetail 的 `target` 来自批次冻结快照，历史批次不会串用项目当前环境。
- **执行前检查**：执行页同屏显示项目名、执行目标、需求版本与已确认用例；缺接口/环境/确认时给出补充入口（`runContext.mjs`，回归见 `runContext.test.mjs`）。
- **失败区分**：步骤表的断言差异标注「测试断言失败」，分析接口失败标注「模型分析失败」；环境变更导致的整批 ERROR 显示 `error_stage=environment_changed` 提示。
- 真实后端（曾炜毅 environment、沈冠宇 cases/report、周兴宇 runs、郭泽强 analysis）联调后验证字段一致性；样例中的 `req-1/ep-login/ep-me` 需替换为真实 ID。
- 与周兴宇对齐 RunDetail 的 `counts` 终态与 `results` 顺序、脱敏字段命名。
- 下载目前由前端拼接 HTML 文本触发（Mock 直接生成；真实后端 GET report 返回 text/html）。
- **AI 失败分析**：真实模式已接入后端 `POST .../runs/{run_id}/analysis`；接口不可用时显示可读原因，统计与当前批次下载不受影响。请求用「请求序号 + 项目/批次/用例」双重校验，A 批次晚到的响应不会显示在 B 批次上（见 `useAnalysisRequest.ts` 与 `useAnalysisRequest.test.ts`）。
- 详情页轮询：晚到响应会按「轮询令牌 + 批次 ID」丢弃，不会覆盖当前批次；地址中的批次/项目变化时重新加载。

## 接口约定

见 `docs/api-alpha.md`（曾炜毅维护）或 `TestPilot-Alpha-六人开发包/01-共同接口约定.md`。
