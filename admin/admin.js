/* Admin Panel v4 - SlashMyBill */
var API='https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';
var PASS='YuvalEyal1!';
var ADMIN_PASSES=['YuvalEyal1!','AniscoAdmin26!','Anisco2026!'];
var allLeads=[],allTips=[],editingTip=null,editingLead=null,deletingItem=null,deleteType=null,allFeedback=[];
var PS=15,lp=1,tp=1,fp=1,lsc='timestamp',lsa=false,tsc='service',tsa=true,fsc='createdAt',fsa=false,dt=null;

var $=function(id){return document.getElementById(id);};
var loginGate=$('login-gate'),gateForm=$('gate-form'),gatePassword=$('gate-password'),gateError=$('gate-error'),dash=$('dashboard-view');
var leadsPanel=$('leads-tab'),tipsPanel=$('tips-tab'),feedbackPanel=$('feedback-tab'),leadsSearch=$('leads-search'),tipsSearch=$('tips-search'),feedbackSearch=$('feedback-search');
var leadsTbody=$('leads-tbody'),tipsTbody=$('tips-tbody'),feedbackTbody=$('feedback-tbody'),leadsEmpty=$('leads-empty'),tipsEmpty=$('tips-empty'),feedbackEmpty=$('feedback-empty');
var addTipBtn=$('add-tip-btn'),tipModal=$('tip-modal'),tipModalTitle=$('tip-modal-title'),tipForm=$('tip-form');
var tipFormError=$('tip-form-error'),tipCancelBtn=$('tip-cancel-btn'),tipModalClose=$('tip-modal-close'),tipSubmitBtn=$('tip-submit-btn');
var leadModal=$('lead-modal'),leadForm=$('lead-form'),leadFormError=$('lead-form-error'),leadCancelBtn=$('lead-cancel-btn');
var leadModalClose=$('lead-modal-close'),leadSubmitBtn=$('lead-submit-btn');
var delDialog=$('delete-dialog'),delMsg=$('delete-dialog-msg'),delCancel=$('delete-cancel-btn'),delConfirm=$('delete-confirm-btn');
var loading=$('loading-overlay'),notif=$('notification'),notifMsg=$('notification-message');
var bulkBtn=$('bulk-delete-leads-btn'),selAll=$('leads-select-all');
var TF=['service','tipId','category','title','description','estimatedSavings','difficulty','automatedCheck','cloud','provider','level','actionType','actionLabel','drilldownInstructions','drilldownApis','checkConnection'];
/* Optional (non-required) editable fields sent on save */
var TO=['automatedCheck','cloud','provider','level','actionType','actionLabel','drilldownInstructions','drilldownApis','checkConnection'];
/* Read-only metadata shown in the form */
var TM=['version','syncSource','createdAt','contentHash','positiveCount','confidenceTag','checkImplemented','implementedInAct','implementedInScheduler','serviceKey','providerRouting','source','id'];
var TR=['service','tipId','category','title','description','estimatedSavings','difficulty'];

gateForm.onsubmit=function(e){e.preventDefault();var p=gatePassword.value;if(!p){gateError.textContent='Enter password.';return;}if(ADMIN_PASSES.indexOf(p)!==-1){sessionStorage.setItem('ok','1');loginGate.hidden=true;dash.hidden=false;load();}else{gateError.textContent='Wrong password.';gatePassword.value='';}};
if(sessionStorage.getItem('ok')==='1'){loginGate.hidden=true;dash.hidden=false;}

function notify(m,t){notifMsg.textContent=m;notif.className='notification notification-'+t;notif.hidden=false;setTimeout(function(){notif.hidden=true;},4000);}
function showL(){loading.hidden=false;}function hideL(){loading.hidden=true;}
function fmtD(ts){if(!ts)return'';try{var d=new Date(ts);return isNaN(d)?ts:d.toLocaleString('en-US',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}catch(e){return ts;}}
function fmtM(v){if(v==null||v==='')return'-';var n=Number(v);return isNaN(n)?String(v):'$'+n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function ea(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function switchTab(n){document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.toggle('active',b.dataset.tab===n);});leadsPanel.hidden=n!=='leads';tipsPanel.hidden=n!=='tips';feedbackPanel.hidden=n!=='feedback';var subsPanel=$('subscribers-tab');if(subsPanel)subsPanel.hidden=n!=='subscribers';var schedPanel=$('schedules-tab');if(schedPanel)schedPanel.hidden=n!=='schedules';var syncPanel=$('sync-tab');if(syncPanel)syncPanel.hidden=n!=='sync';if(n==='feedback'&&!allFeedback.length)loadFeedback();if(n==='subscribers'&&!allSubs.length)loadSubscribers();if(n==='schedules'&&!allScheds.length)loadSchedules();if(n==='sync'&&!syncLoaded)loadSyncData();}

async function api(method,path,body){var o={method:method,headers:{'Content-Type':'application/json'}};if(body)o.body=JSON.stringify(body);var r=await fetch(API+path,o);var d=await r.json();if(!r.ok)throw{status:r.status,message:d.message||'Error'};return d;}

function sortArr(a,c,asc){return a.slice().sort(function(x,y){var va=x[c],vb=y[c];if(va==null)va='';if(vb==null)vb='';var na=Number(va),nb=Number(vb);if(!isNaN(na)&&!isNaN(nb))return asc?na-nb:nb-na;va=String(va).toLowerCase();vb=String(vb).toLowerCase();return va<vb?(asc?-1:1):va>vb?(asc?1:-1):0;});}
function updSort(tid,c,a){document.querySelectorAll('#'+tid+' th.sortable').forEach(function(h){h.classList.remove('sort-asc','sort-desc');if(h.dataset.col===c)h.classList.add(a?'sort-asc':'sort-desc');});}
function pg(a,p){var s=(p-1)*PS;return a.slice(s,s+PS);}
function pgNav(id,tot,cur,fn){var c=$(id);if(!c){c=document.createElement('div');c.id=id;c.className='pagination';}c.innerHTML='';var tp=Math.ceil(tot/PS);if(tp<=1){if(c.parentNode)c.remove();return;}function mk(l,p,d,a){var b=document.createElement('button');b.className='page-btn';b.textContent=l;if(a)b.classList.add('active');if(d)b.disabled=true;else b.onclick=function(){fn(p);};return b;}c.appendChild(mk('Prev',cur-1,cur<=1));var s=Math.max(1,cur-2),e=Math.min(tp,cur+2);for(var i=s;i<=e;i++)c.appendChild(mk(i,i,false,i===cur));c.appendChild(mk('Next',cur+1,cur>=tp));var w=$(id.replace('-pagination','-tab'));if(w&&!$(id))w.appendChild(c);}

/* LEADS */
var fLeads=[];
async function loadLeads(){try{showL();var d=await api('GET','/admin/leads');allLeads=d.leads||[];lp=1;applyLeads();}catch(e){notify('Failed to load leads.','error');}finally{hideL();}}
function applyLeads(){var q=(leadsSearch.value||'').toLowerCase().trim();fLeads=q?allLeads.filter(function(l){return(l.email||'').toLowerCase().includes(q)||(l.name||'').toLowerCase().includes(q)||(l.company||'').toLowerCase().includes(q);}):allLeads.slice();fLeads=sortArr(fLeads,lsc,lsa);updSort('leads-table',lsc,lsa);renderLeads();}
function renderLeads(){var p=pg(fLeads,lp);leadsTbody.innerHTML='';if(!fLeads.length){leadsEmpty.hidden=false;return;}leadsEmpty.hidden=true;p.forEach(function(l,idx){var r=document.createElement('tr');r.innerHTML='<td style="color:#999;font-size:12px">'+(l.leadId||'-')+'</td><td><input type="checkbox" class="lchk" data-e="'+ea(l.email)+'" data-t="'+ea(l.timestamp)+'"></td><td>'+esc(l.email||'')+'</td><td>'+esc(l.name||'')+'</td><td>'+esc(l.company||'')+'</td><td>'+esc(l.phone||'')+'</td><td>'+esc(l.fileName||'')+'</td><td>'+fmtM(l.billTotalCost)+'</td><td>'+fmtM(l.monthlySavingsMin)+' - '+fmtM(l.monthlySavingsMax)+'</td><td>'+fmtD(l.timestamp)+'</td><td class="actions-cell"><button class="btn-icon btn-icon-edit" data-a="el" data-e="'+ea(l.email)+'" data-t="'+ea(l.timestamp)+'">&#9998;</button> <button class="btn-icon btn-icon-delete" data-a="dl" data-e="'+ea(l.email)+'" data-t="'+ea(l.timestamp)+'">&#128465;</button></td>';leadsTbody.appendChild(r);});pgNav('leads-pagination',fLeads.length,lp,function(x){lp=x;renderLeads();});updBulk();}
function showLeadForm(l){leadFormError.textContent='';editingLead=l;$('lead-email').value=l.email||'';$('lead-timestamp').value=fmtD(l.timestamp)||'';$('lead-name').value=l.name||'';$('lead-company').value=l.company||'';$('lead-phone').value=l.phone||'';$('lead-fileName').value=l.fileName||'';$('lead-billTotalCost').value=l.billTotalCost!=null?fmtM(l.billTotalCost):'-';$('lead-billCurrency').value=l.billCurrency||'';$('lead-monthlySavingsMin').value=l.monthlySavingsMin!=null?fmtM(l.monthlySavingsMin):'-';$('lead-monthlySavingsMax').value=l.monthlySavingsMax!=null?fmtM(l.monthlySavingsMax):'-';$('lead-notes').value=l.notes||'';leadModal.hidden=false;}
function hideLeadForm(){leadModal.hidden=true;editingLead=null;}
async function saveLead(){if(!editingLead)return;leadFormError.textContent='';var b={email:editingLead.email,timestamp:editingLead.timestamp,name:$('lead-name').value.trim(),company:$('lead-company').value.trim(),phone:$('lead-phone').value.trim(),notes:$('lead-notes').value.trim()};try{showL();await api('PUT','/admin/leads',b);notify('Lead updated.','success');hideLeadForm();await loadLeads();}catch(e){leadFormError.textContent=e.message||'Failed.';}finally{hideL();}}

/* TIPS */
var fTips=[];
async function loadTips(){try{showL();allTips=[];var offset=0,batchSize=100,hasMore=true;while(hasMore){var d=await api('GET','/admin/tips?limit='+batchSize+'&offset='+offset);var batch=d.tips||[];allTips=allTips.concat(batch);offset+=batch.length;hasMore=batch.length>=batchSize&&offset<(d.total||9999);}tp=1;applyTips();}catch(e){notify('Failed to load tips.','error');}finally{hideL();}}
function applyTips(){var q=(tipsSearch.value||'').toLowerCase().trim();fTips=q?allTips.filter(function(t){return(t.service||'').toLowerCase().includes(q)||(t.title||'').toLowerCase().includes(q)||(t.category||'').toLowerCase().includes(q)||(t.tipId||'').toLowerCase().includes(q)||(t.description||'').toLowerCase().includes(q)||(t.estimatedSavings||'').toLowerCase().includes(q)||(t.difficulty||'').toLowerCase().includes(q)||(t.cloud||'').toLowerCase().includes(q)||(t.automatedCheck||'').toLowerCase().includes(q)||(t.actionLabel||'').toLowerCase().includes(q);}):allTips.slice();fTips=sortArr(fTips,tsc,tsa);updSort('tips-table',tsc,tsa);renderTips();}
function renderTips(){var p=pg(fTips,tp);tipsTbody.innerHTML='';if(!fTips.length){tipsEmpty.hidden=false;return;}tipsEmpty.hidden=true;var tOff=(tp-1)*PS;p.forEach(function(t,idx){var r=document.createElement('tr');var sb=t.automatedCheck?'<span class="script-badge" data-a="vs" data-s="'+ea(t.service)+'" data-i="'+ea(t.tipId)+'">&#9881; Check</span>':'-';var pc=t.positiveCount||0;var scoreHtml=pc>0?'<span style="color:#10b981;font-weight:700">+'+pc+'</span>':pc<0?'<span style="color:#ef4444;font-weight:700">'+pc+'</span>':'<span style="color:#8b949e">0</span>';if(t.confidenceTag==='high-confidence')scoreHtml+=' <span style="background:#10b981;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;">✓</span>';var actHtml=t.implementedInAct?'<span style="background:#6366f1;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;">✓ Act</span>':'<span style="color:#d1d5db;font-size:10px;">—</span>';var schedHtml=t.implementedInScheduler?'<span style="background:#f59e0b;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;margin-left:4px;">⏰ Sched</span>':'';var cloudBadge=t.cloud?'<span style="background:#ff9900;color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;">'+esc(t.cloud)+'</span>':'<span style="color:#d1d5db;font-size:10px;">—</span>';var createdStr=t.createdAt?t.createdAt.substring(0,10):'—';r.innerHTML='<td style="color:#999;font-size:12px">'+(tOff+idx+1)+'</td><td>'+esc(t.service||'')+'</td><td>'+esc(t.tipId||'')+'</td><td>'+cloudBadge+'</td><td>'+esc(t.category||'')+'</td><td>'+esc(t.title||'')+'</td><td title="'+ea(t.description)+'">'+esc(t.description||'')+'</td><td>'+esc(t.estimatedSavings||'')+'</td><td><span class="badge badge-'+(t.difficulty||'').toLowerCase()+'">'+esc(t.difficulty||'')+'</span></td><td style="text-align:center">'+scoreHtml+'</td><td>'+actHtml+schedHtml+'</td><td>'+sb+'</td><td style="font-size:11px;color:#6b7280;">'+createdStr+'</td><td class="actions-cell"><button class="btn-icon btn-icon-edit" data-a="et" data-s="'+ea(t.service)+'" data-i="'+ea(t.tipId)+'">&#9998;</button> <button class="btn-icon btn-icon-delete" data-a="dt" data-s="'+ea(t.service)+'" data-i="'+ea(t.tipId)+'">&#128465;</button></td>';tipsTbody.appendChild(r);});pgNav('tips-pagination',fTips.length,tp,function(x){tp=x;renderTips();});}
function fmtTipVal(f,v){if(v==null)return '';if(f==='drilldownApis'){if(Array.isArray(v))return v.join('\n');if(typeof v==='string'){var s=v.trim();if(s.charAt(0)==='['){try{var a=JSON.parse(s);if(Array.isArray(a))return a.join('\n');}catch(e){}}return v;}return String(v);}return (typeof v==='object')?JSON.stringify(v):String(v);}
function renderTipMeta(t){var box=$('tip-meta');if(!box)return;if(!t){box.innerHTML='<span style="color:#9ca3af;font-size:12px">No metadata (new tip).</span>';return;}var html='';TM.forEach(function(f){var has=t[f]!==undefined&&t[f]!==null&&t[f]!=='';var val=has?esc(String(t[f])):'<span style="color:#cbd5e1">—</span>';html+='<div class="tip-meta-item"><span class="tip-meta-k">'+f+'</span><span class="tip-meta-v">'+val+'</span></div>';});box.innerHTML=html;}
function showTipForm(t){tipFormError.textContent='';if(t){editingTip=t;tipModalTitle.textContent='Edit Tip';tipSubmitBtn.textContent='Update Tip';TF.forEach(function(f){var e=$('tip-'+f);if(e)e.value=fmtTipVal(f,t[f]);});$('tip-service').disabled=true;$('tip-tipId').disabled=true;renderTipMeta(t);}else{editingTip=null;tipModalTitle.textContent='Add Tip';tipSubmitBtn.textContent='Save Tip';TF.forEach(function(f){var e=$('tip-'+f);if(e)e.value='';});$('tip-service').disabled=false;$('tip-tipId').disabled=false;renderTipMeta(null);}tipModal.hidden=false;}
function hideTipForm(){tipModal.hidden=true;editingTip=null;}
async function saveTip(){tipFormError.textContent='';var d={};for(var i=0;i<TR.length;i++){var f=TR[i],v=$('tip-'+f).value.trim();if(!v){tipFormError.textContent='All required fields must be filled.';return;}d[f]=v;}for(var j=0;j<TO.length;j++){var of=TO[j],oe=$('tip-'+of);if(!oe)continue;var ov=oe.value.trim();if(!ov)continue;if(of==='drilldownApis'){d.drilldownApis=ov.split('\n').map(function(s){return s.trim();}).filter(function(s){return s;});}else{d[of]=ov;}}try{showL();if(editingTip){await api('PUT','/admin/tips',d);notify('Tip updated.','success');}else{await api('POST','/admin/tips',d);notify('Tip created.','success');}hideTipForm();await loadTips();}catch(e){tipFormError.textContent=e.message||'Failed.';}finally{hideL();}}

/* DELETE */
function showDel(type,item){deleteType=type;deletingItem=item;delMsg.textContent='Delete this '+type+'? This cannot be undone.';delDialog.hidden=false;}
function hideDel(){delDialog.hidden=true;deletingItem=null;deleteType=null;delConfirm.hidden=false;delCancel.textContent='Cancel';delConfirm.textContent='Delete';}
async function doDel(){
  var item=deletingItem,dtype=deleteType;
  if(!item)return;
  delConfirm.disabled=true;delConfirm.textContent='Deleting...';
  try{
    var result;
    if(dtype==='tip'){result=await api('DELETE','/admin/tips',{service:item.service,tipId:item.tipId});}
    else if(dtype==='lead'){result=await api('DELETE','/admin/leads',{email:item.email,timestamp:item.timestamp});}
    else if(dtype==='bulk'){result=await api('POST','/admin/leads/bulk-delete',{items:item});}
    delMsg.innerHTML='<span style="color:#10b981;font-weight:700;">&#10003; '+(result.message||'Deleted successfully')+'</span>';
    delConfirm.hidden=true;delCancel.textContent='Close';
    if(dtype==='tip')await loadTips();
    else{if(selAll)selAll.checked=false;await loadLeads();}
  }catch(e){
    delMsg.innerHTML='<span style="color:#ef4444;font-weight:700;">&#10007; Error: '+(e.message||'Delete failed')+'</span>';
    delConfirm.hidden=true;delCancel.textContent='Close';
  }finally{delConfirm.disabled=false;delConfirm.textContent='Delete';}
}

/* BULK */
function getSel(){var c=document.querySelectorAll('.lchk:checked');var r=[];c.forEach(function(x){r.push({email:x.dataset.e,timestamp:x.dataset.t});});return r;}
function updBulk(){var s=getSel();bulkBtn.hidden=s.length===0;if(s.length>0)bulkBtn.textContent='Delete Selected ('+s.length+')';}

/* EVENTS */
document.querySelectorAll('.tab-btn').forEach(function(b){b.onclick=function(){switchTab(b.dataset.tab);};});
leadsSearch.oninput=function(){lp=1;applyLeads();};
tipsSearch.oninput=function(){tp=1;applyTips();};
feedbackSearch.oninput=function(){fp=1;applyFeedback();};
addTipBtn.onclick=function(){showTipForm(null);};
var _expJsonBtn=$('export-tips-json-btn');if(_expJsonBtn)_expJsonBtn.onclick=function(){exportTipsJSON();};
var _expCsvBtn=$('export-tips-csv-btn');if(_expCsvBtn)_expCsvBtn.onclick=function(){exportTipsCSV();};
tipForm.onsubmit=function(e){e.preventDefault();saveTip();};
tipCancelBtn.onclick=hideTipForm;tipModalClose.onclick=hideTipForm;
leadForm.onsubmit=function(e){e.preventDefault();saveLead();};
leadCancelBtn.onclick=hideLeadForm;leadModalClose.onclick=hideLeadForm;
delCancel.onclick=hideDel;
delConfirm.onclick=doDel;
selAll.onchange=function(){document.querySelectorAll('.lchk').forEach(function(c){c.checked=selAll.checked;});updBulk();};
leadsTbody.onchange=function(e){if(e.target.classList.contains('lchk'))updBulk();};
bulkBtn.onclick=function(){var s=getSel();if(!s.length)return;deleteType='bulk';deletingItem=s;delMsg.textContent='Delete '+s.length+' lead(s)? Cannot be undone.';delDialog.hidden=false;};

tipsTbody.onclick=function(e){var b=e.target.closest('[data-a]');if(!b)return;var a=b.dataset.a;if(a==='et'){var t=allTips.find(function(x){return x.service===b.dataset.s&&x.tipId===b.dataset.i;});if(t)showTipForm(t);}else if(a==='dt'){showDel('tip',{service:b.dataset.s,tipId:b.dataset.i});}else if(a==='vs'){var t2=allTips.find(function(x){return x.service===b.dataset.s&&x.tipId===b.dataset.i;});if(t2&&t2.automatedCheck){$('script-modal-title').textContent=t2.title+' - Automated Check';$('script-modal-content').textContent=t2.automatedCheck;$('script-modal').hidden=false;}}};
leadsTbody.onclick=function(e){var b=e.target.closest('[data-a]');if(!b)return;var a=b.dataset.a;if(a==='el'){var l=allLeads.find(function(x){return x.email===b.dataset.e&&x.timestamp===b.dataset.t;});if(l)showLeadForm(l);}else if(a==='dl'){showDel('lead',{email:b.dataset.e,timestamp:b.dataset.t});}};

tipModal.onclick=function(e){if(e.target===tipModal)hideTipForm();};
leadModal.onclick=function(e){if(e.target===leadModal)hideLeadForm();};
delDialog.addEventListener('click',function(e){if(e.target===delDialog)hideDel();},false);
$('script-modal').onclick=function(e){if(e.target===$('script-modal'))$('script-modal').hidden=true;};
$('script-modal-close').onclick=function(){$('script-modal').hidden=true;};
$('script-close-btn').onclick=function(){$('script-modal').hidden=true;};
$('script-copy-btn').onclick=function(){navigator.clipboard.writeText($('script-modal-content').textContent);notify('Copied.','success');};

/* FEEDBACK */
var fFeedback=[];
var feedbackLoaded=false;
async function loadFeedback(){try{showL();var d=await api('GET','/admin/feedback');allFeedback=d.feedback||[];feedbackLoaded=true;fp=1;renderFeedbackStats();applyFeedback();}catch(e){notify('Failed to load feedback.','error');}finally{hideL();}}
function renderFeedbackStats(){var el=$('feedback-stats');if(!el)return;var total=allFeedback.length;var pos=allFeedback.filter(function(f){return f.feedbackScore==='yes';}).length;var neg=allFeedback.filter(function(f){return f.feedbackScore==='no';}).length;var corr=allFeedback.filter(function(f){return f.userCorrection;}).length;var svcMap={};allFeedback.forEach(function(f){var s=f.relatedService||'General';if(!svcMap[s])svcMap[s]={pos:0,neg:0};if(f.feedbackScore==='yes')svcMap[s].pos++;else svcMap[s].neg++;});var topSvcs=Object.entries(svcMap).sort(function(a,b){return(b[1].pos+b[1].neg)-(a[1].pos+a[1].neg);}).slice(0,5);var rate=total>0?Math.round(pos/total*100):0;el.innerHTML='<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:120px;"><div style="color:#8b949e;font-size:0.8em;">Total Feedback</div><div style="color:#e2e8f0;font-size:1.4em;font-weight:700;">'+total+'</div></div>'+'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:120px;"><div style="color:#8b949e;font-size:0.8em;">Positive Rate</div><div style="color:#10b981;font-size:1.4em;font-weight:700;">'+rate+'% <span style="font-size:0.6em;color:#8b949e;">('+pos+' 👍 / '+neg+' 👎)</span></div></div>'+'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:120px;"><div style="color:#8b949e;font-size:0.8em;">Corrections</div><div style="color:#f59e0b;font-size:1.4em;font-weight:700;">'+corr+'</div></div>'+'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:2;min-width:200px;"><div style="color:#8b949e;font-size:0.8em;margin-bottom:4px;">Top Services by Feedback</div>'+topSvcs.map(function(s){return'<span style="display:inline-block;margin:2px 6px 2px 0;font-size:0.85em;color:#c9d1d9;">'+esc(s[0])+': <span style="color:#10b981;">'+s[1].pos+'👍</span> <span style="color:#ef4444;">'+s[1].neg+'👎</span></span>';}).join('')+'</div>';}function applyFeedback(){var q=(feedbackSearch.value||'').toLowerCase().trim();fFeedback=q?allFeedback.filter(function(f){return(f.memberEmail||'').toLowerCase().includes(q)||(f.userQuestion||'').toLowerCase().includes(q)||(f.relatedService||'').toLowerCase().includes(q)||(f.userCorrection||'').toLowerCase().includes(q);}):allFeedback.slice();fFeedback=sortArr(fFeedback,fsc,fsa);updSort('feedback-table',fsc,fsa);renderFeedback();}
function truncText(s,max){if(!s)return'';return s.length>max?s.substring(0,max)+'…':s;}
function renderFeedback(){var p=pg(fFeedback,fp);feedbackTbody.innerHTML='';if(!fFeedback.length){feedbackEmpty.hidden=false;return;}feedbackEmpty.hidden=true;var fOff=(fp-1)*PS;p.forEach(function(f,idx){var r=document.createElement('tr');var h=f.feedbackScore;var scoreHtml=h==='yes'?'<span style="color:#10b981;font-weight:700">👍 yes</span>':h==='no'?'<span style="color:#ef4444;font-weight:700">👎 no</span>':esc(h||'-');var qTrunc=truncText(f.userQuestion||'',60);var cTrunc=truncText(f.userCorrection||'',60);r.innerHTML='<td style="color:#999;font-size:12px">'+(fOff+idx+1)+'</td><td>'+esc(f.memberEmail||'')+'</td><td title="'+ea(f.userQuestion||'')+'">'+esc(qTrunc)+'</td><td>'+scoreHtml+'</td><td>'+esc(f.relatedService||'')+'</td><td title="'+ea(f.userCorrection||'')+'">'+esc(cTrunc)+'</td><td>'+fmtD(f.createdAt)+'</td>';feedbackTbody.appendChild(r);});pgNav('feedback-pagination',fFeedback.length,fp,function(x){fp=x;renderFeedback();});}

/* Feedback table sorting */
$('feedback-table').querySelector('thead').onclick=function(e){var th=e.target.closest('.sortable');if(!th)return;var c=th.dataset.col;if(fsc===c)fsa=!fsa;else{fsc=c;fsa=true;}fp=1;applyFeedback();};
$('leads-table').querySelector('thead').onclick=function(e){var th=e.target.closest('.sortable');if(!th)return;var c=th.dataset.col;if(lsc===c)lsa=!lsa;else{lsc=c;lsa=true;}lp=1;applyLeads();};
$('tips-table').querySelector('thead').onclick=function(e){var th=e.target.closest('.sortable');if(!th)return;var c=th.dataset.col;if(tsc===c)tsa=!tsa;else{tsc=c;tsa=true;}tp=1;applyTips();};

function load(){loadLeads();loadTips();}
if(sessionStorage.getItem('ok')==='1')load();


// ============================================================
// Subscribers Tab
// ============================================================
var allSubs=[];var fSubs=[];var sp=1;var ssc='createdAt';var ssa=false;
var subsTbody=$('subs-tbody');var subsEmpty=$('subs-empty');var subsSearch=$('subs-search');
var subModal=$('sub-modal');var editingSub=null;

var AI_CREDITS_MAP={free:100,growth:300,scale:1500};

async function loadSubscribers(){
    try{showL();var d=await api('GET','/admin/subscribers');allSubs=d.subscribers||[];sp=1;renderSubsStats();applySubs();}
    catch(e){notify('Failed to load subscribers.','error');}
    finally{hideL();}
}

function renderSubsStats(){
    var el=$('subs-stats');if(!el)return;
    var total=allSubs.length;
    var free=allSubs.filter(function(s){return(s.tier||'free')==='free';}).length;
    var growth=allSubs.filter(function(s){return s.tier==='growth';}).length;
    var scale=allSubs.filter(function(s){return s.tier==='scale';}).length;
    var totalBonus=allSubs.reduce(function(a,s){return a+(s.bonusTokens||0);},0);
    el.innerHTML='<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Total</div><div style="color:#e2e8f0;font-size:1.4em;font-weight:700;">'+total+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Free</div><div style="color:#9ca3af;font-size:1.4em;font-weight:700;">'+free+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Growth</div><div style="color:#3b82f6;font-size:1.4em;font-weight:700;">'+growth+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Scale</div><div style="color:#8b5cf6;font-size:1.4em;font-weight:700;">'+scale+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Bonus Tokens Given</div><div style="color:#f59e0b;font-size:1.4em;font-weight:700;">'+totalBonus+'</div></div>';
}

function applySubs(){
    var q=(subsSearch&&subsSearch.value||'').toLowerCase().trim();
    fSubs=q?allSubs.filter(function(s){return(s.email||'').toLowerCase().includes(q);}):allSubs.slice();
    fSubs=sortArr(fSubs,ssc,ssa);updSort('subs-table',ssc,ssa);renderSubs();
}

function renderSubs(){
    var p=pg(fSubs,sp);subsTbody.innerHTML='';
    if(!fSubs.length){subsEmpty.hidden=false;return;}
    subsEmpty.hidden=true;
    var off=(sp-1)*PS;
    p.forEach(function(s,idx){
        var r=document.createElement('tr');
        var tier=s.tier||'free';
        var tierBadge='<span class="badge badge-'+tier+'">'+tier.charAt(0).toUpperCase()+tier.slice(1)+'</span>';
        var bonus=s.bonusTokens||0;
        var maxTk=AI_CREDITS_MAP[tier]||100;
        var used=s.aiCreditsUsed||0;
        var curMonth=new Date().toISOString().slice(0,7);
        if((s.aiCreditsMonth||'')!==curMonth)used=0;
        var totalTk=maxTk+bonus;
        var remaining=Math.max(0,totalTk-used);
        var status=s.subscriptionStatus||'-';
        var statusColor=status==='active'?'#10b981':status==='canceled'?'#ef4444':'#8b949e';
        r.innerHTML='<td style="color:#999;font-size:12px">'+(off+idx+1)+'</td>'
            +'<td>'+esc(s.email||'')+'</td>'
            +'<td>'+tierBadge+'</td>'
            +'<td style="color:#f59e0b;font-weight:600;">'+bonus+'</td>'
            +'<td>'+used+' / '+totalTk+' <span style="color:#6b7280;font-size:11px;">('+remaining+' left)</span></td>'
            +'<td><span style="color:'+statusColor+';font-weight:600;">'+esc(status)+'</span></td>'
            +'<td style="font-size:11px;color:#6b7280;">'+esc(s.paddleSubscriptionId||'-')+'</td>'
            +'<td>'+fmtD(s.lastLoginAt)+'</td>'
            +'<td>'+fmtD(s.createdAt)+'</td>'
            +'<td style="text-align:center;"><span style="color:#f59e0b;font-weight:600;">'+(s.scheduleCount||0)+'</span></td>'
            +'<td class="actions-cell"><button class="btn-icon btn-icon-edit" data-a="es" data-e="'+ea(s.email)+'">&#9998;</button></td>';
        subsTbody.appendChild(r);
    });
    pgNav('subs-pagination',fSubs.length,sp,function(x){sp=x;renderSubs();});
}

function showSubModal(email){
    var s=allSubs.find(function(x){return x.email===email;});
    if(!s)return;
    editingSub=s;
    $('sub-email').value=s.email;
    $('sub-tier').value=s.tier||'free';
    $('sub-current-bonus').value=s.bonusTokens||0;
    $('sub-add-tokens').value='';
    $('sub-token-reason').value='';
    $('sub-form-error').textContent='';
    subModal.hidden=false;
}

function hideSubModal(){subModal.hidden=true;editingSub=null;}

async function saveSubTier(){
    if(!editingSub)return;
    var tier=$('sub-tier').value;
    $('sub-form-error').textContent='';
    try{
        showL();
        await api('PUT','/admin/subscribers/tier',{email:editingSub.email,tier:tier});
        notify('Tier updated to '+tier+' for '+editingSub.email,'success');
        hideSubModal();await loadSubscribers();
    }catch(e){$('sub-form-error').textContent=e.message||'Failed.';}
    finally{hideL();}
}

async function addSubTokens(){
    if(!editingSub)return;
    var tokens=parseInt($('sub-add-tokens').value,10);
    var reason=$('sub-token-reason').value.trim();
    $('sub-form-error').textContent='';
    if(!tokens||tokens<=0){$('sub-form-error').textContent='Enter a positive number of tokens.';return;}
    try{
        showL();
        var d=await api('POST','/admin/subscribers/tokens',{email:editingSub.email,tokens:tokens,reason:reason});
        notify(tokens+' tokens added to '+editingSub.email+' (new bonus: '+d.bonusTokens+')','success');
        hideSubModal();await loadSubscribers();
    }catch(e){$('sub-form-error').textContent=e.message||'Failed.';}
    finally{hideL();}
}

// Wire up subscribers events
if(subsSearch)subsSearch.addEventListener('input',function(){sp=1;applySubs();});
if($('sub-modal-close'))$('sub-modal-close').onclick=hideSubModal;
if($('sub-cancel-btn'))$('sub-cancel-btn').onclick=hideSubModal;
if($('sub-save-tier-btn'))$('sub-save-tier-btn').onclick=saveSubTier;
if($('sub-add-tokens-btn'))$('sub-add-tokens-btn').onclick=addSubTokens;

// Sortable headers for subs table
document.querySelectorAll('#subs-table th.sortable').forEach(function(h){
    h.style.cursor='pointer';
    h.onclick=function(){var c=h.dataset.col;if(ssc===c)ssa=!ssa;else{ssc=c;ssa=true;}sp=1;applySubs();};
});

// Delegate click for subscriber edit buttons
document.addEventListener('click',function(e){
    var btn=e.target.closest('[data-a="es"]');
    if(btn){showSubModal(btn.dataset.e);}
});


// ============================================================
// Schedules Tab
// ============================================================
var allScheds=[];var fScheds=[];var schp=1;var schsc='memberEmail';var schsa=true;var schedStats=null;
var schedTbody=$('sched-tbody');var schedEmpty=$('sched-empty');var schedSearch=$('sched-search');

async function loadSchedules(){
    try{showL();var d=await api('GET','/admin/schedules');allScheds=d.schedules||[];schedStats=d.stats||{};schp=1;renderSchedStats();applyScheds();}
    catch(e){notify('Failed to load schedules.','error');}
    finally{hideL();}
}

function renderSchedStats(){
    var el=$('sched-stats');if(!el||!schedStats)return;
    var st=schedStats;
    var failRate=st.executionsLast24h>0?Math.round(st.failuresLast24h/st.executionsLast24h*100):0;
    el.innerHTML='<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Total Schedules</div><div style="color:#e2e8f0;font-size:1.4em;font-weight:700;">'+st.totalSchedules+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Active</div><div style="color:#10b981;font-size:1.4em;font-weight:700;">'+st.activeSchedules+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Paused</div><div style="color:#9ca3af;font-size:1.4em;font-weight:700;">'+st.pausedSchedules+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Executions (24h)</div><div style="color:#3b82f6;font-size:1.4em;font-weight:700;">'+st.executionsLast24h+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Failure Rate (24h)</div><div style="color:'+(failRate>0?'#ef4444':'#10b981')+';font-size:1.4em;font-weight:700;">'+failRate+'%</div></div>';
}

function applyScheds(){
    var q=(schedSearch&&schedSearch.value||'').toLowerCase().trim();
    fScheds=q?allScheds.filter(function(s){return(s.memberEmail||'').toLowerCase().includes(q)||(s.type||'').toLowerCase().includes(q)||(s.status||'').toLowerCase().includes(q)||(s.accountId||'').toLowerCase().includes(q)||(s.name||'').toLowerCase().includes(q);}):allScheds.slice();
    fScheds=sortArr(fScheds,schsc,schsa);updSort('sched-table',schsc,schsa);renderScheds();
}

function renderScheds(){
    var p=pg(fScheds,schp);schedTbody.innerHTML='';
    if(!fScheds.length){schedEmpty.hidden=false;return;}
    schedEmpty.hidden=true;
    var off=(schp-1)*PS;
    p.forEach(function(s,idx){
        var r=document.createElement('tr');
        var statusColor=s.status==='active'?'#10b981':s.status==='paused'?'#9ca3af':'#8b949e';
        var lastRun=s.lastExecution?fmtD(s.lastExecution.timestamp):'-';
        var lastResult='-';
        if(s.lastExecution){
            var le=s.lastExecution;
            if(le.status==='success')lastResult='<span style="color:#10b981;">✅ '+le.successCount+'/'+le.resourceCount+'</span>';
            else if(le.status==='partial')lastResult='<span style="color:#f59e0b;">⚠️ '+le.successCount+'/'+le.resourceCount+'</span>';
            else if(le.status==='failure')lastResult='<span style="color:#ef4444;">❌ '+le.failureCount+'/'+le.resourceCount+'</span>';
            else lastResult=esc(le.status||'-');
        }
        r.innerHTML='<td style="color:#999;font-size:12px">'+(off+idx+1)+'</td>'
            +'<td>'+esc(s.memberEmail||'')+'</td>'
            +'<td>'+esc(s.name||'')+'</td>'
            +'<td>'+esc(s.type||'')+'</td>'
            +'<td style="font-size:11px;color:#6b7280;">'+esc(s.accountId||'-')+'</td>'
            +'<td><span style="color:'+statusColor+';font-weight:600;">'+esc(s.status||'-')+'</span></td>'
            +'<td>'+lastRun+'</td>'
            +'<td>'+lastResult+'</td>';
        schedTbody.appendChild(r);
    });
    pgNav('sched-pagination',fScheds.length,schp,function(x){schp=x;renderScheds();});
}

// Wire up schedules events
if(schedSearch)schedSearch.addEventListener('input',function(){schp=1;applyScheds();});

// Sortable headers for sched table
document.querySelectorAll('#sched-table th.sortable').forEach(function(h){
    h.style.cursor='pointer';
    h.onclick=function(){var c=h.dataset.col;if(schsc===c)schsa=!schsa;else{schsc=c;schsa=true;}schp=1;applyScheds();};
});


// ============================================================
// Tips Sync Tab
// ============================================================
var syncLogs=[];var syncMeta=null;var syncp=1;var syncLoaded=false;

async function loadSyncData(){
    try{showL();var d=await api('GET','/admin/tips-sync/logs');syncLogs=d.logs||[];syncMeta=d.metadata||null;syncLoaded=true;syncp=1;renderSyncStatus();renderSyncTable();}
    catch(e){notify('Failed to load sync data.','error');}
    finally{hideL();}
}

function renderSyncStatus(){
    var el=$('sync-status-cards');if(!el)return;
    if(!syncMeta){el.innerHTML='<p style="color:#8b949e;">No sync has been executed yet.</p>';return;}
    var m=syncMeta;
    var srcOk=(m.sourcesSucceeded||[]).length;
    var srcFail=(m.sourcesFailed||[]).length;
    var statusColor=srcFail===0?'#10b981':'#f59e0b';
    var statusText=srcFail===0?'✅ All Sources OK':'⚠️ '+srcFail+' Source(s) Failed';
    el.innerHTML='<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:140px;"><div style="color:#8b949e;font-size:0.8em;">Last Sync</div><div style="color:#e2e8f0;font-size:1.1em;font-weight:600;">'+fmtD(m.lastSyncTimestamp)+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:120px;"><div style="color:#8b949e;font-size:0.8em;">Status</div><div style="color:'+statusColor+';font-size:1.1em;font-weight:600;">'+statusText+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Duration</div><div style="color:#e2e8f0;font-size:1.1em;font-weight:600;">'+(m.durationMs||0)+'ms</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Trigger</div><div style="color:#e2e8f0;font-size:1.1em;font-weight:600;">'+esc(m.triggerType||'-')+'</div></div>'
        +'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;flex:1;min-width:100px;"><div style="color:#8b949e;font-size:0.8em;">Tips Changed</div><div style="color:#e2e8f0;font-size:1.1em;font-weight:600;"><span style="color:#10b981;">+'+(m.tipsInserted||0)+'</span> / <span style="color:#3b82f6;">~'+(m.tipsUpdated||0)+'</span> / <span style="color:#8b949e;">='+(m.tipsUnchanged||0)+'</span></div></div>';
}

function renderSyncTable(){
    var tbody=$('sync-tbody');var empty=$('sync-empty');
    if(!syncLogs.length){empty.hidden=false;tbody.innerHTML='';return;}
    empty.hidden=true;
    var p=pg(syncLogs,syncp);var off=(syncp-1)*PS;
    tbody.innerHTML='';
    p.forEach(function(log,idx){
        var r=document.createElement('tr');
        var st=log.status||'unknown';
        var stColor=st==='success'?'#10b981':'#ef4444';
        var stText=st==='success'?'✅ Success':'❌ Failed';
        var srcOk=(log.sourcesSucceeded||[]).join(', ')||'-';
        var srcFail=(log.sourcesFailed||[]).length;
        var srcHtml=srcFail>0?esc(srcOk)+' <span style="color:#ef4444;">('+srcFail+' failed)</span>':esc(srcOk);
        r.innerHTML='<td style="color:#999;font-size:12px">'+(off+idx+1)+'</td>'
            +'<td>'+fmtD(log.timestamp)+'</td>'
            +'<td>'+esc(log.triggerType||'-')+'</td>'
            +'<td style="color:#10b981;font-weight:600;">'+(log.tipsInserted||0)+'</td>'
            +'<td style="color:#3b82f6;font-weight:600;">'+(log.tipsUpdated||0)+'</td>'
            +'<td style="color:#8b949e;">'+(log.tipsUnchanged||0)+'</td>'
            +'<td>'+(log.durationMs||0)+'ms</td>'
            +'<td>'+srcHtml+'</td>'
            +'<td><span style="color:'+stColor+';font-weight:600;">'+stText+'</span></td>';
        tbody.appendChild(r);
    });
    pgNav('sync-pagination',syncLogs.length,syncp,function(x){syncp=x;renderSyncTable();});
}

async function triggerSync(){
    var btn=$('trigger-sync-btn');
    if(!btn||btn.disabled)return;
    btn.disabled=true;btn.textContent='Triggering...';
    try{await api('POST','/admin/tips-sync/trigger');notify('Sync triggered! Reloading in 15s...','success');setTimeout(function(){syncLoaded=false;loadSyncData();},15000);}
    catch(e){notify('Failed to trigger sync: '+(e.message||'Unknown error'),'error');}
    finally{btn.disabled=false;btn.textContent='⚡ Trigger Manual Sync';}
}

// Wire trigger button
var trigBtn=$('trigger-sync-btn');
if(trigBtn)trigBtn.onclick=triggerSync;


// ============================================================
// Transactions Tab
// ============================================================
var txnPage=1;var txnTotalPages=1;var txnDebounceTimer=null;var txnLoaded=false;
var txnFilters={search:'',date_from:'',date_to:'',score_min:'',score_max:'',status:'',source_handler:''};

var txnTbody=$('txn-tbody');var txnEmpty=$('txn-empty');var txnSearch=$('txn-search');
var txnPrevBtn=$('txn-prev-btn');var txnNextBtn=$('txn-next-btn');var txnPageIndicator=$('txn-page-indicator');
var txnDetailModal=$('txn-detail-modal');

function getScoreBadgeColor(score){
    if(score==null||score===''||isNaN(Number(score)))return'gray';
    var s=Number(score);
    if(s>=70)return'green';
    if(s>=40)return'yellow';
    return'red';
}

async function loadTransactions(page,filters){
    var params=[];
    params.push('page='+(page||1));
    params.push('page_size=50');
    if(filters.search)params.push('search='+encodeURIComponent(filters.search));
    if(filters.date_from)params.push('date_from='+encodeURIComponent(filters.date_from));
    if(filters.date_to)params.push('date_to='+encodeURIComponent(filters.date_to));
    if(filters.score_min)params.push('score_min='+encodeURIComponent(filters.score_min));
    if(filters.score_max)params.push('score_max='+encodeURIComponent(filters.score_max));
    if(filters.status)params.push('status='+encodeURIComponent(filters.status));
    if(filters.source_handler)params.push('source_handler='+encodeURIComponent(filters.source_handler));
    try{
        showL();
        var d=await api('GET','/admin/transactions?'+params.join('&'));
        txnLoaded=true;
        var transactions=d.transactions||[];
        var pagination=d.pagination||{};
        txnPage=pagination.page||1;
        txnTotalPages=pagination.total_pages||1;
        renderTransactionsTable(transactions);
        updateTxnPagination();
    }catch(e){
        notify('Failed to load transactions.','error');
    }finally{hideL();}
}

async function loadTransactionDetail(transaction_id,start_timestamp){
    try{
        showL();
        var d=await api('GET','/admin/transactions/detail?transaction_id='+encodeURIComponent(transaction_id)+'&start_timestamp='+encodeURIComponent(start_timestamp));
        renderDetailModal(d.transaction||d);
        txnDetailModal.hidden=false;
    }catch(e){
        notify('Failed to load transaction detail.','error');
    }finally{hideL();}
}

function renderTransactionsTable(transactions){
    txnTbody.innerHTML='';
    if(!transactions.length){txnEmpty.hidden=false;return;}
    txnEmpty.hidden=true;
    var off=(txnPage-1)*50;
    transactions.forEach(function(t,idx){
        var r=document.createElement('tr');
        r.style.cursor='pointer';
        r.dataset.txnId=t.transaction_id||'';
        r.dataset.txnTs=t.start_timestamp||'';
        var scoreBadge='';
        if(t.audit_status==='pending'){
            scoreBadge='<span class="score-badge score-pending">⏳ Pending</span>';
        }else if(t.audit_status==='failed'){
            scoreBadge='<span class="score-badge score-failed">✗ Failed</span>';
        }else if(t.audit_score!=null&&t.audit_score!==''){
            var color=getScoreBadgeColor(t.audit_score);
            scoreBadge='<span class="score-badge score-'+color+'">'+t.audit_score+'</span>';
        }else{
            scoreBadge='<span class="score-badge score-pending">⏳ Pending</span>';
        }
        var statusColor=t.status==='success'?'#10b981':'#ef4444';
        var statusText=t.status==='success'?'✅ Success':'❌ Error';
        r.innerHTML='<td style="color:#999;font-size:12px">'+(off+idx+1)+'</td>'
            +'<td>'+esc(t.user_email||'')+'</td>'
            +'<td>'+esc(t.function_name||'')+'</td>'
            +'<td>'+(t.duration_ms!=null?t.duration_ms+'ms':'-')+'</td>'
            +'<td>'+scoreBadge+'</td>'
            +'<td><span style="color:'+statusColor+';font-weight:600;">'+statusText+'</span></td>'
            +'<td>'+fmtD(t.start_timestamp)+'</td>';
        txnTbody.appendChild(r);
    });
}

function updateTxnPagination(){
    txnPageIndicator.textContent='Page '+txnPage+' of '+txnTotalPages;
    txnPrevBtn.disabled=txnPage<=1;
    txnNextBtn.disabled=txnPage>=txnTotalPages;
}

function renderDetailModal(entry){
    $('txn-detail-id').textContent=entry.transaction_id||'-';
    $('txn-detail-email').textContent=entry.user_email||'-';
    $('txn-detail-function').textContent=entry.function_name||'-';
    $('txn-detail-source').textContent=entry.source_handler||'-';
    var statusColor=entry.status==='success'?'#10b981':'#ef4444';
    $('txn-detail-status').innerHTML='<span style="color:'+statusColor+';font-weight:600;">'+esc(entry.status||'-')+'</span>';
    $('txn-detail-duration').textContent=(entry.duration_ms!=null?entry.duration_ms+'ms':'-');
    $('txn-detail-start').textContent=fmtD(entry.start_timestamp);
    $('txn-detail-end').textContent=fmtD(entry.end_timestamp);

    // Request/Response payloads formatted as JSON
    var reqPayload=entry.request_payload;
    var resPayload=entry.response_payload;
    try{
        if(typeof reqPayload==='string')reqPayload=JSON.parse(reqPayload);
        $('txn-detail-request').textContent=JSON.stringify(reqPayload,null,2);
    }catch(e){$('txn-detail-request').textContent=typeof reqPayload==='object'?JSON.stringify(reqPayload,null,2):String(reqPayload||'N/A');}
    try{
        if(typeof resPayload==='string')resPayload=JSON.parse(resPayload);
        $('txn-detail-response').textContent=JSON.stringify(resPayload,null,2);
    }catch(e){$('txn-detail-response').textContent=typeof resPayload==='object'?JSON.stringify(resPayload,null,2):String(resPayload||'N/A');}

    // Audit evaluation section
    var auditPending=$('txn-detail-audit-pending');
    var auditContent=$('txn-detail-audit-content');
    if(entry.audit_status==='pending'||(!entry.audit_score&&entry.audit_status!=='completed'&&entry.audit_status!=='failed')){
        auditPending.hidden=false;
        auditContent.hidden=true;
    }else{
        auditPending.hidden=true;
        auditContent.hidden=false;
        var scoreColor=getScoreBadgeColor(entry.audit_score);
        $('txn-detail-score').innerHTML='<span class="score-badge score-'+scoreColor+'" style="font-size:1.2em;">'+(entry.audit_score!=null?entry.audit_score:'-')+'</span>';
        $('txn-detail-audit-status').textContent=entry.audit_status||'-';
        $('txn-detail-accuracy').textContent=entry.audit_accuracy_assessment||'-';
        $('txn-detail-timing').textContent=entry.audit_timing_assessment||'-';
        // Render improvement suggestions as clickable recommendation chips
        var suggestionsEl=$('txn-detail-suggestions');
        var sugText=entry.audit_improvement_suggestions||'';
        if(sugText&&sugText!=='-'){
            var items=sugText.split(/\d+\.\s+/).filter(function(s){return s.trim();});
            if(items.length>1){
                var html='';
                items.forEach(function(item){
                    html+='<button class="txn-recommendation-chip" title="Click to copy" onclick="navigator.clipboard.writeText(this.textContent.trim());this.style.background=\'#10b981\';this.style.color=\'#fff\';setTimeout(function(){}.bind(this),1000);">'+esc(item.trim())+'</button>';
                });
                suggestionsEl.innerHTML=html;
            }else{
                suggestionsEl.textContent=sugText;
            }
        }else{
            suggestionsEl.textContent='-';
        }
    }

    // Copy buttons — store entry for the copy handlers
    window._currentTxnEntry=entry;
    var copyBtnsEl=$('txn-copy-buttons');
    if(copyBtnsEl){
        copyBtnsEl.innerHTML='<button class="btn btn-sm" id="txn-copy-text-btn" style="margin-right:8px;">&#128203; Copy as Text</button><button class="btn btn-sm" id="txn-copy-json-btn">&#123;&#125; Copy as JSON</button><span id="txn-copy-status" style="margin-left:10px;color:#10b981;font-size:12px;"></span>';
        $('txn-copy-text-btn').addEventListener('click',function(){
            var e=window._currentTxnEntry;
            var text='Transaction Detail\n'+'Transaction ID: '+e.transaction_id+'\nUser Email: '+e.user_email+'\nFunction: '+e.function_name+'\nSource Handler: '+e.source_handler+'\nStatus: '+e.status+'\nDuration: '+e.duration_ms+'ms\nStart Time: '+e.start_timestamp+'\nEnd Time: '+e.end_timestamp+'\n\nRequest Payload:\n'+$('txn-detail-request').textContent+'\n\nResponse Payload:\n'+$('txn-detail-response').textContent+'\n\nAudit Evaluation\nScore: '+(e.audit_score||'-')+'\nAudit Status: '+(e.audit_status||'-')+'\nAccuracy Assessment: '+(e.audit_accuracy_assessment||'-')+'\nTiming Assessment: '+(e.audit_timing_assessment||'-')+'\nImprovement Suggestions: '+(e.audit_improvement_suggestions||'-');
            navigator.clipboard.writeText(text).then(function(){$('txn-copy-status').textContent='Copied!';setTimeout(function(){$('txn-copy-status').textContent='';},2000);});
        });
        $('txn-copy-json-btn').addEventListener('click',function(){
            navigator.clipboard.writeText(JSON.stringify(window._currentTxnEntry,null,2)).then(function(){$('txn-copy-status').textContent='JSON copied!';setTimeout(function(){$('txn-copy-status').textContent='';},2000);});
        });
    }
}

function collectTxnFilters(){
    txnFilters.search=txnSearch.value.trim();
    txnFilters.date_from=$('txn-date-from').value;
    txnFilters.date_to=$('txn-date-to').value;
    txnFilters.score_min=$('txn-score-min').value;
    txnFilters.score_max=$('txn-score-max').value;
    txnFilters.status=$('txn-status-filter').value;
    txnFilters.source_handler=$('txn-source-filter').value;
}

// Search input with debounce (300ms)
if(txnSearch)txnSearch.addEventListener('input',function(){
    clearTimeout(txnDebounceTimer);
    txnDebounceTimer=setTimeout(function(){
        txnPage=1;
        collectTxnFilters();
        loadTransactions(txnPage,txnFilters);
    },300);
});

// Filter change handlers
['txn-date-from','txn-date-to','txn-score-min','txn-score-max','txn-status-filter','txn-source-filter'].forEach(function(id){
    var el=$(id);
    if(el)el.addEventListener('change',function(){
        txnPage=1;
        collectTxnFilters();
        loadTransactions(txnPage,txnFilters);
    });
});

// Row click handler to open detail modal
if(txnTbody)txnTbody.addEventListener('click',function(e){
    var row=e.target.closest('tr');
    if(!row||!row.dataset.txnId)return;
    loadTransactionDetail(row.dataset.txnId,row.dataset.txnTs);
});

// Pagination button handlers
if(txnPrevBtn)txnPrevBtn.addEventListener('click',function(){
    if(txnPage>1){
        txnPage--;
        collectTxnFilters();
        loadTransactions(txnPage,txnFilters);
    }
});
if(txnNextBtn)txnNextBtn.addEventListener('click',function(){
    if(txnPage<txnTotalPages){
        txnPage++;
        collectTxnFilters();
        loadTransactions(txnPage,txnFilters);
    }
});

// Modal close handlers
if($('txn-modal-close'))$('txn-modal-close').addEventListener('click',function(){txnDetailModal.hidden=true;});
if($('txn-modal-close-btn'))$('txn-modal-close-btn').addEventListener('click',function(){txnDetailModal.hidden=true;});
if(txnDetailModal)txnDetailModal.addEventListener('click',function(e){if(e.target===txnDetailModal)txnDetailModal.hidden=true;});

// Refresh button for Transactions tab — reloads without switching tabs
if($('txn-refresh-btn'))$('txn-refresh-btn').addEventListener('click',function(){collectTxnFilters();loadTransactions(txnPage,txnFilters);});

// Tab activation — update switchTab to include transactions
(function(){
    var origSwitch=switchTab;
    switchTab=function(n){
        origSwitch(n);
        var txnPanel=$('transactions-tab');
        if(txnPanel)txnPanel.hidden=n!=='transactions';
        if(n==='transactions'&&!txnLoaded){
            collectTxnFilters();
            loadTransactions(txnPage,txnFilters);
        }
    };
})();


/* ---- Tips export (JSON / CSV) ---- */
function _downloadFile(content, filename, mime){
  try{
    var blob=new Blob([content],{type:mime+';charset=utf-8;'});
    var url=URL.createObjectURL(blob);
    var a=document.createElement('a');
    a.href=url;a.download=filename;a.style.display='none';
    document.body.appendChild(a);a.click();
    document.body.removeChild(a);
    setTimeout(function(){URL.revokeObjectURL(url);},1000);
  }catch(e){notify('Export failed: '+(e.message||e),'error');}
}

function _tipsTimestamp(){
  var d=new Date();
  function p(n){return(n<10?'0':'')+n;}
  return d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+'-'+p(d.getHours())+p(d.getMinutes())+p(d.getSeconds());
}

function exportTipsJSON(){
  if(!allTips||!allTips.length){notify('No tips to export.','error');return;}
  _downloadFile(JSON.stringify(allTips,null,2),'tips-'+_tipsTimestamp()+'.json','application/json');
  notify('Exported '+allTips.length+' tips to JSON.','success');
}

function _csvCell(val){
  if(val===null||val===undefined)return '';
  var s=(typeof val==='object')?JSON.stringify(val):String(val);
  if(/[",\n\r]/.test(s))s='"'+s.replace(/"/g,'""')+'"';
  return s;
}

function exportTipsCSV(){
  if(!allTips||!allTips.length){notify('No tips to export.','error');return;}
  // Union of all keys across every record so no field is dropped
  var keys=[];var seen={};
  allTips.forEach(function(t){Object.keys(t||{}).forEach(function(k){if(!seen[k]){seen[k]=true;keys.push(k);}});});
  var lines=[keys.map(_csvCell).join(',')];
  allTips.forEach(function(t){
    lines.push(keys.map(function(k){return _csvCell(t?t[k]:'');}).join(','));
  });
  _downloadFile(lines.join('\r\n'),'tips-'+_tipsTimestamp()+'.csv','text/csv');
  notify('Exported '+allTips.length+' tips to CSV.','success');
}


// ============================================================
// Custom Plans Tab
// ============================================================
var allCustomPlans=[];var fCustomPlans=[];var cpp=1;var cpsc='email';var cpsa=true;var customPlansLoaded=false;
var customPlansTbody=$('custom-plans-tbody');var customPlansEmpty=$('custom-plans-empty');

async function loadCustomPlans(){
    try{
        showL();
        var d=await api('GET','/admin/custom-plans');
        allCustomPlans=d.customPlans||[];
        customPlansLoaded=true;
        cpp=1;
        renderCustomPlansStats(d.summary||{});
        applyCustomPlans();
    }catch(e){
        notify('Failed to load custom plans.','error');
    }finally{hideL();}
}

function renderCustomPlansStats(summary){
    var el=$('custom-plans-stats');if(!el)return;
    var mrr=summary.totalMonthlyRevenue||0;
    var active=summary.totalActiveCommitments||0;
    var grace=summary.gracePeriodCount||0;
    el.innerHTML='<div class="cp-summary-card"><div class="cp-summary-label">Monthly Recurring Revenue</div><div class="cp-summary-value" style="color:#10b981;">$'+mrr.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})+'</div></div>'
        +'<div class="cp-summary-card"><div class="cp-summary-label">Active Commitments</div><div class="cp-summary-value" style="color:#3b82f6;">'+active+'</div></div>'
        +'<div class="cp-summary-card"><div class="cp-summary-label">Grace Period</div><div class="cp-summary-value" style="color:'+(grace>0?'#f59e0b':'#10b981')+';">'+grace+'</div></div>';
}

function applyCustomPlans(){
    fCustomPlans=allCustomPlans.slice();
    fCustomPlans=sortArr(fCustomPlans,cpsc,cpsa);
    updSort('custom-plans-table',cpsc,cpsa);
    renderCustomPlans();
}

function renderCustomPlans(){
    var p=pg(fCustomPlans,cpp);
    customPlansTbody.innerHTML='';
    if(!fCustomPlans.length){customPlansEmpty.hidden=false;return;}
    customPlansEmpty.hidden=true;
    var off=(cpp-1)*PS;
    p.forEach(function(cp,idx){
        var r=document.createElement('tr');
        var status=cp.status||'unknown';
        var statusColor=status==='active'?'#10b981':status==='grace_period'?'#f59e0b':'#8b949e';
        var statusLabel=status==='grace_period'?'Grace Period':status.charAt(0).toUpperCase()+status.slice(1);
        if(status==='grace_period')r.classList.add('cp-grace-row');
        var startDate=cp.commitmentStartDate?cp.commitmentStartDate.substring(0,10):'—';
        var endDate=cp.commitmentEndDate?cp.commitmentEndDate.substring(0,10):'—';
        r.innerHTML='<td style="color:#999;font-size:12px">'+(off+idx+1)+'</td>'
            +'<td>'+esc(cp.email||'')+'</td>'
            +'<td>'+fmtM(cp.monthlyPrice)+'</td>'
            +'<td>'+((cp.tokenAllocation!=null)?cp.tokenAllocation.toLocaleString():'—')+'</td>'
            +'<td>'+startDate+'</td>'
            +'<td>'+endDate+'</td>'
            +'<td style="text-align:center;font-weight:600;">'+((cp.remainingMonths!=null)?cp.remainingMonths:'—')+'</td>'
            +'<td><span style="color:'+statusColor+';font-weight:600;">'+esc(statusLabel)+'</span></td>';
        customPlansTbody.appendChild(r);
    });
    pgNav('custom-plans-pagination',fCustomPlans.length,cpp,function(x){cpp=x;renderCustomPlans();});
}

// Sortable headers for custom plans table
document.querySelectorAll('#custom-plans-table th.sortable').forEach(function(h){
    h.style.cursor='pointer';
    h.onclick=function(){var c=h.dataset.col;if(cpsc===c)cpsa=!cpsa;else{cpsc=c;cpsa=true;}cpp=1;applyCustomPlans();};
});

// ============================================================
// Discount Configuration Editor
// ============================================================
var discountConfigLoaded=false;
var discountTiers=[];

async function loadDiscountConfig(){
    try{
        var d=await api('GET','/admin/custom-plans/config');
        var config=d.config||{};
        $('dc-base-price').value=config.baseMonthlyPrice||'';
        $('dc-base-tokens').value=config.baseTokenCount||'';
        discountTiers=(config.discountTiers||[]).map(function(t){return{minMonths:t.minMonths,maxMonths:t.maxMonths,discountPercent:t.discountPercent};});
        renderDiscountTiers();
        renderDiscountMeta(config);
        discountConfigLoaded=true;
        $('dc-error').textContent='';
        $('dc-success').textContent='';
    }catch(e){
        $('dc-error').textContent='Failed to load discount configuration: '+(e.message||'Unknown error');
    }
}

function renderDiscountTiers(){
    var tbody=$('dc-tiers-tbody');
    tbody.innerHTML='';
    discountTiers.forEach(function(tier,idx){
        var r=document.createElement('tr');
        r.innerHTML='<td><input type="number" min="3" max="24" value="'+tier.minMonths+'" data-idx="'+idx+'" data-field="minMonths"></td>'
            +'<td><input type="number" min="3" max="24" value="'+tier.maxMonths+'" data-idx="'+idx+'" data-field="maxMonths"></td>'
            +'<td><input type="number" min="1" max="50" value="'+tier.discountPercent+'" data-idx="'+idx+'" data-field="discountPercent"></td>'
            +'<td><button type="button" class="dc-remove-tier-btn" data-idx="'+idx+'">Remove</button></td>';
        tbody.appendChild(r);
    });
}

function renderDiscountMeta(config){
    var el=$('dc-meta');
    if(!el)return;
    if(config.updatedAt||config.updatedBy){
        var parts=[];
        if(config.updatedAt)parts.push('Last updated: '+fmtD(config.updatedAt));
        if(config.updatedBy)parts.push('by '+config.updatedBy);
        el.textContent=parts.join(' ');
    }else{
        el.textContent='';
    }
}

function collectDiscountTiers(){
    var rows=document.querySelectorAll('#dc-tiers-tbody tr');
    var tiers=[];
    rows.forEach(function(row){
        var inputs=row.querySelectorAll('input[type="number"]');
        var tier={};
        inputs.forEach(function(inp){
            tier[inp.dataset.field]=parseInt(inp.value,10)||0;
        });
        tiers.push(tier);
    });
    return tiers;
}

async function saveDiscountConfig(){
    $('dc-error').textContent='';
    $('dc-success').textContent='';
    var basePrice=parseFloat($('dc-base-price').value);
    var baseTokens=parseInt($('dc-base-tokens').value,10);
    var tiers=collectDiscountTiers();

    // Basic client-side validation
    if(!basePrice||basePrice<=200){
        $('dc-error').textContent='Base monthly price must be greater than $200.';
        return;
    }
    if(!baseTokens||baseTokens<1){
        $('dc-error').textContent='Base token count must be at least 1.';
        return;
    }

    var payload={
        baseMonthlyPrice:basePrice,
        baseTokenCount:baseTokens,
        discountTiers:tiers
    };

    try{
        showL();
        var d=await api('PUT','/admin/custom-plans/config',payload);
        $('dc-success').textContent='Configuration saved successfully.';
        // Refresh to show updated meta
        await loadDiscountConfig();
        notify('Discount configuration updated.','success');
    }catch(e){
        $('dc-error').textContent=e.message||'Failed to save configuration.';
    }finally{hideL();}
}

// Wire up discount config events
var dcAddTierBtn=$('dc-add-tier-btn');
if(dcAddTierBtn)dcAddTierBtn.onclick=function(){
    discountTiers.push({minMonths:3,maxMonths:6,discountPercent:5});
    renderDiscountTiers();
};

var dcTiersTbody=$('dc-tiers-tbody');
if(dcTiersTbody)dcTiersTbody.addEventListener('click',function(e){
    var btn=e.target.closest('.dc-remove-tier-btn');
    if(!btn)return;
    var idx=parseInt(btn.dataset.idx,10);
    discountTiers.splice(idx,1);
    renderDiscountTiers();
});

// Update discountTiers array when inputs change
if(dcTiersTbody)dcTiersTbody.addEventListener('input',function(e){
    var inp=e.target;
    if(inp.tagName!=='INPUT')return;
    var idx=parseInt(inp.dataset.idx,10);
    var field=inp.dataset.field;
    if(idx>=0&&field&&discountTiers[idx]){
        discountTiers[idx][field]=parseInt(inp.value,10)||0;
    }
});

var dcSaveBtn=$('dc-save-btn');
if(dcSaveBtn)dcSaveBtn.onclick=saveDiscountConfig;

// Tab activation — extend switchTab for custom-plans
(function(){
    var prevSwitch=switchTab;
    switchTab=function(n){
        prevSwitch(n);
        var cpPanel=$('custom-plans-tab');
        if(cpPanel)cpPanel.hidden=n!=='custom-plans';
        if(n==='custom-plans'&&!customPlansLoaded){
            loadCustomPlans();
            loadDiscountConfig();
        }
    };
})();
