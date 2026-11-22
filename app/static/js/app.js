'use strict';
/* QueueWise front end: all DOM output from API responses is HTML-escaped. */
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const getStored = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
const setStored = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };
const state = {
  csrf: '', user: null, today: '', documents: [], categories: [],
  view: 'dashboard', adminData: null, notifications: [], publicTracked: [],
  staffTab: 'all', search: '', filter: 'All', lastSuccessId: null, trackedResult: null,
  helpTab: 'student', installPrompt: null, busy: false, renderToken: 0
};
const todayLabel = () => new Intl.DateTimeFormat('en-PH',{month:'long',day:'numeric',year:'numeric'}).format(new Date(`${state.today || new Date().toISOString().slice(0,10)}T00:00:00`));
const datetime = text => { try { return new Intl.DateTimeFormat('en-PH',{month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZone:'Asia/Manila'}).format(new Date(text)); } catch { return '—'; } };
const dayLabel = text => { try { return new Intl.DateTimeFormat('en-PH',{month:'short',day:'numeric',year:'numeric'}).format(new Date(`${text}T00:00:00`)); } catch { return '—'; } };
const statusBadge = text => `<span class="badge status-${escapeHtml(String(text).replaceAll(' ','-'))}">${escapeHtml(text)}</span>`;
const empty = (title, body, action = '') => `<div class="empty-state"><div class="empty-icon">${icon('document')}</div><strong>${title}</strong><p>${body}</p>${action}</div>`;

async function api(path, options = {}) {
  const init = {credentials:'same-origin',method:options.method || 'GET',headers:{Accept:'application/json'}};
  if (options.body !== undefined) { init.body = JSON.stringify(options.body); init.headers['Content-Type'] = 'application/json'; }
  if (init.method !== 'GET') init.headers['X-CSRF-Token'] = state.csrf;
  let response;
  try { response = await fetch(path, init); }
  catch { throw Error('Cannot reach the QueueWise server. Check your connection.'); }
  let data;
  try { data = await response.json(); }
  catch { throw Error('The server returned an unreadable response. Please retry.'); }
  if (!response.ok) throw Error(data.error || 'Something went wrong. Please retry.');
  if (data.csrf_token) state.csrf = data.csrf_token;
  return data;
}
function toast(message, error=false) {
  const node = document.createElement('div');
  node.className = `toast${error ? ' error' : ''}`;
  node.innerHTML = `${icon(error?'info':'check')}<span>${escapeHtml(message)}</span>`;
  $('#toastArea').append(node);
  setTimeout(()=>node.remove(), 4800);
}
function openModal(id) { const modal = document.getElementById(id); if (modal && !modal.open) modal.showModal(); }
function closeModal(id) { const modal = document.getElementById(id); if (modal?.open) modal.close(); }
function setTheme(theme) {
  const actual = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = actual;
  try { localStorage.setItem('queuewise_theme', actual); } catch {}
  $('#themeIcon').innerHTML = `<use href="#i-${actual==='dark'?'sun':'moon'}"></use>`;
  $('#themeButton').title = `Switch to ${actual==='dark'?'light':'dark'} mode`;
  document.querySelector('meta[name="theme-color"]').content = actual === 'dark' ? '#101c16' : '#155c38';
}
function pageHeading(title, subtitle, actions = '') { return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${actions?`<div class="heading-actions">${actions}</div>`:''}</div>`; }
function button(label, action, kind='primary', extra='') { return `<button type="button" class="button ${kind}" data-action="${action}" ${extra}>${label}</button>`; }
const isStaff = () => !!state.user;

function trackedIds() { return getStored('queuewise_tracked_ids',[]).filter(id=>/^REQ-\d{4,}$/.test(id)).slice(0,12); }
function saveTracked(id) { setStored('queuewise_tracked_ids', [id, ...trackedIds().filter(x=>x!==id)].slice(0,12)); }
async function loadPublicTracked() {
  const ids = trackedIds();
  const results = await Promise.all(ids.map(async id => { try { return await api(`/api/track/${encodeURIComponent(id)}`); } catch { return null; } }));
  state.publicTracked = results.filter(Boolean);
}
async function loadAdmin() {
  const [data, feed] = await Promise.all([api('/api/admin/requests'),api('/api/admin/notifications')]);
  state.adminData = data; state.notifications = feed.notifications; state.unread = feed.unread;
}
function updateChrome() {
  const names = {dashboard:'Dashboard',requests:'Document Request',notifications:'Notifications',profile:'Profile'};
  $('#currentSection').textContent = names[state.view] || 'Dashboard';
  $$('.nav-item').forEach(el=>{el.classList.toggle('active',el.dataset.nav===state.view); el.setAttribute('aria-current',el.dataset.nav===state.view?'page':'false');});
  $('#topName').textContent = state.user?.display_name || 'Guest portal';
  $('#topRole').textContent = state.user?'Registrar Administrator':'Student / Alumni';
  $('#topAvatar').textContent = state.user?.display_name?.[0] || 'G';
  const count = state.user ? (state.unread || 0) : 0;
  $('#navBadge').textContent = String(count>99?'99+':count);
  $('#navBadge').classList.toggle('hidden',count===0);
  $('#appShell').classList.remove('menu-open');
}
function navigate(view) {
  const accepted = ['dashboard','requests','notifications','profile'];
  const v = accepted.includes(view)?view:'dashboard';
  if (location.hash !== `#${v}`) location.hash=v;
  else render();
}
async function render() {
  const requested = location.hash.replace(/^#/,'');
  const view = ['dashboard','requests','notifications','profile'].includes(requested)?requested:'dashboard';
  state.view = view;
  const ticket = ++state.renderToken;
  updateChrome();
  const target = $('#page');
  target.innerHTML = '<div class="initial-loader"><span class="spinner"></span><p>Loading your workspace…</p></div>';
  try {
    if (isStaff() && (!state.adminData || ['dashboard','requests'].includes(view))) await loadAdmin();
    if (!isStaff() && ['dashboard','requests','notifications'].includes(view)) await loadPublicTracked();
    if (isStaff() && view==='notifications') {
      const feed = await api('/api/admin/notifications');
      state.notifications = feed.notifications; state.unread = feed.unread;
    }
    if (ticket!==state.renderToken) return;
    const html = view==='dashboard' ? (isStaff()?adminDashboard():publicDashboard())
      : view==='requests' ? (isStaff()?adminRequests():publicRequests())
      : view==='notifications' ? notificationsPage() : profilePage();
    target.innerHTML = html;
    updateChrome();
    if (view==='requests' && isStaff()) renderStaffRows();
    if (!isStaff() && state.trackedResult && $('#inlineTrackResult')) $('#inlineTrackResult').innerHTML=renderTrackCard(state.trackedResult);
  } catch (error) {
    if (ticket!==state.renderToken) return;
    target.innerHTML = empty('Unable to load this page',escapeHtml(error.message),button('Try again','refresh','primary'));
    toast(error.message,true);
  }
}
function hero({staff=false}={}) {
  const label = staff?'REGISTRAR CONTROL CENTER':'DOCUMENT REQUEST PORTAL';
  const title = staff?'Your registrar workspace, simplified.':'A smarter way to request documents.';
  const description = staff?'Monitor the queue, review the latest requests, and process academic documents with confidence.':'Submit your request online, keep your reference ID, and follow its progress—all in one convenient place.';
  return `<section class="hero"><div class="hero-copy"><div class="hero-label">${label}</div><h1>${title}</h1><p>${description}</p><div class="hero-actions">${staff?button(`${icon('layers')} Open request queue`,'go-requests','white'):button(`${icon('plus')} New document request`,'go-requests','white')}${staff?button('Refresh dashboard','refresh','transparent'):button('Track my request','focus-track','transparent')}</div></div><div class="hero-art" aria-hidden="true"><div class="art-page"><div class="art-line" style="margin-top:47px"></div><div class="art-line short"></div><div class="art-line"></div><div class="art-check">${icon('check')}</div></div><div class="art-small">${icon('document')}</div></div></section>`;
}
function stat(label,number,caption,symbol) { return `<article class="stat-card"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon(symbol)}</span></div><strong>${number}</strong><p class="stat-caption">${caption}</p></article>`; }
function adminDashboard() {
  const data=state.adminData, stats=data.stats;
  return hero({staff:true})+`<section class="stat-grid">${stat('Total Requests',stats.total,'All registered transactions','document')}${stat('Pending Queue',stats.pending,'Awaiting registrar processing','clock')}${stat('In Progress',stats.processing+stats.ready,'Processing / ready for release','layers')}${stat('Completed',stats.processed,'Successfully processed requests','check')}</section>
    <div class="section-grid"><section class="panel"><div class="panel-header"><div><h2>Priority queue overview</h2><p>Requests ranked by weighted priority score</p></div><button class="text-button" data-action="go-requests">View all ${icon('arrow')}</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Rank</th><th>Request ID</th><th>Requester</th><th>Score</th><th>Deadline</th></tr></thead><tbody>${data.priority.slice(0,5).map((r,i)=>`<tr><td><span class="rank-number">${i+1}</span></td><td class="main-cell">${escapeHtml(r.public_id)}</td><td>${escapeHtml(r.requester_name)}</td><td class="score-cell">${Number(r.priority_score).toFixed(2)}</td><td>${dayLabel(r.deadline)}</td></tr>`).join('')||`<tr><td colspan="5">${empty('No pending requests','Submit a document request or load demonstration records to see the queue.')}</td></tr>`}</tbody></table></div></section>
      <section class="panel pad"><div class="panel-header" style="padding:0 0 20px"><div><h2>Up next in queue</h2><p>Automatically selected highest priority</p></div>${icon('layers')}</div><div class="quick-next"><small>NEXT REQUEST TO PROCESS</small><strong>${escapeHtml(data.next_id||'Queue is clear')}</strong><div class="next-details"><span>${stats.pending} pending</span><span>Auto-ranked by score</span></div>${button(`${icon('check')} Process next request`,'process-next','primary',stats.pending?'':'disabled')}</div><h3 class="subheading">Recent activity</h3>${state.notifications.slice(0,2).map(n=>`<div class="mini-activity"><span class="activity-icon">${icon('bell')}</span><div><strong>${escapeHtml(n.title)}</strong><p>${escapeHtml(n.message)}</p><small>${datetime(n.created_at)}</small></div></div>`).join('')||`<p class="panel-subtitle">No activity yet. New requests and status changes will appear here.</p>`}</section></div>
    <div class="panel pad"><div class="panel-header" style="padding:0 0 18px"><div><h2>How your queue is organized</h2><p>The three data structures implemented in your project</p></div><span class="badge status-info">Live demonstration</span></div><div class="adt-row"><div class="adt-card"><span>${icon('list')}</span><div><strong>FIFO Arrival Queue</strong><p>${stats.total} recorded IDs, retained in arrival order</p></div></div><div class="adt-card"><span>${icon('layers')}</span><div><strong>Binary Min-Heap</strong><p>${stats.heap_entries} pending entries • ${stats.heap_valid?'Valid heap':'Needs attention'}</p></div></div><div class="adt-card"><span>${icon('search')}</span><div><strong>Chained Hash Table</strong><p>${stats.hash_entries} indexed records • ${stats.hash_buckets} buckets</p></div></div></div></div>`;
}
function publicDashboard() {
  const current=state.publicTracked;
  const active=current.filter(x=>x.request.status!=='Processed').length;
  const completed=current.filter(x=>x.request.status==='Processed').length;
  return hero()+`<section class="stat-grid">${stat('My Tracked Requests',current.length,'Stored on this browser','document')}${stat('Active Requests',active,'Pending or in progress','clock')}${stat('Completed Requests',completed,'Marked as processed','check')}${stat('Online Portal','PWA','Available while server is running','shield')}</section>
    <div class="section-grid"><section class="panel pad"><div class="panel-header" style="padding:0 0 13px"><div><h2>Track a document request</h2><p>Enter your assigned reference number for an instant status check.</p></div>${icon('search')}</div><form class="tracker-form" data-form="track"><input class="filter-input" aria-label="Request ID" id="homeTrackInput" name="request_id" placeholder="Example: REQ-0001" required pattern="REQ-[0-9]{4,}" maxlength="24"><button class="button primary" type="submit">${icon('search')} Check status</button></form><div id="inlineTrackResult" class="tracker-result"></div><div class="divider"></div><div class="panel-header" style="padding:0 0 17px"><div><h2>Recently tracked</h2><p>Your requests remembered on this device</p></div></div>${recentTracked()}</section>
    <section class="panel pad"><div class="panel-header" style="padding:0 0 5px"><div><h2>Getting started is easy</h2><p>Three simple steps from request to processing</p></div></div><div class="step-list"><div class="step-item"><div class="step-no">01</div><div><strong>Fill in the request form</strong><p>Select your document type, category, and deadline, then submit your complete name.</p></div></div><div class="step-item"><div class="step-no">02</div><div><strong>Keep your reference ID</strong><p>QueueWise automatically generates a unique ID for every successful submission.</p></div></div><div class="step-item"><div class="step-no">03</div><div><strong>Check your request status</strong><p>Use your reference ID anytime to view pending, processing, and completed stages.</p></div></div></div><div class="tip-box">${icon('info')}<span>QueueWise is an academic prototype. It does not submit official document requests to the university.</span></div></section></div>`;
}
function recentTracked() {
  return state.publicTracked.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Request ID</th><th>Status</th><th>Submitted</th><th></th></tr></thead><tbody>${state.publicTracked.slice(0,5).map(x=>`<tr><td class="main-cell">${escapeHtml(x.request.id)}</td><td>${statusBadge(x.request.status)}</td><td>${dayLabel(x.request.submitted_at)}</td><td><button class="row-action" data-action="quick-track" data-id="${escapeHtml(x.request.id)}">View</button></td></tr>`).join('')}</tbody></table></div>`:empty('No tracked requests yet','After submitting a request, your reference number will appear here.',button('Submit a request','go-requests','light'));
}
function publicRequests() {
  return pageHeading('Document request','Create a new simulated request or check the status of an existing one.')+`<div class="form-layout"><section class="panel form-section"><p class="eyebrow">NEW REQUEST</p><h2>Request details</h2><p class="section-subtext">Please provide complete, accurate details. Fields marked * are required.</p><form id="requestForm" class="form-grid"><label class="form-label full-span" for="requesterName"><span>Full name <span class="required">*</span></span><input id="requesterName" name="requester_name" minlength="2" maxlength="60" placeholder="e.g. Juan Dela Cruz" autocomplete="name" required><small>Enter both first and last name. Numbers and incomplete names are not accepted.</small></label><label class="form-label" for="documentType"><span>Document type <span class="required">*</span></span><select id="documentType" name="document_type" required><option value="">Choose a document</option>${state.documents.map(x=>`<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join('')}</select></label><label class="form-label" for="requesterCategory"><span>Requester category <span class="required">*</span></span><select id="requesterCategory" name="category" required><option value="">Choose a category</option>${state.categories.map(x=>`<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join('')}</select></label><label class="form-label full-span" for="requestDeadline"><span>Required-by date <span class="required">*</span></span><input id="requestDeadline" name="deadline" type="date" min="${escapeHtml(state.today)}" required><small>When do you need your document? Past dates are not accepted.</small></label><div class="submit-wrap full-span"><small>By submitting, you acknowledge this is a simulated school-project system, not an official CvSU transaction.</small><button class="button primary" id="submitRequestButton" type="submit">Submit request ${icon('arrow')}</button></div></form></section>
    <div><section class="panel pad"><p class="eyebrow">STEP-BY-STEP</p><h2 style="font-size:17px;margin-bottom:16px">What happens next?</h2><div class="step-list"><div class="step-item"><span class="step-no">1</span><div><strong>Request submitted</strong><p>You'll get a unique reference ID automatically.</p></div></div><div class="step-item"><span class="step-no">2</span><div><strong>Added to the queue</strong><p>The system records arrival order and calculates a demonstration priority score.</p></div></div><div class="step-item"><span class="step-no">3</span><div><strong>Registrar processes it</strong><p>Only signed-in staff can process requests or change statuses.</p></div></div></div></section><section class="panel pad" style="margin-top:18px"><h2 style="font-size:16px;margin-bottom:6px">Already have a request?</h2><p class="panel-subtitle">Look up your transaction with the ID generated at submission.</p><form class="tracker-form" data-form="track"><input class="filter-input" name="request_id" placeholder="REQ-0001" required pattern="REQ-[0-9]{4,}" maxlength="24" aria-label="Request ID"><button type="submit" class="button light">Track</button></form><div id="inlineTrackResult" class="tracker-result"></div></section></div></div>`;
}
function renderTrackCard(data) {
  const r=data.request;
  return `<div class="track-detail"><div class="id-line"><strong>${escapeHtml(r.id)}</strong>${statusBadge(r.status)}</div><p><strong>Submitted:</strong> ${dayLabel(r.submitted_at)}</p><p><strong>Last updated:</strong> ${datetime(r.updated_at)}</p>${r.processed_at?`<p><strong>Processed:</strong> ${datetime(r.processed_at)}</p>`:''}<div class="timeline">${data.events.map(event=>`<div class="timeline-item"><span class="timeline-bullet"></span><div><strong>${escapeHtml(event.status)}</strong><p>${escapeHtml(event.message)}</p><small>${datetime(event.created_at)}</small></div></div>`).join('')}</div></div>`;
}
function adminRequests() {
  const stats=state.adminData.stats;
  return pageHeading('Document requests','Manage the registrar queue, view arrival history, and process pending requests.',`${button(`${icon('refresh')} Refresh`,'refresh','outline')}${button(`${icon('plus')} Load sample data`,'seed','light')}${button(`${icon('check')} Process next`,'process-next','primary',stats.pending?'':'disabled')}`)+`<div class="top-tools"><div class="tab-bar" role="tablist"><button type="button" data-staff-tab="all" class="${state.staffTab==='all'?'active':''}">All requests</button><button type="button" data-staff-tab="priority" class="${state.staffTab==='priority'?'active':''}">Priority ranking</button><button type="button" data-staff-tab="arrival" class="${state.staffTab==='arrival'?'active':''}">FIFO arrivals</button></div></div><div class="filters"><input class="filter-input" id="staffSearch" placeholder="Search ID, name, document…" value="${escapeHtml(state.search)}" aria-label="Filter requests"><select class="filter-select" id="staffFilter" aria-label="Filter status">${['All','Pending','Processing','Ready for Release','Processed'].map(s=>`<option value="${s}" ${state.filter===s?'selected':''}>${s==='All'?'All statuses':s}</option>`).join('')}</select></div><section class="panel"><div class="panel-header"><div><h2 id="tableHeading">${state.staffTab==='priority'?'Priority ranking':state.staffTab==='arrival'?'FIFO arrival history':'All document requests'}</h2><p id="tableDescription">${state.staffTab==='priority'?'Highest score first, with deadline and arrival tie-breakers.':state.staffTab==='arrival'?'Original arrival order, including completed requests.':'Review the details and change the status of eligible requests.'}</p></div><span class="badge status-info" id="recordCount">${stats.total} records</span></div><div id="staffTable"></div></section><div class="queue-summary"><span class="online-pip"></span><span>Scoring refreshed on <strong>${todayLabel()}</strong></span><span>•</span><span>Min-heap verified: <strong>${stats.heap_valid?'Yes':'No'}</strong></span><span>•</span><span>Hash buckets: <strong>${stats.hash_buckets}</strong></span></div>`;
}
function nextStatusOptions(r) {
  const options={Pending:['Processing','Processed'],Processing:['Ready for Release','Processed'],'Ready for Release':['Processed'],Processed:[]};
  const choices=options[r.status]||[];
  if (!choices.length) return '<span style="font-size:11px;color:var(--muted)">Finalized</span>';
  return `<div class="row-actions"><select class="filter-select" aria-label="Next status for ${escapeHtml(r.public_id)}" data-status-select="${escapeHtml(r.public_id)}" style="min-width:120px;width:138px;min-height:32px;padding:5px;font-size:10.5px">${choices.map(s=>`<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('')}</select><button class="row-action" data-action="save-status" data-id="${escapeHtml(r.public_id)}">Apply</button></div>`;
}
function renderStaffRows() {
  const container=$('#staffTable'); if(!container) return;
  const data=state.adminData;
  let rows=state.staffTab==='priority'?data.priority:state.staffTab==='arrival'
    ? data.arrivals.map(id=>data.requests.find(x=>x.public_id===id)).filter(Boolean) : data.requests;
  const term=state.search.toLowerCase();
  rows=rows.filter(r=>(state.filter==='All'||r.status===state.filter) &&
      (!term||[r.public_id,r.requester_name,r.document_type,r.category].some(x=>String(x).toLowerCase().includes(term))));
  $('#recordCount').textContent=`${rows.length} record${rows.length===1?'':'s'}`;
  const rank=state.staffTab==='priority', arrival=state.staffTab==='arrival';
  const header=rank?'Rank':arrival?'Arrival':'Request ID';
  container.innerHTML = rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>${header}</th>${state.staffTab!=='all'?'<th>Request ID</th>':''}<th>Requester / Document</th><th>Category</th><th>Deadline</th><th>Score</th><th>Status</th><th>Manage</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td class="main-cell">${state.staffTab==='all'?escapeHtml(r.public_id):`<span class="rank-number">${arrival?r.arrival_number:i+1}</span>`}</td>${state.staffTab!=='all'?`<td class="main-cell">${escapeHtml(r.public_id)}</td>`:''}<td class="main-cell">${escapeHtml(r.requester_name)}<span class="sub-cell">${escapeHtml(r.document_type)}${r.demo?' · Demo':''}</span></td><td>${escapeHtml(r.category)}</td><td>${dayLabel(r.deadline)}</td><td class="score-cell">${r.status==='Pending'?Number(r.priority_score).toFixed(2):'—'}</td><td>${statusBadge(r.status)}</td><td>${nextStatusOptions(r)}</td></tr>`).join('')}</tbody></table></div>`:empty('No matching requests','Try a different search or filter. If the database is empty, load sample requests.',button('Load sample requests','seed','light'));
}
function notificationsPage() {
  if (isStaff()) {
    return pageHeading('Notifications','All in-app request activity and registrar updates.',button(`${icon('check')} Mark all as read`,'mark-read','outline',(state.unread||0)?'':'disabled'))+`<section class="panel pad"><div class="panel-header" style="padding:0 0 5px"><div><h2>Activity inbox</h2><p>${state.unread||0} unread updates • ${state.notifications.length} recent entries</p></div></div>${state.notifications.length?`<div class="activity-feed">${state.notifications.map(n=>`<div class="feed-entry ${n.is_read?'':'unread'}"><div class="feed-icon">${icon('bell')}</div><div class="feed-body"><strong>${escapeHtml(n.title)}</strong><p>${escapeHtml(n.message)}</p><small>${datetime(n.created_at)}</small></div>${n.is_read?'':'<span class="unread-dot" aria-label="Unread"></span>'}</div>`).join('')}</div>`:empty('Your inbox is clear','New submissions and processing updates will appear here.')}</section>`;
  }
  const updates=state.publicTracked.flatMap(track=>track.events.map(event=>({id:track.request.id,event}))).sort((a,b)=>b.event.created_at.localeCompare(a.event.created_at));
  return pageHeading('Notifications','Status activity for reference numbers saved on this browser.')+`<section class="panel pad"><div class="panel-header" style="padding:0 0 8px"><div><h2>My request updates</h2><p>These are in-app status records—not email, SMS, or push notifications.</p></div></div>${updates.length?`<div class="activity-feed">${updates.map(item=>`<div class="feed-entry"><div class="feed-icon">${icon('document')}</div><div class="feed-body"><strong>${escapeHtml(item.id)} · ${escapeHtml(item.event.status)}</strong><p>${escapeHtml(item.event.message)}</p><small>${datetime(item.event.created_at)}</small></div></div>`).join('')}</div>`:empty('No request activity yet','Once you submit or track a request on this device, its updates will appear here.',button('Create a request','go-requests','light'))}</section>`;
}
function profilePage() {
  if (isStaff()) return pageHeading('My profile','Manage your registrar account and access settings.')+`<div class="profile-grid"><section class="panel profile-card"><div class="profile-banner"><div class="profile-avatar">${escapeHtml(state.user.display_name[0])}</div><div><h2>${escapeHtml(state.user.display_name)}</h2><p>Registrar administrator</p></div></div><div class="detail-row"><span>Username</span><strong>${escapeHtml(state.user.username)}</strong></div><div class="detail-row"><span>Account role</span><strong>Registrar Staff</strong></div><div class="detail-row"><span>Access</span><strong>Priority queue · Request processing</strong></div><div class="detail-row"><span>Environment</span><strong>Academic demonstration</strong></div>${button(`${icon('log')} Sign out`,'logout','outline')}</section><section class="panel profile-card"><h2 style="font-size:17px;margin-bottom:8px">Security settings</h2><p class="panel-subtitle">Change the demonstration password before using the prototype on a shared computer or network.</p><form id="passwordForm" class="form-stack" style="margin-top:23px"><label class="form-label">Current password<input name="current_password" autocomplete="current-password" type="password" required></label><label class="form-label">New password<input name="new_password" autocomplete="new-password" type="password" minlength="10" required><small>At least 10 characters with uppercase, lowercase, a number, and a symbol.</small></label><button type="submit" class="button primary">Update password ${icon('arrow')}</button></form><div class="tip-box">${icon('shield')}<span>Only authorized registrar staff can view requester names, priority rankings, and processing controls. Guests can track a minimal status using a request ID.</span></div></section></div>`;
  return pageHeading('Profile & access','Student / alumni portal and registrar staff access.')+`<div class="profile-grid"><section class="panel profile-card"><div class="profile-banner"><div class="profile-avatar">G</div><div><h2>Guest access</h2><p>Student and alumni portal</p></div></div><p class="panel-subtitle">For this prototype, you do not need an account to submit a request or check its status. Reference IDs are saved only in this browser, not in a student profile.</p><div class="detail-row"><span>Access type</span><strong>Public (limited)</strong></div><div class="detail-row"><span>My tracked requests</span><strong>${state.publicTracked.length}</strong></div><div class="detail-row"><span>Current environment</span><strong>Simulation only</strong></div>${button(`${icon('plus')} Create a request`,'go-requests','primary')}</section><section class="panel profile-card"><p class="eyebrow">STAFF AREA</p><h2 style="font-size:19px;margin-bottom:9px">Registrar access</h2><p class="panel-subtitle">Authorized staff can manage the priority queue, process the next request, and change request statuses after signing in.</p><div class="tip-box">${icon('shield')}<span>Protected dashboard, secure password hashing, authenticated sessions, and server-side permission checks.</span></div>${button(`${icon('log')} Registrar staff sign in`,'login','primary')}<div class="divider"></div><h3 class="subheading">Need help?</h3><p class="panel-subtitle">Use the question-mark icon in the upper-right corner to open “How the system works”.</p>${button('Open system guide','help','outline')}</section></div>`;
}
const helpGuides={
  student:[['Open Document Request','Choose “Document Request” from the left sidebar.'],['Complete the form','Enter your first and last name, document type, requester category, and required-by date.'],['Submit and save your ID','The system validates your information and generates a reference such as REQ-0001 automatically.'],['Track your status','Open Dashboard or Document Request and enter the reference ID to see the latest status and timeline.']],
  staff:[['Sign in as registrar staff','Go to Profile and choose “Registrar staff sign in” using a demonstration account.'],['Open the queue dashboard','Review live counts, highest-priority pending requests, and registrar activity.'],['Manage document requests','Switch among All requests, Priority ranking, and FIFO arrivals. Update an eligible status or choose Process next.'],['Understand priority selection','The demonstration score is PS = 0.50U + 0.30W + 0.20C. U is deadline urgency, W waiting time, and C requester category (each 0–100). Scores are recalculated before ranking or processing.'],['Review updates','Use Notifications for in-app activity. Profile includes change password and sign out.']]
};
function renderHelp() {
  $$('#helpModal [data-help-tab]').forEach(b=>b.classList.toggle('selected',b.dataset.helpTab===state.helpTab));
  $('#helpContent').innerHTML=helpGuides[state.helpTab].map(([title,description],i)=>`<div class="help-step"><span class="help-step-number">${String(i+1).padStart(2,'0')}</span><div><strong>${title}</strong><p>${description}</p></div></div>`).join('');
}
async function track(id) {
  const value=id.trim().toUpperCase();
  if (!/^REQ-\d{4,}$/.test(value)) { toast('Enter a valid request ID, such as REQ-0001.',true); return; }
  const data=await api(`/api/track/${encodeURIComponent(value)}`);
  saveTracked(value);
  state.trackedResult=data;
  const node=$('#inlineTrackResult');
  if(node) node.innerHTML=renderTrackCard(data);
  toast(`${value} is currently ${data.request.status}.`);
}
async function submitRequest(form) {
  if(state.busy)return;
  const data=Object.fromEntries(new FormData(form));
  state.busy=true;
  const submit=$('#submitRequestButton'); if(submit)submit.disabled=true;
  try {
    const response=await api('/api/requests',{method:'POST',body:data});
    const id=response.request.id;
    state.lastSuccessId=id;
    saveTracked(id);
    $('#successId').textContent=id;
    form.reset();
    openModal('successModal');
  } catch(error) { toast(error.message,true); }
  finally { state.busy=false; if(submit)submit.disabled=false; }
}
async function refreshCurrent() {
  state.adminData=null;
  await render();
  toast('Workspace is up to date.');
}
async function executeAction(action, element) {
  if (action==='go-requests') return navigate('requests');
  if (action==='go-dashboard') return navigate('dashboard');
  if (action==='profile') return navigate('profile');
  if (action==='login') return openModal('loginModal');
  if (action==='help') {state.helpTab='student';renderHelp();return openModal('helpModal');}
  if (action==='refresh') return refreshCurrent();
  if (action==='focus-track') { navigate('dashboard'); setTimeout(()=>$('#homeTrackInput')?.focus(),150);return; }
  if (action==='quick-track') { const id=element.dataset.id;await track(id);navigate('requests');return; }
  if (action==='copy-success') { try { await navigator.clipboard.writeText(state.lastSuccessId||'');toast('Reference ID copied.'); } catch {toast('Please copy the reference ID manually.',true);} return; }
  if (action==='track-success') {closeModal('successModal');navigate('dashboard');setTimeout(()=>{const field=$('#homeTrackInput');if(field){field.value=state.lastSuccessId;field.closest('form').requestSubmit();}},200);return;}
  if (action==='logout') {await api('/api/auth/logout',{method:'POST'});state.user=null;state.adminData=null;state.notifications=[];state.unread=0;toast('You have signed out.');return navigate('dashboard');}
  if (action==='process-next') {
    if(!confirm('Process the highest-priority pending request now? This marks it Processed.'))return;
    const response=await api('/api/admin/process-next',{method:'POST'});
    toast(response.message);return refreshCurrent();
  }
  if (action==='seed') {
    if(!confirm('Add 12 clearly marked simulated sample requests to the SQLite database?'))return;
    const response=await api('/api/admin/seed',{method:'POST',body:{count:12}});
    toast(response.message);return refreshCurrent();
  }
  if (action==='save-status') {
    const id=element.dataset.id;
    const select=$$('[data-status-select]').find(x=>x.dataset.statusSelect===id);
    if(!select)return;
    const response=await api(`/api/admin/requests/${encodeURIComponent(id)}/status`,{method:'PATCH',body:{status:select.value}});
    toast(response.message);return refreshCurrent();
  }
  if(action==='mark-read') {const response=await api('/api/admin/notifications/read-all',{method:'POST'});toast(response.message);return render();}
}

document.addEventListener('click',async event=>{
  const nav=event.target.closest('[data-nav]');
  if(nav){navigate(nav.dataset.nav);return;}
  const close=event.target.closest('[data-close]');
  if(close){closeModal(close.dataset.close);return;}
  const tab=event.target.closest('[data-help-tab]');
  if(tab){state.helpTab=tab.dataset.helpTab;renderHelp();return;}
  const staffTab=event.target.closest('[data-staff-tab]');
  if(staffTab){state.staffTab=staffTab.dataset.staffTab;$$('[data-staff-tab]').forEach(b=>b.classList.toggle('active',b===staffTab));$('#tableHeading').textContent={all:'All document requests',priority:'Priority ranking',arrival:'FIFO arrival history'}[state.staffTab];$('#tableDescription').textContent={all:'Review the details and change the status of eligible requests.',priority:'Highest score first, with deadline and arrival tie-breakers.',arrival:'Original arrival order, including completed requests.'}[state.staffTab];renderStaffRows();return;}
  const action=event.target.closest('[data-action]');
  if(action){try{await executeAction(action.dataset.action,action);}catch(error){toast(error.message,true);}return;}
});
document.addEventListener('submit',async event=>{
  const form=event.target;
  if(form.id==='requestForm'){event.preventDefault();await submitRequest(form);return;}
  if(form.dataset.form==='track'){event.preventDefault();try{await track(new FormData(form).get('request_id')||'');}catch(error){toast(error.message,true);}return;}
  if(form.id==='loginForm'){
    event.preventDefault();const button=$('#loginSubmit');button.disabled=true;
    try{
      const response=await api('/api/auth/login',{method:'POST',body:Object.fromEntries(new FormData(form))});
      state.user=response.user;state.adminData=null;closeModal('loginModal');form.reset();toast('Welcome to the registrar workspace.');navigate('dashboard');
    }catch(error){toast(error.message,true);}finally{button.disabled=false;}return;
  }
  if(form.id==='passwordForm'){
    event.preventDefault();const button=$('button[type="submit"]',form);button.disabled=true;
    try{
      const response=await api('/api/admin/change-password',{method:'POST',body:Object.fromEntries(new FormData(form))});
      state.user=null;state.adminData=null;toast(response.message);navigate('profile');openModal('loginModal');
    }catch(error){toast(error.message,true);}finally{button.disabled=false;}
  }
});
document.addEventListener('input', event=>{
  if(event.target.id==='staffSearch'){state.search=event.target.value;renderStaffRows();}
});
document.addEventListener('change',event=>{
  if(event.target.id==='staffFilter'){state.filter=event.target.value;renderStaffRows();}
});
$('#helpButton').addEventListener('click',()=>{state.helpTab='student';renderHelp();openModal('helpModal');});
$('#themeButton').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
$('#menuToggle').addEventListener('click',()=>$('#appShell').classList.toggle('menu-open'));
$('#mobileOverlay').addEventListener('click',()=>$('#appShell').classList.remove('menu-open'));
window.addEventListener('hashchange',render);
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();state.installPrompt=event;});
async function start() {
  let storedTheme='light'; try { storedTheme=localStorage.getItem('queuewise_theme')||'light'; } catch {}
  setTheme(storedTheme);
  $('#year').textContent=new Date().getFullYear();
  renderHelp();
  try{
    const boot=await api('/api/bootstrap');
    state.user=boot.user;state.csrf=boot.csrf_token;state.today=boot.today;
    state.documents=boot.documents;state.categories=boot.categories;
    await render();
  }catch(error){$('#page').innerHTML=empty('Unable to connect',escapeHtml(error.message),button('Retry','refresh','primary'));toast(error.message,true);}
  if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});}
}
start();
