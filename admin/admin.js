/* Admin Panel - SlashMyBill admin dashboard v3.1 */
var API_BASE_URL='https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';
var ADMIN_PASS='YuvalEyal1!';
var allLeads=[],allTips=[],editingTip=null,editingLead=null,deletingItem=null,deleteType=null,debounceTimer=null;
var PAGE_SIZE=15;
var leadsPage=1,tipsPage=1;
var leadsSortCol='timestamp',leadsSortAsc=false;
var tipsSortCol='service',tipsSortAsc=true;

var loginGate=document.getElementById('login-gate');
var gateForm=document.getElementById('gate-form');
var gatePassword=document.getElementById('gate-password');
var gateError=document.getElementById('gate-error');
var dashboardView=document.getElementById('dashboard-view');

gateForm.addEventListener('submit',function(e){
  e.preventDefault();
  var pw=gatePassword.value;
  if(!pw){gateError.textContent='Please enter password.';return;}
  if(pw===ADMIN_PASS){sessionStorage.setItem('admin_ok','1');loginGate.hidden=true;dashboardView.hidden=false;loadLeads();loadTips();}
  else{gateError.textContent='Wrong password.';gatePassword.value='';}
});
if(sessionStorage.getItem('admin_ok')==='1'){loginGate.hidden=true;dashboardView.hidden=false;}

var leadsPanel=document.getElementById('leads-tab');
var tipsPanel=document.getElementById('tips-tab');
var leadsSearch=document.getElementById('leads-search');
var tipsSearch=document.getElementById('tips-search');
var leadsTbody=document.getElementById('leads-tbody');
var tipsTbody=document.getElementById('tips-tbody');
var leadsEmpty=document.getElementById('leads-empty');
var tipsEmpty=document.getElementById('tips-empty');
var addTipBtn=document.getElementById('add-tip-btn');
var tipModal=document.getElementById('tip-modal');
var tipModalTitle=document.getElementById('tip-modal-title');
var tipForm=document.getElementById('tip-form');
var tipFormError=document.getElementById('tip-form-error');
var tipCancelBtn=document.getElementById('tip-cancel-btn');
var tipModalClose=document.getElementById('tip-modal-close');
var tipSubmitBtn=document.getElementById('tip-submit-btn');
var leadModal=document.getElementById('lead-modal');
var leadForm=document.getElementById('lead-form');
var leadFormError=document.getElementById('lead-form-error');
var leadCancelBtn=document.getElementById('lead-cancel-btn');
var leadModalClose=document.getElementById('lead-modal-close');
var leadSubmitBtn=document.getElementById('lead-submit-btn');
var deleteDialog=document.getElementById('delete-dialog');
var deleteDialogMsg=document.getElementById('delete-dialog-msg');
var deleteCancelBtn=document.getElementById('delete-cancel-btn');
var deleteConfirmBtn=document.getElementById('delete-confirm-btn');
var loadingOverlay=document.getElementById('loading-overlay');
var notification=document.getElementById('notification');
var notificationMessage=document.getElementById('notification-message');
var TIP_FIELDS=['service','tipId','category','title','description','estimatedSavings','difficulty','automatedCheck'];
var TIP_REQUIRED=['service','tipId','category','title','description','estimatedSavings','difficulty'];

function showNotification(msg,type){notificationMessage.textContent=msg;notification.className='notification notification-'+type;notification.hidden=false;setTimeout(function(){notification.hidden=true;},4000);}
function showLoading(){loadingOverlay.hidden=false;}
function hideLoading(){loadingOverlay.hidden=true;}
function switchTab(name){document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.toggle('active',b.dataset.tab===name);});leadsPanel.hidden=(name!=='leads');tipsPanel.hidden=(name!=='tips');}
function formatDate(ts){if(!ts)return'';try{var d=new Date(ts);return isNaN(d.getTime())?ts:d.toLocaleString('en-US',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}catch(e){return ts;}}
function fmtMoney(v){if(v===undefined||v===null||v==='')return'-';var n=Number(v);return isNaN(n)?String(v):'$'+n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});}
function escapeHtml(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function escapeAttr(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function debounce(fn,ms){return function(){var a=arguments,t=this;clearTimeout(debounceTimer);debounceTimer=setTimeout(function(){fn.apply(t,a);},ms);};}

async function apiRequest(method,path,body){
  var opts={method:method,headers:{'Content-Type':'application/json'}};
  if(body)opts.body=JSON.stringify(body);
  var res=await fetch(API_BASE_URL+path,opts);
  var data=await res.json();
  if(!res.ok)throw{status:res.status,message:data.message||'Something went wrong'};
  return data;
}

function sortData(arr,col,asc){
  return arr.slice().sort(function(a,b){
    var va=a[col],vb=b[col];
    if(va===undefined||va===null)va='';
    if(vb===undefined||vb===null)vb='';
    var na=Number(va),nb=Number(vb);
    if(!isNaN(na)&&!isNaN(nb)){return asc?na-nb:nb-na;}
    va=String(va).toLowerCase();vb=String(vb).toLowerCase();
    if(va<vb)return asc?-1:1;if(va>vb)return asc?1:-1;return 0;
  });
}
function updateSortHeaders(tableId,col,asc){
  document.querySelectorAll('#'+tableId+' thead th.sortable').forEach(function(th){
    th.classList.remove('sort-asc','sort-desc');
    if(th.dataset.col===col)th.classList.add(asc?'sort-asc':'sort-desc');
  });
}
function paginate(arr,page){var s=(page-1)*PAGE_SIZE;return arr.slice(s,s+PAGE_SIZE);}
function renderPagination(containerId,totalItems,currentPage,onPageChange){
  var c=document.getElementById(containerId);
  if(!c){c=document.createElement('div');c.id=containerId;c.className='pagination';}
  c.innerHTML='';var tp=Math.ceil(totalItems/PAGE_SIZE);
  if(tp<=1){if(c.parentNode)c.parentNode.removeChild(c);return;}
  function mk(l,p,dis,act){var b=document.createElement('button');b.className='page-btn';b.textContent=l;if(act)b.classList.add('active');if(dis)b.disabled=true;else b.addEventListener('click',function(){onPageChange(p);});return b;}
  c.appendChild(mk('« Prev',currentPage-1,currentPage<=1,false));
  var sp=Math.max(1,currentPage-2),ep=Math.min(tp,currentPage+2);
  if(sp>1){c.appendChild(mk('1',1,false,currentPage===1));if(sp>2){var d=document.createElement('span');d.className='page-info';d.textContent='...';c.appendChild(d);}}
  for(var p=sp;p<=ep;p++)c.appendChild(mk(String(p),p,false,p===currentPage));
  if(ep<tp){if(ep<tp-1){var d2=document.createElement('span');d2.className='page-info';d2.textContent='...';c.appendChild(d2);}c.appendChild(mk(String(tp),tp,false,currentPage===tp));}
  c.appendChild(mk('Next »',currentPage+1,currentPage>=tp,false));
  var info=document.createElement('span');info.className='page-info';info.textContent='('+totalItems+' records)';c.appendChild(info);
  var w=document.getElementById(containerId.replace('-pagination','-tab'));
  if(w&&!document.getElementById(containerId))w.appendChild(c);
}

/* LEADS */
var filteredLeads=[];
async function loadLeads(){try{showLoading();var data=await apiRequest('GET','/admin/leads');allLeads=data.leads||[];leadsPage=1;applyLeads();}catch(e){showNotification('Failed to load leads.','error');}finally{hideLoading();}}
function applyLeads(){
  var q=(leadsSearch.value||'').toLowerCase().trim();
  filteredLeads=q?allLeads.filter(function(l){return(l.email||'').toLowerCase().indexOf(q)>=0||(l.name||'').toLowerCase().indexOf(q)>=0||(l.company||'').toLowerCase().indexOf(q)>=0;}):allLeads.slice();
  filteredLeads=sortData(filteredLeads,leadsSortCol,leadsSortAsc);
  updateSortHeaders('leads-table',leadsSortCol,leadsSortAsc);
  renderLeadsPage();
}
function renderLeadsPage(){
  var page=paginate(filteredLeads,leadsPage);
  leadsTbody.innerHTML='';
  if(!filteredLeads.length){leadsEmpty.hidden=false;renderPagination('leads-pagination',0,1,function(){});return;}
  leadsEmpty.hidden=true;
  page.forEach(function(l){
    var tr=document.createElement('tr');
    tr.innerHTML='<td>'+escapeHtml(l.email||'')+'</td><td>'+escapeHtml(l.name||'')+'</td><td>'+escapeHtml(l.company||'')+'</td><td>'+escapeHtml(l.phone||'')+'</td><td>'+escapeHtml(l.fileName||'')+'</td><td>'+fmtMoney(l.billTotalCost)+'</td><td>'+fmtMoney(l.monthlySavingsMin)+' - '+fmtMoney(l.monthlySavingsMax)+'</td><td>'+fmtMoney(l.yearlySavingsMin)+' - '+fmtMoney(l.yearlySavingsMax)+'</td><td>'+formatDate(l.timestamp)+'</td><td class="actions-cell"><button class="btn-icon btn-icon-edit" data-action="edit-lead" data-email="'+escapeAttr(l.email)+'" data-ts="'+escapeAttr(l.timestamp)+'" title="Edit">&#9998;</button><button class="btn-icon btn-icon-delete" data-action="delete-lead" data-email="'+escapeAttr(l.email)+'" data-ts="'+escapeAttr(l.timestamp)+'" title="Delete">&#128465;</button></td>';
    leadsTbody.appendChild(tr);
  });
  renderPagination('leads-pagination',filteredLeads.length,leadsPage,function(p){leadsPage=p;renderLeadsPage();});
}
function showLeadForm(lead){
  leadFormError.textContent='';editingLead=lead;
  document.getElementById('lead-name').value=lead.name||'';
  document.getElementById('lead-company').value=lead.company||'';
  document.getElementById('lead-phone').value=lead.phone||'';
  document.getElementById('lead-notes').value=lead.notes||'';
  leadModal.hidden=false;
}
function hideLeadForm(){leadModal.hidden=true;editingLead=null;}
async function saveLead(){
  if(!editingLead)return;leadFormError.textContent='';
  var body={email:editingLead.email,timestamp:editingLead.timestamp,name:document.getElementById('lead-name').value.trim(),company:document.getElementById('lead-company').value.trim(),phone:document.getElementById('lead-phone').value.trim(),notes:document.getElementById('lead-notes').value.trim()};
  try{showLoading();await apiRequest('PUT','/admin/leads',body);showNotification('Lead updated.','success');hideLeadForm();await loadLeads();}
  catch(e){leadFormError.textContent=e.message||'Failed to save.';}finally{hideLoading();}
}

/* TIPS */
var filteredTips=[];
async function loadTips(){try{showLoading();var data=await apiRequest('GET','/admin/tips');allTips=data.tips||[];tipsPage=1;applyTips();}catch(e){showNotification('Failed to load tips.','error');}finally{hideLoading();}}
function applyTips(){
  var q=(tipsSearch.value||'').toLowerCase().trim();
  filteredTips=q?allTips.filter(function(t){return(t.service||'').toLowerCase().indexOf(q)>=0||(t.title||'').toLowerCase().indexOf(q)>=0||(t.category||'').toLowerCase().indexOf(q)>=0;}):allTips.slice();
  filteredTips=sortData(filteredTips,tipsSortCol,tipsSortAsc);
  updateSortHeaders('tips-table',tipsSortCol,tipsSortAsc);
  renderTipsPage();
}
function renderTipsPage(){
  var page=paginate(filteredTips,tipsPage);
  tipsTbody.innerHTML='';
  if(!filteredTips.length){tipsEmpty.hidden=false;renderPagination('tips-pagination',0,1,function(){});return;}
  tipsEmpty.hidden=true;
  page.forEach(function(t){
    var tr=document.createElement('tr');
    var sb=t.automatedCheck?'<span class="script-badge" data-action="view-script" data-service="'+escapeAttr(t.service)+'" data-tipid="'+escapeAttr(t.tipId)+'" title="View script">Script</span>':'-';
    tr.innerHTML='<td>'+escapeHtml(t.service||'')+'</td><td>'+escapeHtml(t.tipId||'')+'</td><td>'+escapeHtml(t.category||'')+'</td><td>'+escapeHtml(t.title||'')+'</td><td title="'+escapeAttr(t.description)+'">'+escapeHtml(t.description||'')+'</td><td>'+escapeHtml(t.estimatedSavings||'')+'</td><td><span class="badge badge-'+(t.difficulty||'').toLowerCase()+'">'+escapeHtml(t.difficulty||'')+'</span></td><td>'+sb+'</td><td class="actions-cell"><button class="btn-icon btn-icon-edit" data-action="edit" data-service="'+escapeAttr(t.service)+'" data-tipid="'+escapeAttr(t.tipId)+'" title="Edit">&#9998;</button><button class="btn-icon btn-icon-delete" data-action="delete" data-service="'+escapeAttr(t.service)+'" data-tipid="'+escapeAttr(t.tipId)+'" title="Delete">&#128465;</button></td>';
    tipsTbody.appendChild(tr);
  });
  renderPagination('tips-pagination',filteredTips.length,tipsPage,function(p){tipsPage=p;renderTipsPage();});
}
function showTipForm(tip){
  tipFormError.textContent='';
  if(tip){editingTip=tip;tipModalTitle.textContent='Edit Tip';tipSubmitBtn.textContent='Update Tip';TIP_FIELDS.forEach(function(f){var el=document.getElementById('tip-'+f);if(el)el.value=tip[f]||'';});document.getElementById('tip-service').disabled=true;document.getElementById('tip-tipId').disabled=true;}
  else{editingTip=null;tipModalTitle.textContent='Add Tip';tipSubmitBtn.textContent='Save Tip';TIP_FIELDS.forEach(function(f){var el=document.getElementById('tip-'+f);if(el)el.value='';});document.getElementById('tip-service').disabled=false;document.getElementById('tip-tipId').disabled=false;}
  tipModal.hidden=false;
}
function hideTipForm(){tipModal.hidden=true;editingTip=null;}
async function saveTip(){
  tipFormError.textContent='';var tipData={};
  for(var i=0;i<TIP_REQUIRED.length;i++){var f=TIP_REQUIRED[i],val=document.getElementById('tip-'+f).value.trim();if(!val){tipFormError.textContent='All required fields must be filled.';return;}tipData[f]=val;}
  var ac=document.getElementById('tip-automatedCheck');if(ac&&ac.value.trim())tipData.automatedCheck=ac.value.trim();
  try{showLoading();if(editingTip){await apiRequest('PUT','/admin/tips',tipData);showNotification('Tip updated.','success');}else{await apiRequest('POST','/admin/tips',tipData);showNotification('Tip created.','success');}hideTipForm();await loadTips();}
  catch(e){if(e.status===409)tipFormError.textContent='A tip with this service and ID already exists.';else tipFormError.textContent=e.message||'Failed to save tip.';}finally{hideLoading();}
}

/* DELETE */
function showDeleteDialog(type,item){deleteType=type;deletingItem=item;deleteDialogMsg.textContent='Are you sure you want to delete this '+type+'? This cannot be undone.';deleteDialog.hidden=false;}
function hideDeleteDialog(){deleteDialog.hidden=true;deletingItem=null;deleteType=null;}
async function confirmDelete(){
  if(!deletingItem)return;hideDeleteDialog();
  try{showLoading();
    if(deleteType==='tip'){await apiRequest('DELETE','/admin/tips',{service:deletingItem.service,tipId:deletingItem.tipId});showNotification('Tip deleted.','success');await loadTips();}
    else if(deleteType==='lead'){await apiRequest('DELETE','/admin/leads',{email:deletingItem.email,timestamp:deletingItem.timestamp});showNotification('Lead deleted.','success');await loadLeads();}
  }catch(e){showNotification(e.message||'Failed to delete.','error');}finally{hideLoading();}
}

/* Script viewer */
function showScript(svc,tid){
  var tip=allTips.find(function(t){return t.service===svc&&t.tipId===tid;});
  if(!tip||!tip.automatedCheck)return;
  document.getElementById('script-modal-title').textContent=tip.title+' - Script';
  document.getElementById('script-modal-content').textContent=tip.automatedCheck;
  document.getElementById('script-modal').hidden=false;
}

/* EVENT LISTENERS */
document.querySelectorAll('.tab-btn').forEach(function(btn){btn.addEventListener('click',function(){switchTab(btn.dataset.tab);});});
leadsSearch.addEventListener('input',debounce(function(){leadsPage=1;applyLeads();},200));
tipsSearch.addEventListener('input',debounce(function(){tipsPage=1;applyTips();},200));
addTipBtn.addEventListener('click',function(){showTipForm(null);});
tipForm.addEventListener('submit',function(e){e.preventDefault();saveTip();});
tipCancelBtn.addEventListener('click',hideTipForm);
tipModalClose.addEventListener('click',hideTipForm);
leadForm.addEventListener('submit',function(e){e.preventDefault();saveLead();});
leadCancelBtn.addEventListener('click',hideLeadForm);
leadModalClose.addEventListener('click',hideLeadForm);
deleteCancelBtn.addEventListener('click',hideDeleteDialog);
deleteConfirmBtn.addEventListener('click',confirmDelete);

document.querySelectorAll('#leads-table thead th.sortable').forEach(function(th){
  th.addEventListener('click',function(){var col=th.dataset.col;if(leadsSortCol===col)leadsSortAsc=!leadsSortAsc;else{leadsSortCol=col;leadsSortAsc=true;}leadsPage=1;applyLeads();});
});
document.querySelectorAll('#tips-table thead th.sortable').forEach(function(th){
  th.addEventListener('click',function(){var col=th.dataset.col;if(tipsSortCol===col)tipsSortAsc=!tipsSortAsc;else{tipsSortCol=col;tipsSortAsc=true;}tipsPage=1;applyTips();});
});

tipsTbody.addEventListener('click',function(e){
  var btn=e.target.closest('[data-action]');if(!btn)return;
  var action=btn.dataset.action,svc=btn.dataset.service,tid=btn.dataset.tipid;
  if(action==='edit'){var tip=allTips.find(function(t){return t.service===svc&&t.tipId===tid;});if(tip)showTipForm(tip);}
  else if(action==='delete'){showDeleteDialog('tip',{service:svc,tipId:tid});}
  else if(action==='view-script'){showScript(svc,tid);}
});
leadsTbody.addEventListener('click',function(e){
  var btn=e.target.closest('[data-action]');if(!btn)return;
  var action=btn.dataset.action,email=btn.dataset.email,ts=btn.dataset.ts;
  if(action==='edit-lead'){var lead=allLeads.find(function(l){return l.email===email&&l.timestamp===ts;});if(lead)showLeadForm(lead);}
  else if(action==='delete-lead'){showDeleteDialog('lead',{email:email,timestamp:ts});}
});

tipModal.addEventListener('click',function(e){if(e.target===tipModal)hideTipForm();});
leadModal.addEventListener('click',function(e){if(e.target===leadModal)hideLeadForm();});
deleteDialog.addEventListener('click',function(e){if(e.target===deleteDialog)hideDeleteDialog();});
document.getElementById('script-modal').addEventListener('click',function(e){if(e.target===document.getElementById('script-modal'))document.getElementById('script-modal').hidden=true;});
document.getElementById('script-modal-close').addEventListener('click',function(){document.getElementById('script-modal').hidden=true;});
document.getElementById('script-close-btn').addEventListener('click',function(){document.getElementById('script-modal').hidden=true;});
document.getElementById('script-copy-btn').addEventListener('click',function(){navigator.clipboard.writeText(document.getElementById('script-modal-content').textContent);showNotification('Copied to clipboard.','success');});

if(sessionStorage.getItem('admin_ok')==='1'){loadLeads();loadTips();}