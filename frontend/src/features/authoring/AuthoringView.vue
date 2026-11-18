<script setup>
import {ref, computed, watch} from 'vue';
import { USE_MOCK as useMock } from '@/api/config';
import { useRoute, useRouter } from 'vue-router';

import { ElMessage } from 'element-plus';
import {VideoPlay, Search, Plus, Check, Close, EditPen} from '@element-plus/icons-vue';
import {states, requirements as initialReqs, apis as initialApis, seedCases, validateCase} from './model';
const clone=value=>JSON.parse(JSON.stringify(value));
const route = useRoute();
const router = useRouter();
const page = computed(() => route.meta.page || '测试用例');
const query=ref(''), filter=ref('全部用例'), active=ref(null), draft=ref(null), editorOpen=ref(false), errors=ref([]), tab=ref('测试意图');
const reqs=ref(clone(initialReqs)), apis=ref(clone(initialApis)), cases=ref(seedCases());
const reqDraft = ref(null);
const fileInput = ref(null);
const generationBusy = ref(false);
const storageKey = 'testpilot-authoring-demo-v1';

try {
  if (useMock) {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved) {
      cases.value = saved.cases ?? cases.value;
      reqs.value = saved.reqs ?? reqs.value;
    }
  }
} catch {
  ElMessage.warning('本地记录无法读取，已载入初始演示数据');
}

function persist() {
  try {
    localStorage.setItem(storageKey, JSON.stringify({ cases: cases.value, reqs: reqs.value }));
  } catch {
    ElMessage.warning('浏览器存储不可用，本次更改仅在当前页面保留');
  }
}

const count=computed(()=>({confirmed:cases.value.filter(c=>c.state==='CONFIRMED').length,review:cases.value.filter(c=>['READY','NEEDS_REVIEW','DRAFT'].includes(c.state)).length,missing:cases.value.filter(c=>c.state==='NEEDS_INFO').length}));
const shown=computed(()=>cases.value.filter(c=>(`${c.id} ${c.title}`.toLowerCase().includes(query.value.toLowerCase()))&&(filter.value==='全部用例'||(filter.value==='已确认'?c.state==='CONFIRMED':filter.value==='待评审'?['READY','NEEDS_REVIEW','DRAFT'].includes(c.state):c.state==='NEEDS_INFO'))));
const apiFor=c=>apis.value.find(a=>a.id===c.apiId);
function go(name) {
  return router.push({ name: {'测试用例':'cases','需求管理':'requirements','接口与环境':'runs-environment','执行中心':'runs-list','测试报告':'runs-list'}[name], params: { projectId: route.params.projectId } });
}
watch(() => route.fullPath, () => {
  query.value = '';
  editorOpen.value = false;
});
function openFirstCase() {
  if (page.value === '测试用例' && window.matchMedia('(min-width: 1050px)').matches && cases.value.length) {
    openCase(cases.value[0]);
    tab.value = '请求与断言';
  }
}
function openCase(c){active.value=c;draft.value=clone(c);errors.value=[];tab.value=c.version ? '请求与断言' : '测试意图';editorOpen.value=true;}
function newCase(){openCase({id:`TC-${Date.now().toString().slice(-6)}`,title:'',type:'正常',priority:'中',state:'DRAFT',reqIds:[],apiId:'',apiVersion:1,status:200,body:'{}',jsonPath:'$.code',expected:'',version:0,cleanup:'只读操作，无需清理',setup:false,negative:false});}
function saveCase(){const c=draft.value;if(!c.title.trim()){errors.value=['填写用例标题'];return;}const next={...clone(c),version:(active.value?.version||0)+1,state:'DRAFT',confirmedVersion:null};const i=cases.value.findIndex(x=>x.id===next.id);if(i>=0)cases.value[i]=next;else cases.value.push(next);active.value=next;draft.value=clone(next);errors.value=[];persist();ElMessage.success('已保存新版本，需重新校验并确认');}
function validate(){saveCase();if(!draft.value.title.trim())return;errors.value=validateCase(draft.value);const c=cases.value.find(c=>c.id===draft.value.id);c.state=errors.value.length?'NEEDS_INFO':'READY';draft.value.state=c.state;persist();if(!errors.value.length)ElMessage.success('演示表单校验通过，请核对业务预期后确认');}
function confirmCase(){const c=cases.value.find(c=>c.id===draft.value.id);if(!c||c.state!=='READY')return; if(JSON.stringify({...draft.value,state:c.state})!==JSON.stringify(c)){ElMessage.warning('存在未保存的编辑，请重新保存并校验');return;}c.state='CONFIRMED';c.confirmedVersion=c.version;draft.value=clone(c);persist();ElMessage.success('演示用例已确认');}
async function upload(event){const file=event.target.files?.[0];event.target.value='';if(!file)return;if(!/\.(md|txt)$/i.test(file.name)||file.size>2*1024*1024){ElMessage.error('仅支持不超过 2MB 的 .md / .txt 文件');return;}try{const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());if(text.length>20000||!text.trim()){ElMessage.error('正文须为 1～20000 字符');return;}const lines=text.split(/\r?\n/).map((text,i)=>({text:text.trim(),line:i+1})).filter(x=>x.text);reqs.value.push(...lines.map((x,i)=>({id:`R-${Date.now()}-${i+1}`,title:x.text.replace(/^#+\s*/,'').slice(0,40),text:x.text,version:1,source:file.name,line:x.line})));persist();ElMessage.success(`已导入 ${lines.length} 个需求条目，可继续编辑切分`);}catch{ElMessage.error('无法读取文件，请使用 UTF-8 编码后重试');}}
function saveReq(){if(!reqDraft.value.title.trim()||!reqDraft.value.text.trim())return ElMessage.error('填写标题与需求正文');const r=reqs.value.find(r=>r.id===reqDraft.value.id);Object.assign(r,reqDraft.value,{version:r.version+1});cases.value.filter(c=>c.reqIds.includes(r.id)).forEach(c=>c.state='NEEDS_REVIEW');reqDraft.value=null;persist();ElMessage.success('需求已更新，关联用例已标为待复核');}
async function generate(){if(generationBusy.value)return;generationBusy.value=true;await new Promise(r=>setTimeout(r,650));const n=cases.value.length+1;const r=reqs.value[0];cases.value.unshift({...seedCases()[0],id:`TC-${String(n).padStart(3,'0')}`,title:`${r.title} · 生成候选`,reqIds:[r.id],state:'DRAFT',version:1,confirmedVersion:null});generationBusy.value=false;persist();go('测试用例');ElMessage.success('已添加一条模板演示草稿，未调用 AI、未发送请求');}
openFirstCase();

</script>

<template>
<div class="authoring-prototype">
 <div class="main-shell">
  <main v-if="useMock && route.params.projectId === 'proj-demo-0001'">
   <div class="page-heading"><div><h1>{{page}}</h1></div><div class="heading-actions"><template v-if="page==='测试用例'"><el-button :icon="Plus" @click="newCase">新建用例</el-button><el-button :loading="generationBusy" @click="generate">生成演示草稿</el-button></template><el-button v-if="page==='需求管理'" type="primary" :icon="Plus" @click="fileInput.click()">导入需求</el-button></div></div>

   <template v-if="page==='测试用例'">
    <div class="case-workspace" :class="{ 'has-detail': editorOpen }">
    <section class="case-list" aria-label="用例列表">
    <section class="cases-panel">

     <div class="panel-tabs"><button v-for="name in ['全部用例','已确认','待评审','待补充']" :class="{selected:filter===name}" @click="filter=name">{{name}} <span>{{name==='全部用例'?cases.length:name==='已确认'?count.confirmed:name==='待评审'?count.review:count.missing}}</span></button></div>
     <div class="table-toolbar"><el-input v-model="query" placeholder="搜索用例名称或编号" :prefix-icon="Search" clearable aria-label="搜索用例"/><span>{{shown.length}} 条</span></div>
     <el-table :data="shown" row-key="id" @row-click="openCase" :row-class-name="({row})=>editorOpen && draft?.id === row.id ? 'active-case' : ''" empty-text="没有匹配的用例，请调整搜索或创建新用例">

      <el-table-column label="用例" min-width="150"><template #default="{row}">
        <button class="case-title" @click.stop="openCase(row)">{{row.title}}</button>
        <div class="case-meta">{{row.id}} · v{{row.version}} · {{row.type}}</div>
      </template></el-table-column>
      <el-table-column v-if="!editorOpen" label="绑定接口" min-width="135"><template #default="{row}"><span v-if="apiFor(row)" class="endpoint"><b>{{apiFor(row).method}}</b>{{apiFor(row).path}}</span><span v-else class="muted">待绑定</span></template></el-table-column>
      <el-table-column label="状态" width="82" fixed="right"><template #default="{row}"><span class="case-state" :data-state="row.state">{{states[row.state]}}</span></template></el-table-column>
     </el-table>
    </section>
    <div class="execution-bar">
      <span>需求与用例演示</span>
      <el-button :icon="VideoPlay" @click="go('执行中心')">打开执行页</el-button>
    </div>
    </section>
    <aside v-if="editorOpen && draft" class="case-editor" aria-label="用例详情">
  <div class="drawer-heading">
    <div><h2>{{draft.title || '新建用例'}}</h2><p class="case-meta">{{draft.id}} · v{{draft.version}}</p></div>
    <el-button text :icon="Close" aria-label="关闭用例详情" @click="editorOpen=false"/>
  </div>
  <div class="request-line">
    <span v-if="apiFor(draft)" class="endpoint"><b>{{apiFor(draft).method}}</b>{{apiFor(draft).path}}</span>
    <span v-else class="muted">待绑定接口</span>
    <span class="case-state" :data-state="draft.state">{{states[draft.state]}}</span>
  </div>
  <div class="editor-body">
<el-tabs v-model="tab"><el-tab-pane label="测试意图" name="测试意图"/><el-tab-pane label="请求与断言" name="请求与断言"/><el-tab-pane label="需求来源" name="需求来源"/></el-tabs>
 <el-form label-position="top" v-if="tab==='测试意图'"><el-form-item label="用例标题" required><el-input v-model="draft.title" maxlength="120"/></el-form-item><div class="form-pair"><el-form-item label="测试类型"><el-select v-model="draft.type"><el-option v-for="t in ['正常','异常','边界']" :value="t"/></el-select></el-form-item><el-form-item label="用例优先级"><el-select v-model="draft.priority"><el-option v-for="t in ['高','中','低']" :value="t"/></el-select></el-form-item></div><el-form-item label="关联需求点" required><el-select v-model="draft.reqIds" multiple style="width:100%"><el-option v-for="r in reqs" :label="r.id+' · '+r.title" :value="r.id"/></el-select></el-form-item><el-form-item label="测试数据与清理说明" required><el-input v-model="draft.cleanup" type="textarea" :rows="3"/></el-form-item><el-checkbox v-model="draft.negative">声明为负向测试，保留预期无效的业务输入</el-checkbox><div class="inline-note">负向用例可以预期 400 或 401；HTTP 非 2xx 不等于测试失败。</div></el-form>
 <el-form label-position="top" v-if="tab==='请求与断言'"><div v-if="draft.setup" class="inline-note">准备步骤：POST /auth/login → 提取 $.token 到 steps.login.token（敏感）。失败时主测试阻塞；无跨用例变量共享。</div><el-form-item label="测试步骤 · 绑定接口" required><el-select v-model="draft.apiId" style="width:100%" @change="draft.apiVersion=apiFor(draft)?.version||1"><el-option v-for="a in apis" :label="a.method+' '+a.path+' · v'+a.version" :value="a.id"/></el-select></el-form-item><el-form-item label="请求参数 / 请求头（JSON 对象）" required><el-input v-model="draft.body" type="textarea" :rows="6" class="code-input"/></el-form-item><el-form-item label="精确状态码断言" required><el-input-number v-model="draft.status" :min="100" :max="599"/></el-form-item><div class="form-pair"><el-form-item label="JSONPath" required><el-input v-model="draft.jsonPath"/></el-form-item><el-form-item label="字段预期值" required><el-input v-model="draft.expected"/></el-form-item></div></el-form>
 <div v-if="tab==='需求来源'"><article class="source-block" v-for="r in reqs.filter(r=>draft.reqIds.includes(r.id))"><span class="mono muted">{{r.id}} · v{{r.version}}</span><h3>{{r.title}}</h3><p>{{r.text}}</p><small>{{r.source}} · 第 {{r.line}} 行</small></article><el-empty v-if="!draft.reqIds.length" description="先在测试意图中关联需求点。"/></div>
 <div v-if="errors.length" class="field-errors" role="alert"><b>请补齐以下内容</b><p v-for="e in errors">{{e}}</p></div></div><div class="drawer-actions"><el-button @click="saveCase">保存草稿</el-button><el-button @click="validate">保存并校验</el-button><el-button type="primary" :icon="Check" :disabled="draft.state!=='READY'" @click="confirmCase">确认当前版本</el-button></div></aside>
    </div>
   </template>

   <template v-if="page==='需求管理'">
    <input ref="fileInput" type="file" accept=".md,.txt" hidden @change="upload"/>
    <div class="inline-note">支持 UTF-8 Markdown / TXT，单文件 ≤ 2MB、正文 ≤ 20000 字符。当前按非空行切分，可逐条修正。</div>
    <section class="content-panel requirements"><article v-for="r in reqs" :key="r.id"><div><span class="mono muted">{{r.id}} · v{{r.version}}</span><h3>{{r.title}}</h3><p>{{r.text}}</p><small>来源：{{r.source}} · 第 {{r.line}} 行</small></div><el-button :icon="EditPen" @click="reqDraft={...r}">编辑</el-button></article></section>
   </template>

  </main>
  <el-alert v-else title="项目已选定。需求与用例的真实接口接入安排在下一阶段。" type="info" :closable="false"/>
 </div>
</div>



<el-dialog :model-value="!!reqDraft" @close="reqDraft=null" title="编辑需求条目" width="min(600px, 94vw)"><el-form v-if="reqDraft" label-position="top"><el-form-item label="标题"><el-input v-model="reqDraft.title"/></el-form-item><el-form-item label="需求正文"><el-input v-model="reqDraft.text" type="textarea" :rows="5"/></el-form-item></el-form><template #footer><el-button type="primary" @click="saveReq">保存新版本</el-button></template></el-dialog>
</template>




<style src="./style.css"></style>
