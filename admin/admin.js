/* Admin Panel - Slash My Bill admin dashboard */
var API_BASE_URL = 'https://l2fd4h481h.execute-api.us-east-1.amazonaws.com';
var allLeads = [], allTips = [], editingTip = null, deletingTip = null, debounceTimer = null;
var loginView = document.getElementById('login-view');
var dashboardView = document.getElementById('dashboard-view');
var loginForm = document.getElementById('login-form');
var loginUsername = document.getElementById('login-username');
var loginPassword = document.getElementById('login-password');
var loginError = document.getElementById('login-error');
var headerUsername = document.getElementById('header-username');
var logoutBtn = document.getElementById('logout-btn');
var leadsPanel = document.getElementById('leads-tab');
var tipsPanel = document.getElementById('tips-tab');
var leadsSearch = document.getElementById('leads-search');
var tipsSearch = document.getElementById('tips-search');
var leadsTbody = document.getElementById('leads-tbody');
var tipsTbody = document.getElementById('tips-tbody');
var leadsEmpty = document.getElementById('leads-empty');
var tipsEmpty = document.getElementById('tips-empty');
var addTipBtn = document.getElementById('add-tip-btn');
var tipModal = document.getElementById('tip-modal');
var tipModalTitle = document.getElementById('tip-modal-title');
var tipForm = document.getElementById('tip-form');
var tipFormError = document.getElementById('tip-form-error');
var tipCancelBtn = document.getElementById('tip-cancel-btn');
var tipModalClose = document.getElementById('tip-modal-close');
var tipSubmitBtn = document.getElementById('tip-submit-btn');
var deleteDialog = document.getElementById('delete-dialog');
var deleteCancelBtn = document.getElementById('delete-cancel-btn');
var deleteConfirmBtn = document.getElementById('delete-confirm-btn');
var loadingOverlay = document.getElementById('loading-overlay');
var notification = document.getElementById('notification');
var notificationMessage = document.getElementById('notification-message');
var TIP_FIELDS = ['service','tipId','category','title','description','estimatedSavings','difficulty'];

function showNotification(msg,type){notificationMessage.textContent=msg;notification.className='notification notification-'+type;notification.hidden=false;setTimeout(function(){notification.hidden=true;},4000);}
function showLoading(){loadingOverlay.hidden=false;}
function hideLoading(){loadingOverlay.hidden=true;}
function showLogin(){loginView.hidden=false;dashboardView.hidden=true;loginPassword.value='';loginError.textContent='';}
function showDashboard(){loginView.hidden=true;dashboardView.hidden=false;headerUsername.textContent=sessionStorage.getItem('admin_username')||'';}
function switchTab(name){document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.toggle('active',b.dataset.tab===name);});leadsPanel.hidden=(name!=='leads');tipsPanel.hidden=(name!=='tips');}
function formatDate(ts){if(!ts)return '';try{var d=new Date(ts);return isNaN(d.getTime())?ts:d.toLocaleString('en-US',{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});}catch(e){return ts;}}
function escapeHtml(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function escapeAttr(s){return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function debounce(fn,ms){return function(){var a=arguments,t=this;clearTimeout(debounceTimer);debounceTimer=setTimeout(function(){fn.apply(t,a);},ms);};}

async function login(username,password){
showLoading();loginError.textContent='';
try{var res=await fetch(API_BASE_URL+'/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username,password:password})});
var data=await res.json();if(!res.ok){loginError.textContent=data.message||'Invalid username or password';return;}
sessionStorage.setItem('admin_token',data.token);sessionStorage.setItem('admin_username',data.username);showDashboard();loadLeads();loadTips();
}catch(e){loginError.textContent='Unable to connect. Please check your connection.';}finally{hideLoading();}}

function logout(){sessionStorage.removeItem('admin_token');sessionStorage.removeItem('admin_username');allLeads=[];allTips=[];leadsTbody.innerHTML='';tipsTbody.innerHTML='';leadsSearch.value='';tipsSearch.value='';showLogin();}

async function apiRequest(method,path,body){
var token=sessionStorage.getItem('admin_token');var opts={method:method,headers:{'Content-Type':'application/json','Authorization':'Bearer '+token}};
if(body)opts.body=JSON.stringify(body);var res=await fetch(API_BASE_URL+path,opts);
if(res.status===401){showNotification('Session expired. Please log in again.','error');logout();throw new Error('Unauthorized');}
var data=await res.json();if(!res.ok)throw{status:res.status,message:data.message||'Something went wrong'};return data;}

async function loadLeads(){try{showLoading();var data=await apiRequest('GET','/admin/leads');allLeads=data.leads||[];renderLeads(allLeads);}catch(e){if(e.message!=='Unauthorized')showNotification('Failed to load leads.','error');}finally{hideLoading();}}
function renderLeads(leads){leadsTbody.innerHTML='';if(!leads.length){leadsEmpty.hidden=false;return;}leadsEmpty.hidden=true;leads.forEach(function(l){var tr=document.createElement('tr');tr.innerHTML='<td>'+escapeHtml(l.email||'')+'</td><td>'+escapeHtml(l.name||'')+'</td><td>'+escapeHtml(l.company||'')+'</td><td>'+escapeHtml(l.phone||'')+'</td><td>'+escapeHtml(l.fileName||'')+'</td><td>'+formatDate(l.timestamp)+'</td>';leadsTbody.appendChild(tr);});}
function filterLeads(q){q=(q||'').toLowerCase().trim();if(!q){renderLeads(allLeads);return;}renderLeads(allLeads.filter(function(l){return(l.email||'').toLowerCase().indexOf(q)>=0||(l.name||'').toLowerCase().indexOf(q)>=0||(l.company||'').toLowerCase().indexOf(q)>=0;}));}

async function loadTips(){try{showLoading();var data=await apiRequest('GET','/admin/tips');allTips=data.tips||[];renderTips(allTips);}catch(e){if(e.message!=='Unauthorized')showNotification('Failed to load tips.','error');}finally{hideLoading();}}
function renderTips(tips){tipsTbody.innerHTML='';if(!tips.length){tipsEmpty.hidden=false;return;}tipsEmpty.hidden=true;tips.forEach(function(t){var tr=document.createElement('tr');tr.innerHTML='<td>'+escapeHtml(t.service||'')+'</td><td>'+escapeHtml(t.tipId||'')+'</td><td>'+escapeHtml(t.category||'')+'</td><td>'+escapeHtml(t.title||'')+'</td><td title="'+escapeAttr(t.description)+'">'+escapeHtml(t.description||'')+'</td><td>'+escapeHtml(t.estimatedSavings||'')+'</td><td><span class="badge badge-'+(t.difficulty||'').toLowerCase()+'">'+escapeHtml(t.difficulty||'')+'</span></td><td class="actions-cell"><button class="btn-icon btn-icon-edit" data-action="edit" data-service="'+escapeAttr(t.service)+'" data-tipid="'+escapeAttr(t.tipId)+'" title="Edit">&#9998;</button><button class="btn-icon btn-icon-delete" data-action="delete" data-service="'+escapeAttr(t.service)+'" data-tipid="'+escapeAttr(t.tipId)+'" title="Delete">&#128465;</button></td>';tipsTbody.appendChild(tr);});}
function filterTips(q){q=(q||'').toLowerCase().trim();if(!q){renderTips(allTips);return;}renderTips(allTips.filter(function(t){return(t.service||'').toLowerCase().indexOf(q)>=0||(t.title||'').toLowerCase().indexOf(q)>=0||(t.category||'').toLowerCase().indexOf(q)>=0;}));}

function showTipForm(tip){tipFormError.textContent='';if(tip){editingTip=tip;tipModalTitle.textContent='Edit Tip';tipSubmitBtn.textContent='Update Tip';TIP_FIELDS.forEach(function(f){document.getElementById('tip-'+f).value=tip[f]||'';});document.getElementById('tip-service').disabled=true;document.getElementById('tip-tipId').disabled=true;}else{editingTip=null;tipModalTitle.textContent='Add Tip';tipSubmitBtn.textContent='Save Tip';TIP_FIELDS.forEach(function(f){document.getElementById('tip-'+f).value='';});document.getElementById('tip-service').disabled=false;document.getElementById('tip-tipId').disabled=false;}tipModal.hidden=false;}
function hideTipForm(){tipModal.hidden=true;editingTip=null;}

async function saveTip(){tipFormError.textContent='';var tipData={};for(var i=0;i<TIP_FIELDS.length;i++){var f=TIP_FIELDS[i],val=document.getElementById('tip-'+f).value.trim();if(!val){tipFormError.textContent='All fields are required.';return;}tipData[f]=val;}
try{showLoading();if(editingTip){await apiRequest('PUT','/admin/tips',tipData);showNotification('Tip updated.','success');}else{await apiRequest('POST','/admin/tips',tipData);showNotification('Tip created.','success');}hideTipForm();await loadTips();}catch(e){if(e.status===409)tipFormError.textContent='A tip with this service and ID already exists.';else if(e.message!=='Unauthorized')tipFormError.textContent=e.message||'Failed to save tip.';}finally{hideLoading();}}

function showDeleteDialog(svc,tid){deletingTip={service:svc,tipId:tid};deleteDialog.hidden=false;}
function hideDeleteDialog(){deleteDialog.hidden=true;deletingTip=null;}
async function deleteTip(){if(!deletingTip)return;var svc=deletingTip.service,tid=deletingTip.tipId;hideDeleteDialog();try{showLoading();await apiRequest('DELETE','/admin/tips',{service:svc,tipId:tid});showNotification('Tip deleted.','success');await loadTips();}catch(e){if(e.status===404){showNotification('Tip not found.','error');await loadTips();}else if(e.message!=='Unauthorized')showNotification(e.message||'Failed to delete tip.','error');}finally{hideLoading();}}

loginForm.addEventListener('submit',function(e){e.preventDefault();var u=loginUsername.value.trim(),p=loginPassword.value;if(!u||!p){loginError.textContent='Please enter username and password.';return;}login(u,p);});
logoutBtn.addEventListener('click',logout);
document.querySelectorAll('.tab-btn').forEach(function(btn){btn.addEventListener('click',function(){switchTab(btn.dataset.tab);});});
leadsSearch.addEventListener('input',debounce(function(){filterLeads(leadsSearch.value);},200));
tipsSearch.addEventListener('input',debounce(function(){filterTips(tipsSearch.value);},200));
addTipBtn.addEventListener('click',function(){showTipForm(null);});
tipForm.addEventListener('submit',function(e){e.preventDefault();saveTip();});
tipCancelBtn.addEventListener('click',hideTipForm);
tipModalClose.addEventListener('click',hideTipForm);
deleteCancelBtn.addEventListener('click',hideDeleteDialog);
deleteConfirmBtn.addEventListener('click',deleteTip);
tipsTbody.addEventListener('click',function(e){var btn=e.target.closest('[data-action]');if(!btn)return;var action=btn.dataset.action,svc=btn.dataset.service,tid=btn.dataset.tipid;if(action==='edit'){var tip=allTips.find(function(t){return t.service===svc&&t.tipId===tid;});if(tip)showTipForm(tip);}else if(action==='delete')showDeleteDialog(svc,tid);});
tipModal.addEventListener('click',function(e){if(e.target===tipModal)hideTipForm();});
deleteDialog.addEventListener('click',function(e){if(e.target===deleteDialog)hideDeleteDialog();});

(function(){if(sessionStorage.getItem('admin_token')){showDashboard();loadLeads();loadTips();}else showLogin();})();
