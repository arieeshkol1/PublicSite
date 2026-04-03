/* Admin Panel v4 - SlashMyBill */
var API='https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';
var PASS='YuvalEyal1!';
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
var TF=['service','tipId','category','title','description','estimatedSavings','difficulty','automatedCheck'];
var TR=['service','tipId','category','title','description','estimatedSavings','difficulty'];

gateForm.onsubmit=function(e){e.preventDefault();var p=gatePassword.value;if(!p){gateError.textContent='Enter password.';return;}if(p===PASS){sessionStorage.setItem('ok','1');loginGate.hidden=true;dash.hidden=false;load();}else{gateError.textContent='Wrong password.';gatePassword.value='';}};
if(sessionStorage.getItem('ok')==='1'){loginGate.hidden=true;dash.hidden=false;}

function notify(m,t){notifMsg.textContent=m;notif.className='notification notification-'+t;notif.hidden=false;setTimeout(function(){notif.hidden=true;},4000);}
function showL(){loading.hidden=false;}function hideL(){loading.hidden=true;}
function fmtD(ts){if(!ts)return'';try{var d=new Date(ts);return isNaN(d)?ts:d.toLocaleString('en-US',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}catch(e){return ts;}}
function fmtM(v){if(v==null||v==='')return'-';var n=Number(v);return isNaN(n)?String(v):'$'+n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
function esc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function ea(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function switchTab(n){document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.toggle('active',b.dataset.tab===n);});leadsPanel.hidden=n!=='leads';tipsPanel.hidden=n!=='tips';feedbackPanel.hidden=n!=='feedback';if(n==='feedback'&&!allFeedback.length)loadFeedback();}

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
async function loadTips(){try{showL();var d=await api('GET','/admin/tips');allTips=d.tips||[];tp=1;applyTips();}catch(e){notify('Failed to load tips.','error');}finally{hideL();}}
function applyTips(){var q=(tipsSearch.value||'').toLowerCase().trim();fTips=q?allTips.filter(function(t){return(t.service||'').toLowerCase().includes(q)||(t.title||'').toLowerCase().includes(q)||(t.category||'').toLowerCase().includes(q);}):allTips.slice();fTips=sortArr(fTips,tsc,tsa);updSort('tips-table',tsc,tsa);renderTips();}
function renderTips(){var p=pg(fTips,tp);tipsTbody.innerHTML='';if(!fTips.length){tipsEmpty.hidden=false;return;}tipsEmpty.hidden=true;var tOff=(tp-1)*PS;p.forEach(function(t,idx){var r=document.createElement('tr');var sb=t.automatedCheck?'<span class="script-badge" data-a="vs" data-s="'+ea(t.service)+'" data-i="'+ea(t.tipId)+'">&#9881; Check</span>':'-';r.innerHTML='<td style="color:#999;font-size:12px">'+(tOff+idx+1)+'</td><td>'+esc(t.service||'')+'</td><td>'+esc(t.tipId||'')+'</td><td>'+esc(t.category||'')+'</td><td>'+esc(t.title||'')+'</td><td title="'+ea(t.description)+'">'+esc(t.description||'')+'</td><td>'+esc(t.estimatedSavings||'')+'</td><td><span class="badge badge-'+(t.difficulty||'').toLowerCase()+'">'+esc(t.difficulty||'')+'</span></td><td>'+sb+'</td><td class="actions-cell"><button class="btn-icon btn-icon-edit" data-a="et" data-s="'+ea(t.service)+'" data-i="'+ea(t.tipId)+'">&#9998;</button> <button class="btn-icon btn-icon-delete" data-a="dt" data-s="'+ea(t.service)+'" data-i="'+ea(t.tipId)+'">&#128465;</button></td>';tipsTbody.appendChild(r);});pgNav('tips-pagination',fTips.length,tp,function(x){tp=x;renderTips();});}
function showTipForm(t){tipFormError.textContent='';if(t){editingTip=t;tipModalTitle.textContent='Edit Tip';tipSubmitBtn.textContent='Update Tip';TF.forEach(function(f){var e=$('tip-'+f);if(e)e.value=t[f]||'';});$('tip-service').disabled=true;$('tip-tipId').disabled=true;}else{editingTip=null;tipModalTitle.textContent='Add Tip';tipSubmitBtn.textContent='Save Tip';TF.forEach(function(f){var e=$('tip-'+f);if(e)e.value='';});$('tip-service').disabled=false;$('tip-tipId').disabled=false;}tipModal.hidden=false;}
function hideTipForm(){tipModal.hidden=true;editingTip=null;}
async function saveTip(){tipFormError.textContent='';var d={};for(var i=0;i<TR.length;i++){var f=TR[i],v=$('tip-'+f).value.trim();if(!v){tipFormError.textContent='All required fields must be filled.';return;}d[f]=v;}var ac=$('tip-automatedCheck');if(ac&&ac.value.trim())d.automatedCheck=ac.value.trim();try{showL();if(editingTip){await api('PUT','/admin/tips',d);notify('Tip updated.','success');}else{await api('POST','/admin/tips',d);notify('Tip created.','success');}hideTipForm();await loadTips();}catch(e){tipFormError.textContent=e.message||'Failed.';}finally{hideL();}}

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
async function loadFeedback(){try{showL();var d=await api('GET','/admin/feedback');allFeedback=d.feedback||[];feedbackLoaded=true;fp=1;applyFeedback();}catch(e){notify('Failed to load feedback.','error');}finally{hideL();}}
function applyFeedback(){var q=(feedbackSearch.value||'').toLowerCase().trim();fFeedback=q?allFeedback.filter(function(f){return(f.memberEmail||'').toLowerCase().includes(q)||(f.userQuestion||'').toLowerCase().includes(q)||(f.relatedService||'').toLowerCase().includes(q)||(f.userCorrection||'').toLowerCase().includes(q);}):allFeedback.slice();fFeedback=sortArr(fFeedback,fsc,fsa);updSort('feedback-table',fsc,fsa);renderFeedback();}
function truncText(s,max){if(!s)return'';return s.length>max?s.substring(0,max)+'…':s;}
function renderFeedback(){var p=pg(fFeedback,fp);feedbackTbody.innerHTML='';if(!fFeedback.length){feedbackEmpty.hidden=false;return;}feedbackEmpty.hidden=true;var fOff=(fp-1)*PS;p.forEach(function(f,idx){var r=document.createElement('tr');var h=f.feedbackScore;var scoreHtml=h==='yes'?'<span style="color:#10b981;font-weight:700">👍 yes</span>':h==='no'?'<span style="color:#ef4444;font-weight:700">👎 no</span>':esc(h||'-');var qTrunc=truncText(f.userQuestion||'',60);var cTrunc=truncText(f.userCorrection||'',60);r.innerHTML='<td style="color:#999;font-size:12px">'+(fOff+idx+1)+'</td><td>'+esc(f.memberEmail||'')+'</td><td title="'+ea(f.userQuestion||'')+'">'+esc(qTrunc)+'</td><td>'+scoreHtml+'</td><td>'+esc(f.relatedService||'')+'</td><td title="'+ea(f.userCorrection||'')+'">'+esc(cTrunc)+'</td><td>'+fmtD(f.createdAt)+'</td>';feedbackTbody.appendChild(r);});pgNav('feedback-pagination',fFeedback.length,fp,function(x){fp=x;renderFeedback();});}

/* Feedback table sorting */
$('feedback-table').querySelector('thead').onclick=function(e){var th=e.target.closest('.sortable');if(!th)return;var c=th.dataset.col;if(fsc===c)fsa=!fsa;else{fsc=c;fsa=true;}fp=1;applyFeedback();};
$('leads-table').querySelector('thead').onclick=function(e){var th=e.target.closest('.sortable');if(!th)return;var c=th.dataset.col;if(lsc===c)lsa=!lsa;else{lsc=c;lsa=true;}lp=1;applyLeads();};
$('tips-table').querySelector('thead').onclick=function(e){var th=e.target.closest('.sortable');if(!th)return;var c=th.dataset.col;if(tsc===c)tsa=!tsa;else{tsc=c;tsa=true;}tp=1;applyTips();};

function load(){loadLeads();loadTips();}
if(sessionStorage.getItem('ok')==='1')load();