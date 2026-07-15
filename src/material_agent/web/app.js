const state={token:sessionStorage.getItem('material-agent-token')||'',page:1,pages:1,items:[],overview:null};
const $=(selector)=>document.querySelector(selector);
const escapeHtml=(value)=>String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const fmt=(value,digits=1)=>value===null||value===undefined?'—':Number(value).toFixed(digits);
const toast=(message)=>{const node=$('#toast');node.textContent=message;node.classList.add('show');setTimeout(()=>node.classList.remove('show'),2600)};

async function api(path,options={}){
  const headers={'Content-Type':'application/json',...(options.headers||{})};
  if(state.token)headers.Authorization=`Bearer ${state.token}`;
  const response=await fetch(path,{...options,headers});
  if(response.status===401){$('#token-dialog').showModal();throw new Error('需要访问令牌')}
  const payload=await response.json().catch(()=>({error:response.statusText}));
  if(!response.ok)throw new Error(payload.error||response.statusText);
  return payload;
}

async function authImage(url,img){
  try{const headers={};if(state.token)headers.Authorization=`Bearer ${state.token}`;const response=await fetch(url,{headers});if(!response.ok)throw new Error();const blob=await response.blob();img.src=URL.createObjectURL(blob)}catch{img.replaceWith(Object.assign(document.createElement('span'),{textContent:'无预览'}))}
}

function showView(name){
  document.querySelectorAll('.view').forEach(node=>node.classList.toggle('active',node.id===`view-${name}`));
  document.querySelectorAll('.nav-item').forEach(node=>node.classList.toggle('active',node.dataset.view===name));
  const titles={dashboard:'运行概览',library:'素材库',tasks:'任务与日志',settings:'运行参数',models:'模型管理'};
  $('#view-title').textContent=titles[name];location.hash=name;
  if(name==='library')loadLibrary();if(name==='tasks')loadTasks();if(name==='settings')loadConfig();if(name==='models')loadModels();
}

function renderTasks(tasks,target){
  if(!tasks.length){target.innerHTML='<p class="muted">暂无任务</p>';return}
  target.innerHTML=tasks.map(task=>`<div class="row" data-task="${escapeHtml(task.id)}"><span><strong>${escapeHtml(task.id.slice(0,10))}</strong><br><span class="muted">${new Date(task.created_at*1000).toLocaleString()}</span></span><span>${escapeHtml(task.status)}</span><span>${task.max_files??'全量'}</span><span><button class="secondary task-log-button">日志</button>${['queued','running','cancelling'].includes(task.status)?' <button class="secondary danger task-cancel-button">取消</button>':''}</span></div>`).join('');
}

async function loadOverview(){
  try{
    const data=await api('/api/overview');state.overview=data;
    $('#health-dot').className='ok';$('#health-text').textContent='本地服务在线';
    const lib=data.library;
    $('#metrics').innerHTML=[['已索引',lib.indexed],['已评分',lib.scored],['平均分',fmt(lib.average_score,2)],['错误',lib.errors]].map(([label,value])=>`<div class="metric"><span>${label}</span><strong>${value}</strong></div>`).join('');
    const max=Math.max(1,...lib.scenes.map(item=>item.count));
    $('#scene-bars').innerHTML=lib.scenes.length?lib.scenes.map(item=>`<div class="scene-bar"><span>${escapeHtml(item.scene)}</span><div class="bar-track"><div class="bar-fill" style="width:${item.count/max*100}%"></div></div><b>${item.count}</b></div>`).join(''):'<p class="muted">评分后会在这里显示场景分布。</p>';
    renderTasks(data.tasks,$('#recent-tasks'));
  }catch(error){$('#health-dot').className='bad';$('#health-text').textContent=error.message}
}

async function loadLibrary(){
  const params=new URLSearchParams({page:state.page,page_size:48,search:$('#library-search').value,scored:$('#library-scored').value,order:$('#library-order').value});
  try{
    const data=await api(`/api/library?${params}`);state.pages=data.pages;state.items=data.items;
    $('#library-meta').textContent=`共 ${data.total} 项 · 第 ${data.page}/${data.pages} 页`;
    $('#page-label').textContent=`${data.page} / ${data.pages}`;$('#page-prev').disabled=data.page<=1;$('#page-next').disabled=data.page>=data.pages;
    $('#photo-grid').innerHTML=data.items.map(item=>`<article class="photo-card" data-item="${item.id}"><div class="thumb"><img data-thumb="${item.id}" alt=""></div><div class="photo-info"><div class="photo-title" title="${escapeHtml(item.relative_path)}">${escapeHtml(item.relative_path)}</div><div class="photo-tags"><span>${escapeHtml(item.scene||'未评分')}</span><span>${escapeHtml(item.target||'')}</span><strong class="score">${fmt(item.score_total,1)}</strong></div></div></article>`).join('');
    document.querySelectorAll('[data-thumb]').forEach(img=>authImage(`/api/library/${img.dataset.thumb}/thumbnail`,img));
  }catch(error){toast(error.message)}
}

function pick(payload,path,fallback='—'){let value=payload;for(const key of path.split('.'))value=value?.[key];return value??fallback}
async function showDetail(id){
  try{
    const item=await api(`/api/library/${id}`),score=item.score||{};
    const fields=[['总分',item.score_total],['场景',item.scene],['决策',score.decision],['星级',score.star_rating],['主体',pick(score,'meta.subject_focus.primary_target.label')],['主体对焦',pick(score,'meta.subject_focus.score')],['曝光',pick(score,'meta.dimensions.exposure')],['清晰度',pick(score,'meta.dimensions.sharpness')],['NIMA',pick(score,'meta.aesthetic.raw_score')]];
    $('#detail-content').innerHTML=`<p class="eyebrow">${escapeHtml(item.relative_path)}</p><div class="detail-hero"><div><img id="detail-image" alt=""><p class="muted">${escapeHtml(item.file_path)}</p></div><div><div class="detail-score">${fmt(item.score_total,2)}</div><div class="detail-grid">${fields.map(([label,value])=>`<div class="detail-field"><small>${label}</small>${escapeHtml(value)}</div>`).join('')}</div><h3>完整评分字段</h3><pre>${escapeHtml(JSON.stringify(score,null,2))}</pre></div></div>`;
    $('#detail-dialog').showModal();authImage(`/api/library/${id}/thumbnail`,$('#detail-image'));
  }catch(error){toast(error.message)}
}

async function loadTasks(){try{const data=await api('/api/tasks');renderTasks(data.tasks,$('#task-list'))}catch(error){toast(error.message)}}
async function loadTaskLog(id){try{const data=await api(`/api/tasks/${id}/log`);$('#task-log').textContent=data.log||'日志为空'}catch(error){toast(error.message)}}
async function loadConfig(){try{const data=await api('/api/config');$('#config-editor').value=JSON.stringify(data.config,null,2);$('#config-status').textContent=data.path}catch(error){toast(error.message)}}
async function saveConfig(){try{const config=JSON.parse($('#config-editor').value);const data=await api('/api/config',{method:'PUT',body:JSON.stringify({config})});$('#config-editor').value=JSON.stringify(data.config,null,2);$('#config-status').textContent='配置已验证并保存；原文件备份为 .web.bak';toast('配置已保存')}catch(error){$('#config-status').textContent=error.message}}

async function loadModels(){
  try{const data=await api('/api/models');$('#model-grid').innerHTML=data.models.map(model=>`<article class="model-card"><p class="eyebrow">${escapeHtml(model.role)}</p><h3>${escapeHtml(model.name)}</h3><div class="model-meta">${escapeHtml(model.model_id)}<br>${escapeHtml(model.adapter)} · ${escapeHtml(model.version)}<br>${model.installed?'已安装':'未安装'}${model.selected?' · 当前使用':''}<br>${escapeHtml(model.license)}</div><div class="model-actions">${model.installed?`<button data-model-action="select" data-model="${model.model_id}" ${model.selected?'disabled':''}>选择</button><button class="secondary danger" data-model-action="delete" data-model="${model.model_id}">删除</button>`:`<button data-model-action="install" data-model="${model.model_id}">下载并安装</button>`}</div></article>`).join('')}catch(error){toast(error.message)}
}

async function modelAction(model,action){try{if(action==='delete'){await api(`/api/models/${model}`,{method:'DELETE'});}else{await api(`/api/models/${model}/${action}`,{method:'POST',body:'{}'});}toast('模型状态已更新');loadModels()}catch(error){toast(error.message)}}
async function cancelTask(id){try{await api(`/api/tasks/${id}/cancel`,{method:'POST',body:'{}'});toast('取消请求已发送');loadTasks();loadOverview()}catch(error){toast(error.message)}}

document.addEventListener('click',event=>{
  const nav=event.target.closest('[data-view]');if(nav)showView(nav.dataset.view);
  const go=event.target.closest('[data-go]');if(go)showView(go.dataset.go);
  const card=event.target.closest('[data-item]');if(card)showDetail(card.dataset.item);
  const task=event.target.closest('.task-log-button');if(task)loadTaskLog(task.closest('[data-task]').dataset.task);
  const cancel=event.target.closest('.task-cancel-button');if(cancel)cancelTask(cancel.closest('[data-task]').dataset.task);
  const model=event.target.closest('[data-model-action]');if(model)modelAction(model.dataset.model,model.dataset.modelAction);
});
$('#navigation').addEventListener('click',event=>{const button=event.target.closest('[data-view]');if(button)showView(button.dataset.view)});
$('#index-button').addEventListener('click',async()=>{try{$('#index-button').disabled=true;const data=await api('/api/library/index',{method:'POST',body:'{}'});toast(`已索引 ${data.indexed} 个文件`);loadOverview()}catch(error){toast(error.message)}finally{$('#index-button').disabled=false}});
$('#task-form').addEventListener('submit',async event=>{event.preventDefault();const form=new FormData(event.target);try{const data=await api('/api/tasks',{method:'POST',body:JSON.stringify({max_files:form.get('max_files'),reprocess:form.has('reprocess'),no_visual_merge:form.has('no_visual_merge')})});toast(`任务 ${data.id.slice(0,8)} 已启动`);loadOverview()}catch(error){toast(error.message)}});
$('#library-refresh').addEventListener('click',()=>{state.page=1;loadLibrary()});$('#library-search').addEventListener('keydown',event=>{if(event.key==='Enter'){state.page=1;loadLibrary()}});$('#library-scored').addEventListener('change',()=>{state.page=1;loadLibrary()});$('#library-order').addEventListener('change',()=>{state.page=1;loadLibrary()});
$('#page-prev').addEventListener('click',()=>{if(state.page>1){state.page--;loadLibrary()}});$('#page-next').addEventListener('click',()=>{if(state.page<state.pages){state.page++;loadLibrary()}});
$('#config-save').addEventListener('click',saveConfig);$('#detail-close').addEventListener('click',()=>$('#detail-dialog').close());$('#token-button').addEventListener('click',()=>{$('#token-input').value=state.token;$('#token-dialog').showModal()});
$('#token-form').addEventListener('submit',event=>{event.preventDefault();state.token=$('#token-input').value.trim();sessionStorage.setItem('material-agent-token',state.token);$('#token-dialog').close();loadOverview()});

const initial=location.hash.slice(1)||'dashboard';showView(['dashboard','library','tasks','settings','models'].includes(initial)?initial:'dashboard');loadOverview();setInterval(()=>{if($('#view-dashboard').classList.contains('active'))loadOverview()},10000);
