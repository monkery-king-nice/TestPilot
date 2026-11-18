export const states = { DRAFT: '草稿', NEEDS_INFO: '待补充', READY: '待确认', CONFIRMED: '已确认', NEEDS_REVIEW: '待复核' };
export const requirements = [
 ['正确密码登录', '正确密码调用 POST /auth/login，返回 200 和非空字符串 token。'],
 ['错误密码被拒绝', '错误密码返回 401，code 为 INVALID_CREDENTIALS。'],
 ['空密码参数校验', '空字符串密码返回 400，code 为 VALIDATION_ERROR。'],
 ['获取当前用户信息', '有效 Bearer token 调用 GET /me，返回 200 且 user.id 等于预置用户编号。'],
 ['未授权访问被拒绝', '缺失或无效 Bearer token 调用 GET /me，返回 401。'],
 ['分页大小边界', 'page_size 为 1 至 100 的整数返回 200，范围外返回 400。']
].map(([title, text], i) => ({ id: `R-DEMO-0${i + 1}`, title, text, version: 1, source: '演示需求.md', line: i + 1 }));
export const apis = [
 { id: 'API-01', name: '账号登录', method: 'POST', path: '/auth/login', version: 1, response: '200: token 为非空字符串；400 / 401: code 为业务错误码' },
 { id: 'API-02', name: '当前用户', method: 'GET', path: '/me', version: 1, response: '200: user.id 为预置用户编号；401: 未授权' },
 { id: 'API-03', name: '分页列表', method: 'GET', path: '/items', version: 1, response: '200: items 数组；400: 参数范围错误' }
];
export function seedCases() {
 return [
 ['正确凭证登录并读取用户', '正常', '高', 'CONFIRMED', 0, 'API-02', 200, '{"Authorization":"Bearer ${steps.login.token}"}', '$.user.id', '1001'],
 ['错误密码返回鉴权错误', '异常', '高', 'CONFIRMED', 1, 'API-01', 401, '{"username":"${env.demo_user}","password":"wrong-demo"}', '$.code', 'INVALID_CREDENTIALS'],
 ['空密码返回参数校验错误', '异常', '高', 'READY', 2, 'API-01', 400, '{"username":"${env.demo_user}","password":""}', '$.code', 'VALIDATION_ERROR'],
 ['无凭证访问用户信息', '异常', '中', 'CONFIRMED', 4, 'API-02', 401, '{}', '$.code', 'UNAUTHORIZED'],
 ['分页下界 page_size = 1', '边界', '中', 'CONFIRMED', 5, 'API-03', 200, '{"page_size":1}', '$.items', 'array'],
 ['分页上界 page_size = 100', '边界', '中', 'NEEDS_INFO', 5, '', 200, '{"page_size":100}', '$.items', 'array'],
 ['分页越界 page_size = 101', '边界', '中', 'DRAFT', 5, 'API-03', 400, '{"page_size":101}', '$.code', 'VALIDATION_ERROR'],
 ['有效凭证读取用户编号', '正常', '高', 'NEEDS_REVIEW', 3, 'API-02', 200, '{"Authorization":"Bearer ${env.demo_token}"}', '$.user.id', '1001']
 ].map(([title,type,priority,state,ri,apiId,status,body,jsonPath,expected],i)=>({id:`TC-${String(i+1).padStart(3,'0')}`, title,type,priority,state,reqIds:[requirements[ri].id],apiId,status,body,jsonPath,expected,version:1,apiVersion:1,negative:type!=='正常',source:'演示需求 §5',setup:i===0,cleanup:'使用只读演示数据，无需清理',confirmedVersion:state==='CONFIRMED'?1:null}));
}
// ponytail: 此处是演示表单校验；正式联调须以后端结构、变量、目标和版本预检为准。
export function validateCase(c) {
 const errors=[];
 if (!c.title?.trim()) errors.push('填写用例标题');
 if (!c.reqIds?.length) errors.push('至少关联一个需求点');
 if (!c.apiId) errors.push('绑定测试接口');
 if (!Number.isInteger(Number(c.status)) || Number(c.status)<100 || Number(c.status)>599) errors.push('填写有效的精确 HTTP 状态码');
 try { const body=JSON.parse(c.body); if (!body || typeof body!=='object' || Array.isArray(body)) errors.push('请求参数须为 JSON 对象'); } catch { errors.push('请求参数不是合法 JSON'); }
 if (!c.jsonPath?.match(/^\$(\.[A-Za-z_][\w]*|\[\d+\])*$/)) errors.push('JSONPath 仅支持对象字段和固定数组下标');
 if (!c.expected?.trim()) errors.push('填写字段预期值');
 if (!c.cleanup?.trim()) errors.push('说明清理方式或无需清理');
 return errors;
}
export function preflight(cases) {
 if (!cases.length) return ['至少选择一条用例'];
 if (cases.length>20) return ['每批最多执行 20 条用例'];
 return cases.flatMap(c=>[...(c.state!=='CONFIRMED'||c.confirmedVersion!==c.version?[`${c.id}：当前版本尚未确认`]:[]),...validateCase(c).map(e=>`${c.id}：${e}`)]);
}
export function stats(results) {
 const counts=Object.fromEntries(['PASS','FAIL','ERROR','BLOCKED'].map(s=>[s,results.filter(r=>r.result===s).length]));
 return {...counts,total:results.length,done:Object.values(counts).reduce((a,b)=>a+b,0),rate:results.length?Math.round(counts.PASS/results.length*100):0};
}
export function escapeHtml(value) {return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
export function reportHtml(run) {
 const s=stats(run.results),e=escapeHtml;
 return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>TestPilot 演示报告</title><style>body{font:15px system-ui;margin:48px;color:#21352f}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd8d1;padding:12px;text-align:left}p{line-height:1.7}</style><h1>TestPilot · 演示批次报告</h1><p>仅为前端模拟数据，未发送 HTTP 请求。批次 ${e(run.id)} · ${e(run.state)} · ${e(run.time)}<br>通过 ${s.PASS} / 失败 ${s.FAIL} / 错误 ${s.ERROR} / 阻塞 ${s.BLOCKED}；通过率 ${s.rate}%（分母 ${s.total}）</p><table><tr><th>用例 / 版本</th><th>结果</th><th>预期 / 实际</th></tr>${run.results.map(r=>`<tr><td>${e(r.id)} · v${r.version}<br>${e(r.title)}</td><td>${e(r.result||'未完成')}</td><td>${e(r.evidence||'无差异')}<br>预期状态 ${e(r.status)}；实际 ${e(r.actual??'未获得响应')}</td></tr>`).join('')}</table><p>AI 分析状态：${e(run.analysis||'未生成')}。结果仅针对本批快照，不代表软件整体质量。</p></html>`;
}
