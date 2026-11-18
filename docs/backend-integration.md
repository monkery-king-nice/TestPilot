# 后端基础与数据：模块接入说明

负责人：曾炜毅。数据模块只拥有 `projects`、`requirements`、`requirement_revisions`、`endpoints`、`environments` 表，其他成员负责各自的表。

## 共享连接和事务

从 HTTP 路由通过 `request.app.state.database` 取得 `Database`，通过 `request.app.state.project_repository` 取得 `ProjectRepository`。应用生命周期先初始化公共数据库和基础表，再调用显式注册的 `startup_hooks`。

```python
database = request.app.state.database
repository = request.app.state.project_repository
with database.connection(write=True) as connection:
    repository.require_project(project_id, connection=connection)
    source = repository.get_requirement(
        project_id, requirement_id, expected_version=requirement_version,
        connection=connection,
    )
    endpoint = repository.get_endpoint(
        project_id, endpoint_id, expected_version=endpoint_version,
        connection=connection,
    )
    # 使用同一个 connection 写入自己模块的表；所有SQL值使用参数绑定。
```

`connection(write=True)` 使用 `BEGIN IMMEDIATE`，成功自动提交，异常回滚，结束关闭连接。读取使用短读事务。
每个连接启用外键，等待锁10秒，数据库初始化启用 WAL。不要在事务中等待模型或HTTP请求。
同一组“校验版本、校验归属、保存记录”应使用同一个连接，避免校验与保存之间需求被修改。
模块建表自行提供初始化函数；在 startup hook 内使用该连接执行建表和迁移，不要重建公共表。
不要在同步连接内跨线程执行SQL，也不要在后台任务中保留请求结束后的连接。

## 内部查询契约

| 方法 | 行为 |
|---|---|
| `require_project(project_id, connection=None)` | 返回 `{id,name}`；不存在抛 HTTPException 404 |
| `get_requirement(project_id, requirement_id, expected_version=None, connection=None)` | 返回当前 `{id,text,version}`；跨项目/不存在404；预期版本过期409 |
| `get_requirement_version(project_id, requirement_id, version)` | 返回历史 `{id,text,version}`，仍校验当前项目归属；不存在404 |
| `get_endpoint(project_id, endpoint_id, expected_version=None, connection=None)` | 返回 `{id,method,path,version}`；跨项目/不存在404；预期版本不匹配409 |
| `load_text(project_id, requirement_id)` | 返回精确保留的需求原文；不在该项目下返回 None，供 Agent router 调用 |
| `read_environment(project_id, target="demo")` | 返回内部 `{username,password}` 字符串映射；项目不存在404，未配置或目标不支持422 |

需求每次 PATCH 均增加版本，包括提交相同正文；旧正文保存在 `requirement_revisions`。
Alpha约定没有端点修改/删除路由，端点版本目前固定为1；后续增加修改路由时需追加迁移和版本失效处理。
本模块不会修改其他成员的用例表。用例模块需在读取/确认/预检时比较当前需求和端点版本，设置 NEEDS_REVIEW 并拒绝旧版本执行；旧报告使用执行模块冻结的快照，不能用当前正文替代。

## 郭泽强：需求澄清接入

已同步主分支合入的 `feature/agent-clarify`，并在 `main.py` 显式注册其 `build_router(load_text, provider=None)`，使用本模块的真实需求读取函数：

```python
from .modules.agent.router import build_router
application.include_router(build_router(repository.load_text, provider=agent_provider))
```

默认agent_provider为None，沿用Agent模块的真实模型调用逻辑；本次验证未发送模型请求。
不要把环境凭证传给Agent。测试可在create_app传固定agent_provider，其输出是测试替身，不能算真实模型评估。
已验证读到最新需求原文、跨项目引用在模型调用前被拒绝，以及模型错误时基础数据仍可读取。

## 周兴宇、沈冠宇：执行与预检接入

已检查远端 `feature/runs-executor` 的 `RunDependencies` 协议：

```python
class SharedRunDependencies:
    def __init__(self, project_repository, cases_service):
        self.projects = project_repository
        self.cases = cases_service

    def preflight(self, project_id, cases):
        # cases_service由用例模块提供；失败转成执行模块PreflightRejected。
        return self.cases.preflight(project_id, cases)

    def read_environment(self, project_id, target):
        return self.projects.read_environment(project_id, target)
```

上述为接入示意，未提供虚构的真实 `cases_service`。真实预检未合并，执行路由目前不注册。
创建执行服务时，将本模块 `settings.database_path` 和 `settings.demo_base_url` 分别传给该模块的数据库和服务端目标配置；公共数据和 runs 表可使用同一个 SQLite 文件。
执行器读取凭证后应及时脱敏，不写入执行快照、公开响应或日志。未配置环境时，在发请求前转成明确的预检拒绝或执行错误。

## 显式路由和生命周期

`create_app(settings=None, routers=(), startup_hooks=(), agent_provider=None)` 可注册已就绪的 APIRouter 和初始化函数，并在测试中注入Agent provider。
生产入口为 `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`。
`startup_hooks` 是同步、短时的初始化操作；未来执行器如需启动/关闭 worker，应在公共 lifespan 中成对管理，不要通过导入启动后台线程。
应用实例状态有 `settings`、`database`、`project_repository`；未来合入时再加入 `run_service`，不预置假的执行器。

## 前端

```javascript
// vite.config.js 的 server.proxy
proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } }
```

创建返回201；列表为直接数组；错误统一为 `{"detail":"原因"}`。
GET/PUT environment都不返回凭证，前端显示 `configured_keys`，编辑时重新输入值；PUT为完整替换，需要同时提交username、password。
