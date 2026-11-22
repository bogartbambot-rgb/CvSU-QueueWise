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
  view: 'dashboard', adminData: null, notifications: [], publicTracked: [], myRequests: [], authTab: 'Student', registerRole: 'Student', verificationEmail: '',
  staffTab: 'all', search: '', filter: 'All', requesterFilter: 'All', claimSearch: '', reviewId: null, cancelId: null, lastSuccessId: null, trackedResult: null,
  calendarAnchor: null, selectedCalendarDay: null, pickerOpen: false, requestMode: 'mine', requestDate: '', requestDraft: null,
  helpTab: 'student', installPrompt: null, isInstalled: false, busy: false, renderToken: 0
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
function updateInstallUI() {
  const installed = state.isInstalled || window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true;
  for (const id of ['installButton', 'sidebarInstallButton']) {
    const item = document.getElementById(id);
    if (item) item.classList.toggle('hidden', !!installed);
  }
}
async function installApp() {
  if (state.isInstalled || window.matchMedia?.('(display-mode: standalone)').matches) {
    toast('QueueWise is already running as an installed app.');
    return;
  }
  if (!state.installPrompt) { openModal('installModal'); return; }
  const prompt = state.installPrompt;
  state.installPrompt = null;
  try {
    await prompt.prompt();
    const result = await prompt.userChoice;
    if (result.outcome === 'accepted') toast('Installation accepted. Follow your browser to finish setup.');
    else toast('You can install QueueWise later from the browser menu.');
  } catch { openModal('installModal'); }
}
function pageHeading(title, subtitle, actions = '') { return `<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div>${actions?`<div class="heading-actions">${actions}</div>`:''}</div>`; }
function button(label, action, kind='primary', extra='') { return `<button type="button" class="button ${kind}" data-action="${action}" ${extra}>${label}</button>`; }
const isStaff = () => state.user?.role === 'Registrar';
const isRequester = () => ['Student','Alumni'].includes(state.user?.role);
const isAlumni = () => state.user?.role === 'Alumni';
const detailViews = ['tracked','active','completed','portal','ready'];
const isDetailView = view => detailViews.includes(view);
const effectiveStatus = r => r?.cancelled_at ? 'Cancelled' : r?.declined_at ? 'Declined' : r?.claimed_at ? 'Claimed' : (r?.pickup_at && r?.approved_at && new Date(r.pickup_at)>new Date() ? 'Pickup Scheduled' : (r?.status==='Processed' && !r?.approved_at || r?.status==='Ready for Release' && !r?.approved_at ? 'Awaiting Approval' : r.status));
const requesterLabel = r => r.requester_type || 'Not specified';
const documentList = r => Array.isArray(r.documents)&&r.documents.length ? r.documents : [r.document_type].filter(Boolean);
const documentsMarkup = r => documentList(r).map((doc,i)=>`<span class="doc-chip">${escapeHtml(doc)}</span>`).join('');
const canCancel = r => !r.cancelled_at && !r.declined_at && !r.claimed_at && !r.approved_at && !r.pickup_at;

function trackedIds() { return getStored('queuewise_tracked_ids',[]).filter(id=>/^REQ-\d{4,}$/.test(id)).slice(0,12); }
function saveTracked(id) { setStored('queuewise_tracked_ids', [id, ...trackedIds().filter(x=>x!==id)].slice(0,12)); }
async function loadPublicTracked() {
  const ids = trackedIds();
  const results = await Promise.all(ids.map(async id => { try { return await api(`/api/track/${encodeURIComponent(id)}`); } catch { return null; } }));
  state.publicTracked = results.filter(Boolean);
}
async function loadRequester() {
  const [own, feed] = await Promise.all([api('/api/my/requests'), api('/api/my/notifications')]);
  state.myRequests=own.requests; state.notifications=feed.notifications; state.unread=feed.notifications.length;
}
async function loadAdmin() {
  const [data, feed] = await Promise.all([api('/api/admin/requests'),api('/api/admin/notifications')]);
  state.adminData = data; state.notifications = feed.notifications; state.unread = feed.unread;
}
function updateChrome() {
  const names = {tracked:'My Tracked Requests',active:'Active Requests',completed:'Completed Requests',portal:'Online Portal',ready:'Ready to Collect',dashboard:'Dashboard',requests:'Document Request',claimed:'Claimed / Released',notifications:'Notifications',profile:'Profile',login:'Sign in',register:'Create account','verify-email':'Verify email'};
  $('#currentSection').textContent = names[state.view] || 'Dashboard';
  $$('.nav-item').forEach(el=>{el.classList.toggle('active',el.dataset.nav===state.view); el.setAttribute('aria-current',el.dataset.nav===state.view?'page':'false');});
  $('#claimedNavItem').classList.toggle('hidden', !isStaff());
  if (isStaff() && state.adminData) {
    const claimCount = state.adminData.stats.claimed || 0;
    $('#claimedBadge').textContent = String(claimCount > 99 ? '99+' : claimCount);
    $('#claimedBadge').classList.toggle('hidden', claimCount === 0);
  }
  $('#topName').textContent = state.user?.display_name || 'Guest portal';
  $('#topRole').textContent = isStaff()?'Registrar administrator':isRequester()?`${state.user.role} Portal · Verified`:'Student / Alumni';
  $('#appShell').dataset.portal = isStaff()?'registrar':isRequester()?state.user.role.toLowerCase():'guest';
  $('#topAvatar').textContent = state.user?.display_name?.[0] || 'G';
  const authAction = state.user ? 'logout' : 'login';
  $('#sidebarAuthButton').dataset.action = authAction;
  $('#sidebarAuthText').textContent = state.user ? 'Log out' : 'Sign in';
  $('#headerAuthButton').dataset.action = authAction;
  $('#headerAuthText').textContent = state.user ? 'Log out' : 'Sign in';
  $('#headerAuthButton').classList.toggle('signed-in',!!state.user);
  $('#appShell').classList.toggle('auth-screen', ['login','register','verify-email'].includes(state.view));
  updateInstallUI();
  const count = state.user ? (state.unread || 0) : 0;
  $('#navBadge').textContent = String(count>99?'99+':count);
  $('#navBadge').classList.toggle('hidden',count===0);
  $('#appShell').classList.remove('menu-open');
}
function navigate(view) {
  const accepted = ['dashboard','requests','claimed','notifications','profile','login','register','verify-email',...detailViews];
  const v = accepted.includes(view)?view:'dashboard';
  if (location.hash !== `#${v}`) location.hash=v;
  else render();
}
async function render() {
  const requested = location.hash.replace(/^#/,'').split('?')[0];
  const view = ['dashboard','requests','claimed','notifications','profile','login','register','verify-email',...detailViews].includes(requested)?requested:'dashboard';
  if (['login','register','verify-email'].includes(view) && state.user) {navigate('dashboard'); return;}
  if (view === 'claimed' && !isStaff()) {navigate('login'); return;}
  if (isStaff() && isDetailView(view)) {navigate('dashboard'); return;}
  if (view === 'ready' && !isRequester()) {navigate('dashboard'); return;}
  state.view = view;
  const ticket = ++state.renderToken;
  updateChrome();
  const target = $('#page');
  target.innerHTML = '<div class="initial-loader"><span class="spinner"></span><p>Loading your workspace…</p></div>';
  try {
    if (isStaff() && (!state.adminData || ['dashboard','requests','claimed'].includes(view))) await loadAdmin();
    if (isRequester() && ['dashboard','requests','notifications','profile',...detailViews].includes(view)) await loadRequester();
    if (!state.user && ['dashboard','requests','notifications',...detailViews].includes(view)) await loadPublicTracked();
    if (isStaff() && view==='notifications') {
      const feed = await api('/api/admin/notifications');
      state.notifications = feed.notifications; state.unread = feed.unread;
    }
    if (ticket!==state.renderToken) return;
    const html = view==='login' ? loginPage() : view==='register' ? registerPage() : view==='verify-email' ? verifyEmailPage() : view==='dashboard' ? (isStaff()?adminDashboard():isRequester()?requesterDashboard():publicDashboard())
      : view==='requests' ? (isStaff()?adminRequests():publicRequests())
      : view==='claimed' ? claimedPage()
      : view==='notifications' ? notificationsPage() : isDetailView(view) ? dashboardDetailPage(view) : profilePage();
    target.innerHTML = html;
    updateChrome();
    if (view==='requests' && isStaff()) renderStaffRows();
    if (view==='claimed' && isStaff()) renderClaimedRows();
    if (!state.user && state.trackedResult && $('#inlineTrackResult')) $('#inlineTrackResult').innerHTML=renderTrackCard(state.trackedResult);
  } catch (error) {
    if (ticket!==state.renderToken) return;
    target.innerHTML = empty('Unable to load this page',escapeHtml(error.message),button('Try again','refresh','primary'));
    toast(error.message,true);
  }
}
function authFrame(formHtml, register=false) {
  return `<div class="auth-landing"><div class="auth-frame">
    <header class="auth-header"><div class="auth-brand"><span class="auth-brand-icon">Q<span class="auth-brand-spark">✦</span></span><span><strong>QueueWise<span class="brand-dot">.</span></strong><small>DOCUMENT REQUEST & RELEASE PORTAL</small></span></div>
    <div class="auth-header-actions"><button class="auth-header-link" data-action="help">${icon('help')}<span>How it works</span></button><button class="auth-header-link" data-action="theme">${icon('moon')}<span>Appearance</span></button><button class="auth-header-link auth-home-link" data-action="go-dashboard">${icon('home')}<span>Public portal</span></button></div></header>
    <div class="auth-columns"><section class="auth-story" aria-label="QueueWise introduction">
      <p class="auth-kicker"><span></span> A SMARTER WAY TO REQUEST DOCUMENTS</p><h1>Your documents, <span>one simple portal.</span></h1>
      <p class="auth-description">A dedicated space for students, alumni, and registrar staff. Register, submit academic document requests, and check every update in one place.</p>
      <div class="auth-feature-grid">
        <div class="auth-feature"><span>${icon('user')}</span><div><strong>One account, one workspace</strong><p>Student and Alumni share the same registration design and get their own secure login.</p></div></div>
        <div class="auth-feature"><span>${icon('document')}</span><div><strong>Document request tracking</strong><p>Request TOR, certificates and more; see status changes in My Requests.</p></div></div>
        <div class="auth-feature"><span>${icon('check')}</span><div><strong>Collection confirmation</strong><p>Registrar staff confirm when a document has been physically claimed.</p></div></div>
      </div><div class="auth-story-actions"><button class="button primary" data-action="${register?'login':'register'}">${register?'Already have an account? Sign in':'Create a student / alumni account'} ${icon('arrow')}</button></div>
      <div class="auth-trust">${icon('shield')} Academic prototype · Simulated records · Not an official registrar service</div>
    </section><section class="auth-signin" aria-label="${register?'Student or Alumni registration':'Account sign in'}">
      <div class="auth-signin-card">${formHtml}</div>
      <div class="auth-install"><span>${icon('download')}</span><div><strong>Install as a Progressive Web App</strong><p>Use QueueWise in its own app window.</p></div><button class="button outline sm" data-action="install">Install app</button></div>
    </section></div><footer class="auth-footer"><span>© ${new Date().getFullYear()} QueueWise · Academic demonstration only</span><span>Built with Python + SQLite · PWA ready</span></footer>
  </div></div>`;
}
function loginPage() {
  const staff=state.authTab==='staff';
  const role=state.authTab==='Alumni'?'Alumni':'Student';
  const roleDescription=staff?'Access the secure document queue and registrar operations.':role==='Alumni'?'Access graduate document requests, release updates, and your alumni records.':'Access current student document requests, deadlines, and your own status updates.';
  return authFrame(`<div class="auth-signin-icon">${icon(staff?'shield':'user')}</div><p class="eyebrow">${staff?'REGISTRAR ACCESS':`${role.toUpperCase()} PORTAL`}</p>
    <h2>${staff?'Registrar sign in.':role==='Alumni'?'Welcome back, graduate.':'Welcome back, student.'}</h2><p class="auth-card-intro">${roleDescription}</p>
    <div class="auth-role-tabs auth-role-tabs-three" role="tablist" aria-label="Choose account type">
      <button type="button" role="tab" aria-selected="${!staff && role==='Student'}" class="${!staff && role==='Student'?'selected':''}" data-auth-tab="Student">Student</button>
      <button type="button" role="tab" aria-selected="${!staff && role==='Alumni'}" class="${!staff && role==='Alumni'?'selected':''}" data-auth-tab="Alumni">Alumni</button>
      <button type="button" role="tab" aria-selected="${staff}" class="${staff?'selected':''}" data-auth-tab="staff">Registrar</button></div>
    ${staff?`<form id="loginForm" class="form-stack"><label class="form-label">Username<input id="username" name="username" autocomplete="username" required maxlength="100" placeholder="Registrar username" value="admin"></label><label class="form-label">Password<input name="password" type="password" autocomplete="current-password" required maxlength="256" placeholder="Your staff password"></label><p id="authError" class="auth-error hidden" role="alert"></p><button class="button primary full auth-submit" id="loginSubmit" type="submit">Sign in as registrar ${icon('arrow')}</button></form>`
    :`<form id="requesterLoginForm" class="form-stack"><input type="hidden" name="account_type" value="${role}"><label class="form-label">${role} email address<input type="email" name="email" autocomplete="email" maxlength="254" required placeholder="you@example.com"></label><label class="form-label">Password<input type="password" name="password" autocomplete="current-password" maxlength="256" required placeholder="Enter your password"></label><p id="authError" class="auth-error hidden" role="alert"></p><button class="button primary full auth-submit" id="requesterLoginSubmit" type="submit">Enter ${role} Portal ${icon('arrow')}</button></form>`}
    ${!staff?`<div class="auth-form-bottom"><span>Not verified yet?</span><button class="inline-link" data-action="verify-email">Resend verification email ${icon('arrow')}</button></div>`:''}
    <div class="auth-join-box"><span class="auth-join-label">NEW TO QUEUEWISE?</span><p>Create a free account to request documents. An email verification link is required before sign-in.</p><div class="auth-join-actions"><button class="button outline sm" type="button" data-action="register-student">${icon('user')} Register as Student</button><button class="button outline sm" type="button" data-action="register-alumni">${icon('document')} Register as Alumni</button></div></div>
    <div class="auth-private-note">${icon('shield')} Account permissions are checked on the server.</div>
    <div class="auth-form-bottom"><span>${staff?'Requesting a document?':'Already have an account?'}</span><button class="inline-link" data-action="${staff?'switch-requester':'login'}">${staff?'Student / Alumni sign in':'Choose a sign-in tab above'} ${icon('arrow')}</button></div>`,false);
}
function registerPage() {
  const alumni=state.registerRole==='Alumni';
  const role=alumni?'Alumni':'Student';
  return authFrame(`<div class="auth-signin-icon">${icon('user')}</div><p class="eyebrow" id="registerEyebrow">${role.toUpperCase()} REGISTRATION</p><h2 id="registerHeadline">Create your ${role.toLowerCase()} account.</h2>
    <p class="auth-card-intro" id="registerIntro">${alumni?'An alumni account gives you a private workspace for graduate credential requests and collection updates.':'A student account gives you a private workspace for academic requirements and request status updates.'}</p>
    <div class="register-role-picker" role="group" aria-label="Select your registration type">
      <button type="button" class="register-role-option ${alumni?'':'selected'}" data-register-role="Student" aria-pressed="${!alumni}">${icon('user')}<span><strong>Student</strong><small>Currently enrolled</small></span>${icon('check')}</button>
      <button type="button" class="register-role-option ${alumni?'selected':''}" data-register-role="Alumni" aria-pressed="${alumni}">${icon('document')}<span><strong>Alumni</strong><small>Former student / graduate</small></span>${icon('check')}</button>
    </div>
    <form id="registerForm" class="form-stack">
      <input type="hidden" id="registerType" name="account_type" value="${role}">
      <label class="form-label"><span>Full name <span class="required">*</span></span><input name="full_name" minlength="2" maxlength="60" autocomplete="name" placeholder="e.g. Juan Dela Cruz" required></label>
      <label class="form-label"><span id="registrationNumberCaption">${alumni?'Former student number':'Student number'}</span> <span class="required">*</span><input name="student_number" minlength="5" maxlength="24" pattern="[A-Za-z0-9][A-Za-z0-9-]{4,23}" placeholder="${alumni?'e.g. 2018-12345':'e.g. 2026-12345'}" required></label>
      <label class="form-label"><span>Email address <span class="required">*</span></span><input type="email" name="email" maxlength="254" autocomplete="email" placeholder="you@example.com" required></label>
      <div class="auth-pass-columns"><label class="form-label"><span>Create password <span class="required">*</span></span><input type="password" name="password" minlength="10" maxlength="128" autocomplete="new-password" required></label><label class="form-label"><span>Confirm password <span class="required">*</span></span><input type="password" name="confirm_password" minlength="10" maxlength="128" autocomplete="new-password" required></label></div>
      <small class="password-hint">At least 10 characters, with uppercase, lowercase, a number, and a symbol. Verify your email before your first login.</small>
      <p id="registerError" class="auth-error hidden" role="alert"></p>
      <button type="submit" class="button primary full auth-submit" id="registerSubmit">Create ${role.toLowerCase()} account ${icon('arrow')}</button>
    </form>
    <div class="auth-private-note">${icon('shield')} The email verification link expires in 24 hours. This is a school prototype and does not verify institutional enrollment or graduation.</div>
    <div class="auth-form-bottom"><span>Already registered?</span><button class="inline-link" data-action="login">Sign in ${icon('arrow')}</button></div>`,true);
}
function switchRegistrationRole(role) {
  if (!['Student','Alumni'].includes(role)) return;
  state.registerRole=role;
  const alumni=role==='Alumni';
  $('#registerType').value=role;
  $('#registerEyebrow').textContent=`${role.toUpperCase()} REGISTRATION`;
  $('#registerHeadline').textContent=`Create your ${role.toLowerCase()} account.`;
  $('#registerIntro').textContent=alumni?'An alumni account gives you a private workspace for graduate credential requests and collection updates.':'A student account gives you a private workspace for academic requirements and request status updates.';
  $('#registrationNumberCaption').textContent=alumni?'Former student number':'Student number';
  $('#registerSubmit').textContent=`Create ${role.toLowerCase()} account →`;
  const number=$('#registerForm [name="student_number"]');
  number.placeholder=alumni?'e.g. 2018-12345':'e.g. 2026-12345';
  $$('[data-register-role]').forEach(button=>{
    const selected=button.dataset.registerRole===role;
    button.classList.toggle('selected',selected);
    button.setAttribute('aria-pressed',selected?'true':'false');
  });
}
function verifyEmailPage() {
  const params = new URLSearchParams(location.hash.split('?')[1] || '');
  const token = params.get('token') || '';
  const linkValid = /^[A-Za-z0-9_-]{32,128}$/.test(token);
  return authFrame(`<div class="auth-signin-icon">${icon('shield')}</div><p class="eyebrow">ACCOUNT SECURITY</p>
    <h2>Verify your email.</h2><p class="auth-card-intro">Open the verification link we emailed to you, then confirm your account. Links expire after 24 hours.</p>
    ${linkValid?`<form id="verifyEmailForm" class="form-stack"><p class="auth-private-note">${icon('check')} Verification link detected. Click below to activate your account.</p><p class="auth-error hidden" id="verificationError" role="alert"></p><button class="button primary full auth-submit" type="submit" id="verifySubmit">Verify my email ${icon('arrow')}</button></form>`:`<p class="auth-private-note">${icon('info')} No active verification link found. Check your inbox, or send a new verification email.</p>`}
    <form id="resendVerificationForm" class="form-stack" style="margin-top:24px">
      <label class="form-label">Registered email address<input name="email" type="email" required autocomplete="email" maxlength="254" placeholder="you@example.com" value="${escapeHtml(state.verificationEmail)}"></label>
      <p id="resendError" class="auth-error hidden" role="alert"></p><button class="button outline full" id="resendSubmit" type="submit">Resend verification email ${icon('arrow')}</button>
    </form><div class="auth-form-bottom"><span>Verified already?</span><button class="inline-link" data-action="login">Go to sign in ${icon('arrow')}</button></div>`,false);
}
function hero({staff=false}={}) {
  const label = staff?'REGISTRAR CONTROL CENTER':'DOCUMENT REQUEST PORTAL';
  const title = staff?'Your registrar workspace, simplified.':'A smarter way to request documents.';
  const description = staff?'Monitor the queue, review the latest requests, and process academic documents with confidence.':'Submit your request online, keep your reference ID, and follow its progress—all in one convenient place.';
  return `<section class="hero"><div class="hero-copy"><div class="hero-label">${label}</div><h1>${title}</h1><p>${description}</p><div class="hero-actions">${staff?button(`${icon('layers')} Open request queue`,'go-requests','white'):button(`${icon('plus')} New document request`,'go-requests','white')}${staff?button('Refresh dashboard','refresh','transparent'):button('Track my request','focus-track','transparent')}</div></div><div class="hero-art" aria-hidden="true"><div class="art-page"><div class="art-line" style="margin-top:47px"></div><div class="art-line short"></div><div class="art-line"></div><div class="art-check">${icon('check')}</div></div><div class="art-small">${icon('document')}</div></div></section>`;
}
function stat(label,number,caption,symbol) { return `<article class="stat-card"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon(symbol)}</span></div><strong>${number}</strong><p class="stat-caption">${caption}</p></article>`; }
// Native buttons support mouse, keyboard (Enter/Space), and assistive technologies.
function dashboardStat(label,number,caption,symbol,detail) {
  return `<button type="button" class="stat-card stat-card-link" data-action="open-dashboard-card" data-detail="${detail}" aria-label="Open ${escapeHtml(label)} details"><span class="stat-top"><span>${escapeHtml(label)}</span><span class="stat-icon">${icon(symbol)}</span></span><strong>${escapeHtml(number)}</strong><span class="stat-caption">${escapeHtml(caption)}</span><span class="stat-card-cta">View details ${icon('arrow')}</span></button>`;
}

function adminDashboard() {
  const data=state.adminData, stats=data.stats;
  const recent=data.requests.slice(0,8);
  return hero({staff:true})+`<section class="admin-welcome"><div><span class="eyebrow">REGISTRAR REQUEST MONITORING</span><h2>Student and alumni transactions</h2><p>Review incoming document requests, prepare releases, and confirm collection. A processed document still needs registrar approval before collection.</p></div><div class="admin-welcome-actions">${button(`${icon('document')} View requests`,'go-requests','outline')}${button(`${icon('check')} Claimed / Released`,'go-claimed','primary')}</div></section>
    <section class="stat-grid admin-stat-grid">${stat('Student Requests',stats.students,'Submitted by students','user')}${stat('Alumni Requests',stats.alumni,'Submitted by alumni','user')}${stat('Pending Queue',stats.pending,'Waiting for processing','clock')}${stat('Approved for Pickup',stats.ready_to_claim,'Awaiting physical collection','document')}${stat('Claimed / Released',stats.claimed,'Confirmed handovers','check')}${stat('All Requests',stats.total,'Including legacy records','layers')}</section>
    <div class="section-grid"><section class="panel"><div class="panel-header"><div><h2>Recent student & alumni requests</h2><p>Latest submissions, requester type and current status</p></div><button class="text-button" data-action="go-requests">View all ${icon('arrow')}</button></div><div class="table-wrap"><table class="data-table"><thead><tr><th>Request ID</th><th>Requester / Document</th><th>Type</th><th>Status</th></tr></thead><tbody>${recent.map(r=>`<tr><td class="main-cell">${escapeHtml(r.public_id)}</td><td class="main-cell">${escapeHtml(r.requester_name)}<span class="sub-cell">${escapeHtml(r.document_type)}</span></td><td><span class="requester-pill">${escapeHtml(requesterLabel(r))}</span></td><td>${statusBadge(effectiveStatus(r))}</td></tr>`).join('')||`<tr><td colspan="4">${empty('No requests yet','Student and alumni submissions will appear here once received.')}</td></tr>`}</tbody></table></div></section>
      <section class="panel pad"><div class="panel-header" style="padding:0 0 20px"><div><h2>Next request in queue</h2><p>Automatically selected by priority score</p></div>${icon('layers')}</div><div class="quick-next"><small>NEXT DOCUMENT REQUEST</small><strong>${escapeHtml(data.next_id||'Queue is clear')}</strong><div class="next-details"><span>${stats.pending} pending</span><span>Auto-ranked by score</span></div>${button(`${icon('check')} Process next request`,'process-next','primary',stats.pending?'':'disabled')}</div><h3 class="subheading">Ready for collection</h3><p class="panel-subtitle">${stats.ready_to_claim} document(s) are ready for the student or alumni to pick up.</p>${button('Manage requests','go-requests','outline')}</section></div>
    <div class="panel pad"><div class="panel-header" style="padding:0 0 18px"><div><h2>Data structure monitoring</h2><p>FIFO arrival log, priority min-heap and separate-chaining hash lookup</p></div><span class="badge status-info">Live demonstration</span></div><div class="adt-row"><div class="adt-card"><span>${icon('list')}</span><div><strong>FIFO Arrival Queue</strong><p>${stats.total} request IDs retained in arrival order</p></div></div><div class="adt-card"><span>${icon('layers')}</span><div><strong>Binary Min-Heap</strong><p>${stats.heap_entries} pending • ${stats.heap_valid?'Valid heap':'Needs attention'}</p></div></div><div class="adt-card"><span>${icon('search')}</span><div><strong>Chained Hash Table</strong><p>${stats.hash_entries} records • ${stats.hash_buckets} buckets</p></div></div></div></div>`;
}
function requesterDashboard() {
 const items=state.myRequests||[];
 const active=items.filter(r=>!['Processed','Claimed','Cancelled','Declined'].includes(r.status)).length;
 const ready=items.filter(r=>r.status==='Ready for Release').length;
 const claimed=items.filter(r=>r.status==='Claimed').length;
 const alumni=isAlumni();
 const heading=alumni?'Alumni dashboard':'Student dashboard';
 const subtitle=alumni?'Your graduate document requests, status history and collection updates.':'Your academic document requests, required dates and progress updates.';
 const title=alumni?'Your next chapter, supported.':'Stay on track with your academic documents.';
 const intro=alumni?'Request transcripts and certificates for employment, graduate studies or credential verification. Follow each request from submission to pickup.':'Request academic documents for scholarships, enrollment, graduation or transfer. Know when your records are ready for collection.';
 return pageHeading(heading,subtitle,button(`${icon('plus')} New request`,'new-request'))+
  `<section class="requester-banner ${alumni?'alumni-portal':'student-portal'}"><div><p class="eyebrow">${alumni?'ALUMNI PORTAL':'STUDENT PORTAL'} · ${escapeHtml(state.user.display_name.split(' ')[0])}</p><h2>${title}</h2><p>${intro}</p></div><div class="requester-banner-symbol">${icon(alumni?'shield':'document')}</div></section>
  <section class="stat-grid">${dashboardStat('My Requests',items.length,'Requests on your account','document','tracked')}${dashboardStat('Active Requests',active,'Pending, processing or awaiting pickup','clock','active')}${dashboardStat('Ready to Collect',ready,'Available after registrar approval','bell','ready')}${dashboardStat('Claimed',claimed,'Confirmed handovers','check','completed')}</section>
  <section class="role-info-row"><div class="role-info-icon">${icon(alumni?'shield':'calendar')}</div><div><strong>${alumni?'Alumni Document Services':'Student Academic Records'}</strong><p>${alumni?'Request employment, graduate-school or credential documents with your former student number.':'Use your student number to submit academic records requests and monitor deadlines.'}</p></div>${button('New document request','new-request','outline')}</section>
  <section class="panel"><div class="panel-header"><div><h2>${alumni?'My alumni requests':'My student requests'}</h2><p>Visible only to your verified ${alumni?'alumni':'student'} account</p></div>${button('Submit another','go-requests','outline')}</div>${myRequestsTable(items)}</section>`;
}
// Inline needed-by picker. Lives ONLY in New Document Request, never a separate page.
// Use local calendar dates and never convert a user's chosen day into UTC.
const dateKey = dt => `${dt.getFullYear()}-${String(dt.getMonth()+1).padStart(2,'0')}-${String(dt.getDate()).padStart(2,'0')}`;
const parseCalendarDate = key => /^\d{4}-\d{2}-\d{2}$/.test(key||'') ? new Date(Number(key.slice(0,4)), Number(key.slice(5,7))-1, Number(key.slice(8,10))) : new Date();
function pickerMonthMarkup() {
  const today = state.today || dateKey(new Date());
  const chosen = state.selectedCalendarDay || state.requestDate || today;
  const focus = parseCalendarDate(state.calendarAnchor || chosen);
  const title = new Intl.DateTimeFormat('en-PH', {month:'long',year:'numeric'}).format(focus);
  const first = new Date(focus.getFullYear(), focus.getMonth(),1);
  const start = new Date(first);
  start.setDate(first.getDate() - ((first.getDay()+6)%7));
  const limit = dateKey(new Date(parseCalendarDate(today).getFullYear()+3,parseCalendarDate(today).getMonth(),parseCalendarDate(today).getDate()));
  const cells=Array.from({length:42},(_,i)=>{
    const date=new Date(start);date.setDate(start.getDate()+i);
    const key=dateKey(date), disabled=key<today||key>limit;
    const outside=date.getMonth()!==focus.getMonth();
    return `<button type="button" class="needed-day ${outside?'outside':''} ${key===today?'is-today':''} ${key===chosen?'is-selected':''}" data-needed-day="${key}" aria-label="${dayLabel(key)}${disabled?', unavailable':''}" aria-pressed="${key===chosen}" ${disabled?'disabled':''}><span>${date.getDate()}</span></button>`;
  }).join('');
  return `<div class="needed-calendar-head"><div><p class="eyebrow">SELECT DATE NEEDED</p><h3>${title}</h3></div><div class="needed-calendar-controls"><button type="button" class="needed-calendar-today" data-needed-nav="today">Today</button><button type="button" data-needed-nav="prev" aria-label="Previous month">‹</button><button type="button" data-needed-nav="next" aria-label="Next month">›</button></div></div>
   <div class="needed-weekdays">${['M','T','W','T','F','S','S'].map((x,i)=>`<span aria-label="${['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][i]}">${x}</span>`).join('')}</div>
   <div class="needed-day-grid">${cells}</div>
   <div class="needed-calendar-footer"><div><span>YOUR CHOICE</span><strong>${dayLabel(chosen)}</strong><small>This is your requested date, not a promised release date.</small></div><button class="button primary" type="button" data-action="apply-needed-date" ${chosen<today||chosen>limit?'disabled':''}>${icon('check')} Use this date</button></div>`;
}
function dateNeededWidget() {
  const selected=state.requestDate;
  return `<div class="form-label full-span needed-date-field"><span>Date Needed <span class="required">*</span></span>
    <input type="hidden" id="dateNeededValue" name="deadline" value="${escapeHtml(selected)}">
    <div class="needed-date-box"><span class="needed-calendar-symbol">${icon('calendar')}</span><div class="needed-date-copy"><small>WHEN DO YOU NEED YOUR DOCUMENT?</small><strong id="dateNeededLabel">${selected?dayLabel(selected):'Select your preferred date'}</strong><span>Registrar staff will see this date when reviewing your request.</span></div><button type="button" class="button outline" id="openDatePicker" data-action="toggle-needed-picker" aria-expanded="${state.pickerOpen}" aria-controls="neededCalendarContent">${icon('calendar')} ${selected?'Change date':'Choose date'}</button></div>
    <div class="needed-calendar ${state.pickerOpen?'':'hidden'}" id="neededCalendarContent">${pickerMonthMarkup()}</div>
    <small>Select today or a future date (up to 3 years ahead). This date affects the priority score, but release still needs registrar approval.</small>
  </div>`;
}
function redrawNeededPicker(){
  const picker=$('#neededCalendarContent'); if(!picker)return;
  picker.classList.toggle('hidden',!state.pickerOpen);
  if(state.pickerOpen)picker.innerHTML=pickerMonthMarkup();
  const button=$('#openDatePicker');if(button){button.setAttribute('aria-expanded',String(state.pickerOpen));button.innerHTML=`${icon('calendar')} ${state.requestDate?'Change date':'Choose date'}`;}
}
function moveNeededMonth(direction){
  if(direction==='today'){state.calendarAnchor=state.today;state.selectedCalendarDay=state.today;}
  else {
    const focus=parseCalendarDate(state.calendarAnchor || state.today);
    focus.setDate(1); focus.setMonth(focus.getMonth()+(direction==='prev'?-1:1));
    const minimum=parseCalendarDate(state.today);
    if(focus.getFullYear()<minimum.getFullYear()-1 || focus.getFullYear()>minimum.getFullYear()+4)return;
    state.calendarAnchor=dateKey(focus);
  }
  redrawNeededPicker();
}
function chooseNeededDate(day){
  const today=state.today || dateKey(new Date());
  const max=new Date(parseCalendarDate(today)); max.setFullYear(max.getFullYear()+3);
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day||'') || day<today || day>dateKey(max)) {
    toast('Choose today or a future date within three years.',true);return;
  }
  state.selectedCalendarDay=day;
  state.calendarAnchor=day;
  redrawNeededPicker();
}
function applyNeededDate(){
  const day=state.selectedCalendarDay;
  const today=state.today || dateKey(new Date());
  const max=new Date(parseCalendarDate(today));max.setFullYear(max.getFullYear()+3);
  if(!day || day<today || day>dateKey(max)){toast('Choose a valid date first.',true);return;}
  state.requestDate=day;state.pickerOpen=false;
  const input=$('#dateNeededValue'), label=$('#dateNeededLabel');
  if(input)input.value=day;
  if(label)label.textContent=dayLabel(day);
  redrawNeededPicker();
  toast(`Date Needed: ${dayLabel(day)}. You can now submit your request.`);
}
function myRequestsTable(items) {
  if(!items?.length) return empty('No requests yet','Create a request for one or more documents to see them here.',button('New request','new-request','primary'));
  return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Reference</th><th>Requested documents</th><th>Date Needed / Why</th><th>Registrar decision</th><th>Collection schedule</th><th>Action</th></tr></thead><tbody>${items.map(r=>`<tr>
    <td class="main-cell">${escapeHtml(r.public_id)}<span class="sub-cell">${dayLabel(r.submission_date)}</span></td>
    <td><div class="doc-chip-list">${documentsMarkup(r)}</div><span class="sub-cell">Purpose: ${escapeHtml(r.purpose||'—')}</span></td>
    <td>${dayLabel(r.deadline)}<span class="sub-cell wrap-cell">${escapeHtml(r.date_reason||'No date explanation (legacy record)')}</span></td>
    <td>${statusBadge(r.status)}${r.declined_reason?`<p class="decision-note"><strong>Decline reason:</strong> ${escapeHtml(r.declined_reason)}</p>`:''}${r.cancelled_reason?`<p class="decision-note">${escapeHtml(r.cancelled_reason)}</p>`:''}</td>
    <td>${r.pickup_at?`<strong>${datetime(r.pickup_at)}</strong><span class="sub-cell wrap-cell">${escapeHtml(r.pickup_note||'Collection at the registrar')}</span>`:'<span class="muted-final">To be scheduled by registrar</span>'}</td>
    <td>${canCancel(r)?button('Cancel request','open-cancel','outline sm',`data-id="${escapeHtml(r.public_id)}"`):'<span class="muted-final">—</span>'}</td>
  </tr>`).join('')}</tbody></table></div>`;
}
function publicDashboard() {
  const current=state.publicTracked;
  const active=current.filter(x=>!['Processed','Claimed','Cancelled','Declined'].includes(x.request.status)).length;
  const completed=current.filter(x=>['Processed','Claimed'].includes(x.request.status)).length;
  return hero()+`<section class="stat-grid">${dashboardStat('My Tracked Requests',current.length,'Stored on this browser','document','tracked')}${dashboardStat('Active Requests',active,'Pending or in progress','clock','active')}${dashboardStat('Completed Requests',completed,'Marked as processed','check','completed')}${dashboardStat('Online Portal','PWA','Available while server is running','shield','portal')}</section>
    <div class="section-grid"><section class="panel pad"><div class="panel-header" style="padding:0 0 13px"><div><h2>Track a document request</h2><p>Enter your assigned reference number for an instant status check.</p></div>${icon('search')}</div><form class="tracker-form" data-form="track"><input class="filter-input" aria-label="Request ID" id="homeTrackInput" name="request_id" placeholder="Example: REQ-0001" required pattern="REQ-[0-9]{4,}" maxlength="24"><button class="button primary" type="submit">${icon('search')} Check status</button></form><div id="inlineTrackResult" class="tracker-result"></div><div class="divider"></div><div class="panel-header" style="padding:0 0 17px"><div><h2>Recently tracked</h2><p>Your requests remembered on this device</p></div></div>${recentTracked()}</section>
    <section class="panel pad"><div class="panel-header" style="padding:0 0 5px"><div><h2>Getting started is easy</h2><p>Three simple steps from request to processing</p></div></div><div class="step-list"><div class="step-item"><div class="step-no">01</div><div><strong>Fill in the request form</strong><p>Select your document type, category, and Date Needed, then submit your complete name.</p></div></div><div class="step-item"><div class="step-no">02</div><div><strong>Keep your reference ID</strong><p>QueueWise automatically generates a unique ID for every successful submission.</p></div></div><div class="step-item"><div class="step-no">03</div><div><strong>Check your request status</strong><p>Use your reference ID anytime to view pending, processing, and completed stages.</p></div></div></div><div class="tip-box">${icon('info')}<span>QueueWise is an academic prototype. It does not submit official document requests to the university.</span></div></section></div>`;
}
// The four dashboard cards open actual bookmarkable pages. For signed-in users
// every row comes from /api/my/requests; anonymous pages use minimal public
// tracking data for request IDs previously entered on this browser.
function dashboardDetailPage(view) {
  const own=isRequester();
  const isGuest=!state.user;
  const titles={tracked:own?'My Requests':'My Tracked Requests',active:own?'Pending Requests':'Active Requests',completed:own?'Claimed Documents':'Completed Requests',ready:'Ready to Collect',portal:'Online Portal & PWA'};
  const summaries={tracked:own?'Document requests submitted through your verified account.':'Request IDs you previously tracked on this browser.',active:'Requests that still need processing, approval or pickup.',completed:own?'Documents whose physical pickup was confirmed by the registrar.':'Processing-completed or physically claimed requests.',ready:'Documents approved by the registrar and waiting for collection.',portal:'Install QueueWise, access your account, and learn how to track your documents.'};
  const top=pageHeading(titles[view],summaries[view],button(`${icon('arrow')} Back to Dashboard`,'go-dashboard','outline'));
  if(view==='portal') return top+`<section class="detail-hero panel pad"><span class="detail-hero-icon">${icon('shield')}</span><div><span class="eyebrow">PROGRESSIVE WEB APP</span><h2>QueueWise on your device</h2><p>Install the portal from your browser when installation is supported. You can open the app from your home screen, but submitting requests and checking live status still require internet/server access.</p><div class="detail-actions">${button(`${icon('document')} Install QueueWise`,'install','primary')}${button('How the system works','help','outline')}</div></div></section><section class="detail-grid"><div class="panel pad"><h2>Access your portal</h2><p class="panel-subtitle">Sign in to see only your own Student or Alumni document requests.</p><div class="detail-actions">${state.user?button('My profile','profile','outline'):button('Sign in','login','primary')}${!state.user?button('Create an account','register','outline'):button('My requests','my-requests','outline')}</div></div><div class="panel pad"><h2>Installation information</h2><p class="panel-subtitle">Chrome or Edge may offer an Install button. If the native prompt is unavailable, use the browser menu and choose Install app or Add to home screen when offered.</p><div class="tip-box">${icon('info')}<span>Offline mode shows a basic information page; it does not submit or retrieve document requests without the server.</span></div></div></section>`;
  const rows=own?(state.myRequests||[]):(state.publicTracked||[]);
  const statusOf=x=>own?x.status:x.request.status;
  const includesRow=x=>view==='tracked'||(view==='active'?!['Processed','Claimed','Cancelled','Declined'].includes(statusOf(x)):view==='completed'?(own?statusOf(x)==='Claimed':['Processed','Claimed'].includes(statusOf(x))):view==='ready'&&own&&statusOf(x)==='Ready for Release');
  const selected=rows.filter(includesRow);
  const title=own?'My document requests':'Tracked request history';
  const statusNote=view==='completed'&&!own?`<div class="tip-box">${icon('info')}<span>“Processed” means preparation completed; it does not guarantee the document was approved for release or collected. “Claimed” confirms physical handover.</span></div>`:'';
  const privacy=isGuest?`<div class="tip-box">${icon('shield')}<span>These are request IDs saved in this browser only, not a verified list of account-owned documents. Sign in for private Student/Alumni requests.</span></div>`:`<div class="tip-box">${icon('shield')}<span>Only records belonging to your verified ${escapeHtml(state.user.role)} account appear here.</span></div>`;
  const table=own?myRequestsTable(selected):selected.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Request ID</th><th>Status</th><th>Submitted</th><th>View</th></tr></thead><tbody>${selected.map(x=>`<tr><td class="main-cell">${escapeHtml(x.request.id)}</td><td>${statusBadge(x.request.status)}</td><td>${dayLabel(x.request.submitted_at)}</td><td><button class="row-action" data-action="show-tracked-detail" data-id="${escapeHtml(x.request.id)}">View status</button></td></tr>`).join('')}</tbody></table></div>`:empty('No matching requests yet','This section will update when a tracked request reaches the matching status.',own?button('New document request','new-request','primary'):button('Sign in or register','login','primary'));
  return top+`<section class="detail-intro panel pad"><div><span class="eyebrow">LIVE REQUEST STATUS</span><h2>${selected.length} ${selected.length===1?'request':'requests'} ${view==='tracked'?'tracked':view==='active'?'active':view==='completed'?'completed':view==='ready'?'ready for collection':''}</h2><p>${escapeHtml(summaries[view])}</p></div><span class="detail-count">${selected.length}</span></section><section class="panel"><div class="panel-header"><div><h2>${title}</h2><p>${escapeHtml(summaries[view])}</p></div>${button(`${icon('refresh')} Refresh`,'refresh','outline')}</div>${table}</section>${statusNote}${privacy}${!own?`<section class="panel pad" style="margin-top:18px"><h2>Track a different reference ID</h2><form class="tracker-form" data-form="track"><input class="filter-input" name="request_id" placeholder="REQ-0001" aria-label="Request ID" required pattern="REQ-[0-9]{4,}" maxlength="24"><button type="submit" class="button primary">Check status</button></form><div id="inlineTrackResult" class="tracker-result"></div></section>`:''}`;
}
function recentTracked() {
  return state.publicTracked.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Request ID</th><th>Status</th><th>Submitted</th><th></th></tr></thead><tbody>${state.publicTracked.slice(0,5).map(x=>`<tr><td class="main-cell">${escapeHtml(x.request.id)}</td><td>${statusBadge(x.request.status)}</td><td>${dayLabel(x.request.submitted_at)}</td><td><button class="row-action" data-action="quick-track" data-id="${escapeHtml(x.request.id)}">View</button></td></tr>`).join('')}</tbody></table></div>`:empty('No tracked requests yet','After submitting a request, your reference number will appear here.',button('Submit a request','go-requests','light'));
}
function publicRequests() {
 if (!isRequester()) return pageHeading('Document request','Sign in or create an account to submit documents, or track an existing reference ID.')+
   `<section class="panel pad guest-request-prompt"><div class="auth-signin-icon">${icon('user')}</div><h2>Start with your Student / Alumni account</h2><p>Both students and alumni use the same registration page. Your requests and statuses will stay linked to your account.</p><div class="guest-actions">${button('Create account','register','primary')}${button('Sign in','login','outline')}</div></section>`+
   `<section class="panel pad" style="margin-top:18px"><h2>Track by reference ID</h2><p class="panel-subtitle">For previously submitted requests, you can still check a minimal status using the request ID.</p><form class="tracker-form" data-form="track"><input class="filter-input" name="request_id" placeholder="REQ-0001" required pattern="REQ-[0-9]{4,}" maxlength="24" aria-label="Request ID"><button class="button light" type="submit">Track</button></form><div id="inlineTrackResult"></div></section>`;
 const alumni=isAlumni();
 const mine=state.myRequests||[];
 const pending=mine.filter(r=>r.status==='Pending').length;
 const awaiting=mine.filter(r=>r.status==='Awaiting Approval').length;
 const ready=mine.filter(r=>r.status==='Ready for Release').length;
 const claimed=mine.filter(r=>r.status==='Claimed').length;
 const heading=alumni?'My Alumni Document Requests':'My Student Document Requests';
 const desc=alumni?'Only requests submitted with your verified Alumni account appear here.':'Only requests submitted with your verified Student account appear here.';
 const mineMarkup=`<section class="requester-mine-banner panel"><div><span class="eyebrow">${alumni?'ALUMNI':'STUDENT'} · MY REQUESTS</span><h2>Your documents, your account.</h2><p>Only documents you requested are listed here. Other students and alumni cannot view your records. Registrar approval is required before collection.</p></div><div class="requester-mine-icon">${icon('document')}</div></section>
 <div class="mine-request-stats">${stat('My Requests',mine.length,'Submitted by your account','document')}${stat('Pending',pending,'Awaiting processing','clock')}${stat('Awaiting Approval',awaiting,'Admin decision required','shield')}${stat('Ready to Collect',ready,'Approved by registrar','check')}</div>
 <section class="panel"><div class="panel-header"><div><h2>${alumni?'My alumni requests':'My student requests'}</h2><p>${mine.length} document request(s) belonging to your account · newest first</p></div><span class="badge status-info">Private to you</span></div>${myRequestsTable(mine)}<div class="mine-privacy-note">${icon('shield')}<span>Requests are linked to your verified account, not just your name or student number. Claimed: ${claimed}.</span></div></section>`;
 const modeTabs=`<div class="my-request-switch" role="group" aria-label="Document request sections"><button type="button" class="${state.requestMode==='mine'?'selected':''}" data-action="my-requests" aria-pressed="${state.requestMode==='mine'}">${icon('document')} My Requests (${mine.length})</button><button type="button" class="${state.requestMode==='new'?'selected':''}" data-action="new-request" aria-pressed="${state.requestMode==='new'}">${icon('plus')} New Request</button></div>`;
 const requestFormMarkup = `<div class="form-layout"><section class="panel form-section"><p class="eyebrow">NEW DOCUMENT REQUEST</p><h2>Request details</h2><p class="section-subtext">Your name and student number are linked to your ${escapeHtml(state.user.role)} account.</p>
 <form id="requestForm" class="form-grid">
 <input type="hidden" name="requester_name" value="${escapeHtml(state.user.display_name)}">
 <label class="form-label full-span">Full name<input value="${escapeHtml(state.user.display_name)}" readonly></label>
 <label class="form-label">Account type<select id="requesterType" disabled><option>${escapeHtml(state.user.role)}</option></select></label>
 <label class="form-label">${alumni?'Former student number':'Student number'}<input value="${escapeHtml(state.user.student_number)}" readonly></label>
 <fieldset class="form-label full-span doc-picker"><legend>Documents to request <span class="required">*</span> <small>(select up to 5)</small></legend><div class="doc-option-grid">${state.documents.map(x=>`<label class="doc-option"><input type="checkbox" name="document_types" value="${escapeHtml(x)}" ${state.requestDraft?.document_types?.includes(x)?'checked':''}><span>${icon('document')} ${escapeHtml(x)}</span></label>`).join('')}</div><small>All selected documents share one reference ID and one Date Needed.</small></fieldset>
 <label class="form-label"><span>Requester category <span class="required">*</span></span><select name="category" required><option value="">Select request category</option>${state.categories.map(x=>`<option value="${escapeHtml(x)}" ${state.requestDraft?.category===x?'selected':''}>${escapeHtml(x)}</option>`).join('')}</select></label>
 <label class="form-label full-span"><span>Purpose <span class="required">*</span></span><textarea name="purpose" minlength="6" maxlength="180" required rows="3" placeholder="${alumni?'e.g. Employment, graduate studies, credential verification':'e.g. Scholarship, graduation, enrollment, transfer'}">${escapeHtml(state.requestDraft?.purpose || '')}</textarea></label>
 ${dateNeededWidget()}
 <label class="form-label full-span"><span>Why do you need the documents on this date? <span class="required">*</span></span><textarea name="date_reason" minlength="10" maxlength="500" required rows="3" placeholder="e.g. Scholarship application closes on this date; I need the records before the deadline.">${escapeHtml(state.requestDraft?.date_reason||'')}</textarea><small>The registrar will read this explanation before deciding and scheduling collection.</small></label>
 <div class="submit-wrap full-span"><small>This is an academic simulation, not an official university request.</small><button type="submit" class="button primary" id="submitRequestButton">Submit document request ${icon('arrow')}</button></div>
 </form></section><div><section class="panel pad"><p class="eyebrow">YOUR ACCOUNT</p><h2 style="font-size:17px;margin-bottom:12px">${escapeHtml(state.user.role)} · ${escapeHtml(state.user.student_number)}</h2><p class="panel-subtitle">Your request will be queued automatically, and your status will update when the registrar takes action.</p><div class="step-list"><div class="step-item"><span class="step-no">1</span><div><strong>Submit your details</strong><p>Select one or more documents, explain your preferred date, and submit.</p></div></div><div class="step-item"><span class="step-no">2</span><div><strong>Receive a request ID</strong><p>The system records arrival and calculates the priority score.</p></div></div><div class="step-item"><span class="step-no">3</span><div><strong>Track until claimed</strong><p>Wait for a registrar decision and scheduled pickup date before collection. Staff will confirm once your document is received.</p></div></div></div></section><section class="panel pad" style="margin-top:18px"><h2 style="font-size:17px">My recent requests</h2>${myRequestsTable(state.myRequests.slice(0,4))}</section></div></div>`;
 return pageHeading(heading,desc,button(`${icon('plus')} New request`,'new-request','primary'))+modeTabs+(state.requestMode==='new'?requestFormMarkup:mineMarkup);
}
function renderTrackCard(data) {
  const r=data.request;
  return `<div class="track-detail"><div class="id-line"><strong>${escapeHtml(r.id)}</strong>${statusBadge(r.status)}</div><p><strong>Submitted:</strong> ${dayLabel(r.submitted_at)}</p><p><strong>Last updated:</strong> ${datetime(r.updated_at)}</p>${r.processed_at?`<p><strong>Processed:</strong> ${datetime(r.processed_at)}</p>`:''}${r.claimed_at?`<p><strong>Claimed / Received:</strong> ${datetime(r.claimed_at)}</p>`:''}<div class="timeline">${data.events.map(event=>`<div class="timeline-item"><span class="timeline-bullet"></span><div><strong>${escapeHtml(event.status)}</strong><p>${escapeHtml(event.message)}</p><small>${datetime(event.created_at)}</small></div></div>`).join('')}</div></div>`;
}
function adminRequests() {
  const stats=state.adminData.stats;
  return pageHeading('Document requests','View students and alumni, process documents, and confirm that documents have been received.',`${button(`${icon('refresh')} Refresh`,'refresh','outline')}${button(`${icon('plus')} Load sample data`,'seed','light')}${button(`${icon('check')} Process next`,'process-next','primary',stats.pending?'':'disabled')}`)+`<div class="top-tools"><div class="tab-bar" role="tablist"><button type="button" data-staff-tab="all" class="${state.staffTab==='all'?'active':''}">All requests</button><button type="button" data-staff-tab="priority" class="${state.staffTab==='priority'?'active':''}">Priority ranking</button><button type="button" data-staff-tab="arrival" class="${state.staffTab==='arrival'?'active':''}">FIFO arrivals</button></div></div><div class="filters"><input class="filter-input" id="staffSearch" placeholder="Search ID, name, document…" value="${escapeHtml(state.search)}" aria-label="Filter requests"><select class="filter-select" id="requesterFilter" aria-label="Filter requester type">${['All','Student','Alumni','Not specified'].map(t=>`<option value="${t}" ${state.requesterFilter===t?'selected':''}>${t==='All'?'All requester types':t}</option>`).join('')}</select><select class="filter-select" id="staffFilter" aria-label="Filter status">${['All','Pending','Processing','Awaiting Approval','Ready for Release','Pickup Scheduled','Processed','Claimed','Declined','Cancelled'].map(s=>`<option value="${s}" ${state.filter===s?'selected':''}>${s==='All'?'All statuses':s}</option>`).join('')}</select></div><section class="panel"><div class="panel-header"><div><h2 id="tableHeading">${state.staffTab==='priority'?'Priority ranking':state.staffTab==='arrival'?'FIFO arrival history':'All document requests'}</h2><p id="tableDescription">${state.staffTab==='priority'?'Highest score first, with deadline and arrival tie-breakers.':state.staffTab==='arrival'?'Original arrival order, including claimed requests.':'Staff can update progress and confirm pickup when documents are ready.'}</p></div><span class="badge status-info" id="recordCount">${stats.total} records</span></div><div id="staffTable"></div></section><div class="queue-summary"><span class="online-pip"></span><span>Scores refreshed on <strong>${todayLabel()}</strong></span><span>•</span><span>Min-heap verified: <strong>${stats.heap_valid?'Yes':'No'}</strong></span><span>•</span><span>Hash buckets: <strong>${stats.hash_buckets}</strong></span></div>`;
}
function nextStatusOptions(r) {
  return `<button class="button outline sm" type="button" data-action="review-request" data-id="${escapeHtml(r.public_id)}">${icon('eye')} Review</button>`;
}
function reviewRequestHtml(r) {
  const status=effectiveStatus(r);
  const closed=['Claimed','Declined','Cancelled'].includes(status);
  const canDecide=!closed&&!r.decision_at&&!r.approved_at;
  const canSchedule=!closed&&r.decision_at&&!r.approved_at;
  const canClaim=!closed&&r.approved_at;
  const deadlineReason=escapeHtml(r.date_reason||'Legacy record — no explanation provided');
  const earliest=new Date(Date.now()+24*60*60*1000);
  const localValue=String(earliest.getFullYear())+'-'+String(earliest.getMonth()+1).padStart(2,'0')+'-'+String(earliest.getDate()).padStart(2,'0')+'T'+String(earliest.getHours()).padStart(2,'0')+':'+String(earliest.getMinutes()).padStart(2,'0');
  return `<div class="review-card">
    <div class="review-overview"><span class="eyebrow">REQUEST DETAILS · ${escapeHtml(r.public_id)}</span><h3>${escapeHtml(r.requester_name)} <span class="requester-pill">${escapeHtml(requesterLabel(r))}</span></h3>
      <div class="review-meta"><div><small>Requested documents</small><div class="doc-chip-list">${documentsMarkup(r)}</div></div><div><small>Purpose</small><strong>${escapeHtml(r.purpose||'Not stated')}</strong></div><div><small>Date needed by requester</small><strong>${dayLabel(r.deadline)}</strong></div><div><small>Why this date?</small><p>${deadlineReason}</p></div><div><small>Current status</small>${statusBadge(status)}</div><div><small>Priority score</small><strong>${Number(r.priority_score).toFixed(2)} / 100</strong></div></div>
      ${r.declined_reason?`<p class="decision-alert"><strong>Declined:</strong> ${escapeHtml(r.declined_reason)}</p>`:''}
      ${r.cancelled_reason?`<p class="decision-alert"><strong>Cancelled:</strong> ${escapeHtml(r.cancelled_reason)}</p>`:''}
      ${r.pickup_at?`<div class="pickup-summary"><strong>${icon('calendar')} Pickup: ${datetime(r.pickup_at)}</strong><p>${escapeHtml(r.pickup_note||'No additional instructions')}</p></div>`:''}
    </div><div class="review-actions">
      ${canDecide?`<h3>Approve or decline</h3><p class="panel-subtitle">Approve to begin preparing the documents. When declining, a clear reason is required and will be visible to the requester.</p><label class="form-label">Decline reason<textarea id="reviewDeclineReason" rows="3" minlength="10" maxlength="500" placeholder="Explain why the request cannot be accepted."></textarea></label><div class="review-button-pair">${button('Approve request','approve-request','primary',`data-id="${escapeHtml(r.public_id)}"`)}${button('Decline request','decline-request','outline',`data-id="${escapeHtml(r.public_id)}"`)}</div>`:''}
      ${canSchedule?`<h3>Schedule document collection</h3><p class="panel-subtitle">The registrar chooses when documents can be picked up. The requested Date Needed is a preference, not a guaranteed pickup date.</p><label class="form-label">Scheduled pickup date & time<input id="reviewPickupAt" type="datetime-local" required value="${localValue}"></label><label class="form-label">Pickup instructions (optional)<textarea id="reviewPickupNote" rows="2" maxlength="500" placeholder="e.g. Bring a valid ID. Claim at Registrar Window 2."></textarea></label>${button('Confirm pickup schedule','schedule-pickup','primary',`data-id="${escapeHtml(r.public_id)}"`)}`:''}
      ${canClaim?`<h3>Confirm actual collection</h3><p class="panel-subtitle">Pickup is scheduled for <strong>${r.pickup_at?datetime(r.pickup_at):'not recorded (legacy)'}</strong>. Only confirm after the requester has actually received every document.</p>${button('Mark as Claimed','mark-claimed','primary',`data-id="${escapeHtml(r.public_id)}"`)}`:''}
      ${closed?`<div class="tip-box">${icon('shield')}<span>This request is finalized. Its history is preserved in SQLite.</span></div>`:''}
    </div></div>`;
}
function renderStaffRows() {
  const container=$('#staffTable'); if(!container) return;
  const data=state.adminData;
  let rows=state.staffTab==='priority'?data.priority:state.staffTab==='arrival'
    ? data.arrivals.map(id=>data.requests.find(x=>x.public_id===id)).filter(Boolean) : data.requests;
  const term=state.search.toLowerCase();
  rows=rows.filter(r=>(state.filter==='All'||effectiveStatus(r)===state.filter) &&
    (state.requesterFilter==='All'||requesterLabel(r)===state.requesterFilter) &&
    (!term||[r.public_id,r.requester_name,...documentList(r),r.category,requesterLabel(r)].some(x=>String(x).toLowerCase().includes(term))));
  $('#recordCount').textContent=`${rows.length} record${rows.length===1?'':'s'}`;
  const rank=state.staffTab==='priority', arrival=state.staffTab==='arrival';
  const header=rank?'Rank':arrival?'Arrival':'Request ID';
  container.innerHTML=rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>${header}</th>${state.staffTab!=='all'?'<th>Request ID</th>':''}<th>Requester / Documents</th><th>Type</th><th>Date Needed / Reason</th><th>Pickup Schedule</th><th>Score</th><th>Status</th><th>Action</th></tr></thead><tbody>${rows.map((r,i)=>`<tr><td class="main-cell">${state.staffTab==='all'?escapeHtml(r.public_id):`<span class="rank-number">${arrival?r.arrival_number:i+1}</span>`}</td>${state.staffTab!=='all'?`<td class="main-cell">${escapeHtml(r.public_id)}</td>`:''}<td class="main-cell">${escapeHtml(r.requester_name)}<div class="doc-chip-list">${documentsMarkup(r)}</div></td><td><span class="requester-pill">${escapeHtml(requesterLabel(r))}</span></td><td>${dayLabel(r.deadline)}<span class="sub-cell wrap-cell">${escapeHtml(r.date_reason||'Legacy: no reason')}</span></td><td>${r.pickup_at?datetime(r.pickup_at):'<span class="muted-final">Not scheduled</span>'}</td><td class="score-cell">${effectiveStatus(r)==='Pending'?Number(r.priority_score).toFixed(2):'—'}</td><td>${statusBadge(effectiveStatus(r))}</td><td>${nextStatusOptions(r)}</td></tr>`).join('')}</tbody></table></div>`:empty('No matching requests','Try different filters. New Student and Alumni requests appear here after submission.');
}
function claimedPage() {
  const stats=state.adminData.stats;
  return pageHeading('Claimed / Released','Confirmed pickups by students and alumni, recorded by authorized registrar staff.',button(`${icon('refresh')} Refresh`,'refresh','outline'))+`<section class="stat-grid claim-stats">${stat('Claimed / Released',stats.claimed,'Pickup confirmed and recorded','check')}${stat('Approved for Pickup',stats.ready_to_claim,'Waiting for collection','document')}${stat('Student Requests',stats.students,'Total submitted by students','user')}${stat('Alumni Requests',stats.alumni,'Total submitted by alumni','user')}</section><div class="claim-info">${icon('info')}<span>A processed document is <strong>not</strong> automatically claimed. Open <strong>Document Request</strong>, click <strong>Approve for Release</strong> first, then confirm the handover with <strong>Mark as Claimed</strong>.</span></div><section class="panel"><div class="panel-header"><div><h2>Received document log</h2><p>Request ID, requester, document, pickup date/time and confirming staff</p></div><span class="badge status-info" id="claimedCount">${stats.claimed} records</span></div><div class="claim-search"><input class="filter-input" id="claimSearch" placeholder="Search reference ID, student/alumni, document…" value="${escapeHtml(state.claimSearch)}" aria-label="Search claimed requests"></div><div id="claimedTable"></div></section>`;
}
function renderClaimedRows() {
  const target=$('#claimedTable'); if(!target) return;
  const term=state.claimSearch.toLowerCase();
  const rows=state.adminData.claimed.filter(r=> !term || [r.public_id,r.requester_name,r.document_type,r.requester_type,r.claimed_by].some(v=>String(v||'').toLowerCase().includes(term)));
  $('#claimedCount').textContent=`${rows.length} record${rows.length===1?'':'s'}`;
  target.innerHTML=rows.length?`<div class="table-wrap"><table class="data-table"><thead><tr><th>Request ID</th><th>Received by (requester)</th><th>Type</th><th>Document</th><th>Claimed / Released at</th><th>Confirmed by</th><th>Status</th></tr></thead><tbody>${rows.map(r=>`<tr><td class="main-cell">${escapeHtml(r.public_id)}</td><td class="main-cell">${escapeHtml(r.requester_name)}</td><td><span class="requester-pill">${escapeHtml(requesterLabel(r))}</span></td><td>${escapeHtml(r.document_type)}</td><td>${datetime(r.claimed_at)}</td><td>${escapeHtml(r.claimed_by||'Registrar staff')}</td><td>${statusBadge('Claimed')}</td></tr>`).join('')}</tbody></table></div>`:empty('No claimed requests yet','Once a document is marked Ready for Release and handed to its requester, the registrar can confirm it as Claimed.');
}
function notificationsPage() {
  if (isStaff()) {
    return pageHeading('Notifications','All in-app request activity and registrar updates.',button(`${icon('check')} Mark all as read`,'mark-read','outline',(state.unread||0)?'':'disabled'))+`<section class="panel pad"><div class="panel-header" style="padding:0 0 5px"><div><h2>Activity inbox</h2><p>${state.unread||0} unread updates • ${state.notifications.length} recent entries</p></div></div>${state.notifications.length?`<div class="activity-feed">${state.notifications.map(n=>`<div class="feed-entry ${n.is_read?'':'unread'}"><div class="feed-icon">${icon('bell')}</div><div class="feed-body"><strong>${escapeHtml(n.title)}</strong><p>${escapeHtml(n.message)}</p><small>${datetime(n.created_at)}</small></div>${n.is_read?'':'<span class="unread-dot" aria-label="Unread"></span>'}</div>`).join('')}</div>`:empty('Your inbox is clear','New submissions and processing updates will appear here.')}</section>`;
  }
  if (isRequester()) return pageHeading(isAlumni()?'Alumni notifications':'Student notifications','Status updates for your document requests.')+`<section class="panel pad"><div class="panel-header"><div><h2>My updates</h2><p>In-app registrar activity (not SMS or email)</p></div></div>${state.notifications.length?`<div class="activity-feed">${state.notifications.map(n=>`<div class="feed-entry"><div class="feed-icon">${icon('bell')}</div><div class="feed-body"><strong>${escapeHtml(n.public_id)} · ${escapeHtml(n.status)}</strong><p>${escapeHtml(n.message)}</p><small>${datetime(n.created_at)}</small></div></div>`).join('')}</div>`:empty('No updates yet','Updates will appear when your requests change status.')}</section>`;
  const updates=state.publicTracked.flatMap(track=>track.events.map(event=>({id:track.request.id,event}))).sort((a,b)=>b.event.created_at.localeCompare(a.event.created_at));
  return pageHeading('Notifications','Status activity for reference numbers saved on this browser.')+`<section class="panel pad"><div class="panel-header" style="padding:0 0 8px"><div><h2>My request updates</h2><p>These are in-app status records—not email, SMS, or push notifications.</p></div></div>${updates.length?`<div class="activity-feed">${updates.map(item=>`<div class="feed-entry"><div class="feed-icon">${icon('document')}</div><div class="feed-body"><strong>${escapeHtml(item.id)} · ${escapeHtml(item.event.status)}</strong><p>${escapeHtml(item.event.message)}</p><small>${datetime(item.event.created_at)}</small></div></div>`).join('')}</div>`:empty('No request activity yet','Once you submit or track a request on this device, its updates will appear here.',button('Create a request','go-requests','light'))}</section>`;
}
function profilePage() {
  if (isStaff()) return pageHeading('My profile','Manage your registrar account and access settings.')+`<div class="profile-grid"><section class="panel profile-card"><div class="profile-banner"><div class="profile-avatar">${escapeHtml(state.user.display_name[0])}</div><div><h2>${escapeHtml(state.user.display_name)}</h2><p>Registrar administrator</p></div></div><div class="detail-row"><span>Username</span><strong>${escapeHtml(state.user.username)}</strong></div><div class="detail-row"><span>Account role</span><strong>Registrar Staff</strong></div><div class="detail-row"><span>Access</span><strong>Request processing · Claimed / Released log</strong></div><div class="detail-row"><span>Environment</span><strong>Academic demonstration</strong></div>${button(`${icon('log')} Sign out`,'logout','outline')}</section><section class="panel profile-card"><h2 style="font-size:17px;margin-bottom:8px">Security settings</h2><p class="panel-subtitle">Change the demonstration password before using the prototype on a shared computer or network.</p><form id="passwordForm" class="form-stack" style="margin-top:23px"><label class="form-label">Current password<input name="current_password" autocomplete="current-password" type="password" required></label><label class="form-label">New password<input name="new_password" autocomplete="new-password" type="password" minlength="10" required><small>At least 10 characters with uppercase, lowercase, a number, and a symbol.</small></label><button type="submit" class="button primary">Update password ${icon('arrow')}</button></form><div class="tip-box">${icon('shield')}<span>Only authorized registrar staff can view requester names, priority rankings, and processing controls. Guests can track a minimal status using a request ID.</span></div></section></div>`;
  if (isRequester()) return pageHeading(isAlumni()?'Alumni profile':'Student profile',isAlumni()?'Verified alumni account information.':'Verified student account information.')+`<div class="profile-grid"><section class="panel profile-card"><div class="profile-banner"><div class="profile-avatar">${escapeHtml(state.user.display_name[0])}</div><div><h2>${escapeHtml(state.user.display_name)}</h2><p>${escapeHtml(state.user.role)} account</p></div></div><div class="detail-row"><span>${isAlumni()?'Former student number':'Student number'}</span><strong>${escapeHtml(state.user.student_number)}</strong></div><div class="detail-row"><span>Email (verified)</span><strong>${escapeHtml(state.user.email)}</strong></div><div class="detail-row"><span>Submitted requests</span><strong>${state.myRequests.length}</strong></div>${button(`${icon('log')} Log out`,'logout','outline')}</section><section class="panel profile-card"><p class="eyebrow">DOCUMENT SERVICES</p><h2 style="font-size:19px">Your document history</h2><p class="panel-subtitle">Follow requests from Pending to Ready for Release and Claimed. Only the registrar can update processing or confirm physical pickup.</p>${button(`${icon('document')} Submit a request`,'go-requests','primary')}</section></div>`;
  return pageHeading('Profile & access','Student / alumni portal and registrar staff access.')+`<div class="profile-grid"><section class="panel profile-card"><div class="profile-banner"><div class="profile-avatar">G</div><div><h2>Guest access</h2><p>Student and alumni portal</p></div></div><p class="panel-subtitle">Register for a Student or Alumni account to submit new documents and view your private requests. Reference-ID tracking stays available for older transactions.</p><div class="detail-row"><span>Access type</span><strong>Public (limited)</strong></div><div class="detail-row"><span>My tracked requests</span><strong>${state.publicTracked.length}</strong></div><div class="detail-row"><span>Current environment</span><strong>Simulation only</strong></div>${button(`${icon('plus')} Create account`,'register','primary')}</section><section class="panel profile-card"><p class="eyebrow">STAFF AREA</p><h2 style="font-size:19px;margin-bottom:9px">Registrar access</h2><p class="panel-subtitle">Authorized staff can manage the priority queue, process the next request, and change request statuses after signing in.</p><div class="tip-box">${icon('shield')}<span>Protected dashboard, secure password hashing, authenticated sessions, and server-side permission checks.</span></div>${button(`${icon('log')} Sign in`,'login','primary')}<div class="divider"></div><h3 class="subheading">Need help?</h3><p class="panel-subtitle">Use the question-mark icon in the upper-right corner to open “How the system works”.</p>${button('Open system guide','help','outline')}</section></div>`;
}
const helpGuides={
  student:[['Create your account','Click Register on the login page, choose Student or Alumni, and enter your name, student or former student number, email and password.'],['Verify your email','Open the email verification link within 24 hours. If it expires, use Resend verification email from the login page.'],['Sign in and request','Sign in to your own Student or Alumni portal. Open Document Request → New Request; select the document and purpose, then choose Date Needed directly in the form using the interactive calendar.'],['Save your reference ID','The system automatically gives each submission a unique request ID.'],['Follow status','Dashboard and Notifications show your own requests and updates. Registrar staff confirm physical pickup as Claimed.']],
  staff:[['Sign in as registrar staff','Click Sign in in the top-right corner or the registrar login shortcut in the sidebar.'],['Open the queue dashboard','Review live counts, highest-priority pending requests, and registrar activity.'],['Manage student & alumni requests','Open Document Request to see all students and alumni, filter by requester type, and update request status.'],['Approve then release','Review each request and its Date Needed explanation. Approve or decline with a reason; for approved requests, schedule the pickup date/time. Confirm Claimed only after handover.'],['Review claimed records','Select Claimed / Released in the staff sidebar to see confirmed document handovers.'],['Understand priority selection','The demonstration score is PS = 0.50U + 0.30W + 0.20C. U is deadline urgency, W waiting time, and C requester category (each 0–100). Scores are recalculated before ranking or processing.'],['Review updates','Use Notifications for in-app activity. Profile includes change password and sign out.']]
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
  if (isDetailView(state.view) && !isRequester()) state.publicTracked=[data,...state.publicTracked.filter(item=>item.request.id!==value)];
  toast(`${value} is currently ${data.request.status}.`);
}
async function submitRequest(form) {
  if(state.busy)return;
  const formData=new FormData(form);
  const data=Object.fromEntries(formData);
  const documentTypes=formData.getAll('document_types').map(String);
  if (!documentTypes.length || documentTypes.length>5) {toast('Select one to five documents.',true);return;}
  data.document_types=documentTypes;
  data.document_type=documentTypes[0];
  if (isRequester() && (!/^\d{4}-\d{2}-\d{2}$/.test(data.deadline||'') || data.deadline < state.today)) {
    toast('Choose a valid Date Needed in your document request form before submitting.',true);
    return;
  }
  state.busy=true;
  const submit=$('#submitRequestButton'); if(submit)submit.disabled=true;
  try {
    const response=await api('/api/requests',{method:'POST',body:data});
    const id=response.request.id;
    state.lastSuccessId=id;
    saveTracked(id);
    state.requestDate=''; state.requestDraft=null; state.pickerOpen=false;
    if (isRequester()) {await loadRequester();state.requestMode='mine';}
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
  if (action==='go-requests' || action==='my-requests') {state.requestMode='mine';return navigate('requests');}
  if (action==='new-request') {state.requestMode='new';state.pickerOpen=false;return navigate('requests');}
  if(action==='toggle-needed-picker') {
    if(!isRequester())throw Error('Student or Alumni account required.');
    state.pickerOpen=!state.pickerOpen;
    if(state.pickerOpen){state.selectedCalendarDay=state.requestDate||state.today;state.calendarAnchor=state.selectedCalendarDay;}
    redrawNeededPicker(); return;
  }
  if(action==='apply-needed-date') return applyNeededDate();
  if (action==='register-student') {state.registerRole='Student';return navigate('register');}
  if (action==='register-alumni') {state.registerRole='Alumni';return navigate('register');}
  if (action==='go-claimed') return navigate('claimed');
  if (action==='go-dashboard') return navigate('dashboard');
  if (action==='open-dashboard-card') {const detail=element.dataset.detail;if(!detailViews.includes(detail)) throw Error('Unknown dashboard section.');return navigate(detail);}
  if (action==='show-tracked-detail') {const id=element.dataset.id;const found=(state.publicTracked||[]).find(item=>item.request.id===id);if(!found)throw Error('The request is not currently available. Refresh and try again.');const node=$('#inlineTrackResult');if(node){node.innerHTML=renderTrackCard(found);node.scrollIntoView({behavior:'smooth',block:'nearest'});}return;}
  if (action==='profile') return navigate('profile');
  if (action==='login') {state.authTab=isRequester()?state.user.role:(state.registerRole||'Student');return navigate('login');}
  if (action==='register') return navigate('register');
  if (action==='verify-email') return navigate('verify-email');
  if (action==='switch-requester') {state.authTab='Student';return render();}
  if (action==='theme') return setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');
  if (action==='install') return installApp();
  if (action==='toggle-password') {const field=$('#password');if(field){field.type=field.type==='password'?'text':'password';element.setAttribute('aria-label',field.type==='password'?'Show password':'Hide password');}return;}
  if (action==='help') {state.helpTab='student';renderHelp();return openModal('helpModal');}
  if (action==='refresh') return refreshCurrent();
  if (action==='focus-track') { navigate('dashboard'); setTimeout(()=>$('#homeTrackInput')?.focus(),150);return; }
  if (action==='quick-track') { const id=element.dataset.id;await track(id);navigate('requests');return; }
  if (action==='copy-success') { try { await navigator.clipboard.writeText(state.lastSuccessId||'');toast('Reference ID copied.'); } catch {toast('Please copy the reference ID manually.',true);} return; }
  if (action==='track-success' && isRequester()) {closeModal('successModal');state.requestMode='mine';navigate('requests');return;}
  if (action==='track-success') {closeModal('successModal');navigate('dashboard');setTimeout(()=>{const field=$('#homeTrackInput');if(field){field.value=state.lastSuccessId;field.closest('form').requestSubmit();}},200);return;}
  if (action==='logout') {await api('/api/auth/logout',{method:'POST'});state.user=null;state.adminData=null;state.requestMode='mine';state.requestDate='';state.requestDraft=null;state.pickerOpen=false;state.myRequests=[];state.notifications=[];state.unread=0;state.authTab='Student';toast('You have signed out safely.');return navigate('login');}
  if(action==='review-request') {
    if(!isStaff())throw Error('Registrar access required.');
    const id=element.dataset.id;
    const record=state.adminData?.requests?.find(r=>r.public_id===id);
    if(!record)throw Error('Request not found. Refresh and try again.');
    state.reviewId=id;
    $('#reviewContent').innerHTML=reviewRequestHtml(record);
    return openModal('reviewModal');
  }
  if(action==='open-cancel') {
    if(!isRequester())throw Error('Sign in with your Student/Alumni account.');
    const record=state.myRequests?.find(r=>r.public_id===element.dataset.id);
    if(!record||!canCancel(record))throw Error('This request can no longer be cancelled.');
    state.cancelId=record.public_id;
    $('#cancelRequestId').textContent=record.public_id;
    $('#cancelRequestReason').value='';
    return openModal('cancelModal');
  }
  if(action==='approve-request'||action==='decline-request') {
    if(!isStaff())throw Error('Registrar access required.');
    const id=element.dataset.id;
    const decision=action==='approve-request'?'approve':'decline';
    const reason=$('#reviewDeclineReason')?.value?.trim()||'';
    if(decision==='decline'&&reason.length<10)throw Error('Provide a decline reason of at least ten characters.');
    if(!confirm(decision==='approve'?`Approve ${id} for preparation?`:`Decline ${id} and notify the requester of the reason?`))return;
    const response=await api(`/api/admin/requests/${encodeURIComponent(id)}/decision`,{method:'POST',body:{decision,reason:decision==='decline'?reason:null}});
    closeModal('reviewModal');toast(response.message);return refreshCurrent();
  }
  if(action==='schedule-pickup') {
    if(!isStaff())throw Error('Registrar access required.');
    const id=element.dataset.id;
    const pickup_at=$('#reviewPickupAt')?.value;
    const note=$('#reviewPickupNote')?.value||'';
    if(!pickup_at)throw Error('Choose a pickup date and time.');
    if(!confirm(`Confirm ${id} pickup schedule for ${pickup_at}?`))return;
    const response=await api(`/api/admin/requests/${encodeURIComponent(id)}/schedule`,{method:'POST',body:{pickup_at,note}});
    closeModal('reviewModal');toast(response.message);return refreshCurrent();
  }
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
  if (action==='approve-release') {
    if(!isStaff()) throw Error('Registrar access required.');
    const id=element.dataset.id;
    if(!confirm(`Approve ${id} for release? The requester will see that the document is ready for pickup.`))return;
    const response=await api(`/api/admin/requests/${encodeURIComponent(id)}/approve`,{method:'POST'});
    toast(response.message);return refreshCurrent();
  }
  if (action==='mark-claimed') {
    if(!isStaff()) throw Error('Registrar access required.');
    const id=element.dataset.id;
    if(!confirm(`Confirm that the student or alumni actually received the document for ${id}? This pickup record cannot be undone.`)) return;
    const response=await api(`/api/admin/requests/${encodeURIComponent(id)}/claim`,{method:'POST'});
    closeModal('reviewModal');toast(response.message);return refreshCurrent();
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
  const registrationRole=event.target.closest('[data-register-role]');
  if(registrationRole){switchRegistrationRole(registrationRole.dataset.registerRole);return;}
  const authTab=event.target.closest('[data-auth-tab]');
  if(authTab){state.authTab=authTab.dataset.authTab;render();return;}
  const neededNav=event.target.closest('[data-needed-nav]');
  if(neededNav){moveNeededMonth(neededNav.dataset.neededNav);return;}
  const neededDay=event.target.closest('[data-needed-day]');
  if(neededDay){chooseNeededDate(neededDay.dataset.neededDay);return;}
  const staffTab=event.target.closest('[data-staff-tab]');
  if(staffTab){state.staffTab=staffTab.dataset.staffTab;$$('[data-staff-tab]').forEach(b=>b.classList.toggle('active',b===staffTab));$('#tableHeading').textContent={all:'All document requests',priority:'Priority ranking',arrival:'FIFO arrival history'}[state.staffTab];$('#tableDescription').textContent={all:'Review the details and change the status of eligible requests.',priority:'Highest score first, with deadline and arrival tie-breakers.',arrival:'Original arrival order, including completed requests.'}[state.staffTab];renderStaffRows();return;}
  const action=event.target.closest('[data-action]');
  if(action){try{await executeAction(action.dataset.action,action);}catch(error){toast(error.message,true);}return;}
});
document.addEventListener('submit',async event=>{
  const form=event.target;
  if(form.id==='cancelRequestForm'){
    event.preventDefault();
    if(!isRequester()||!state.cancelId)return;
    const submit=$('#confirmCancelButton');if(submit)submit.disabled=true;
    try {const response=await api(`/api/my/requests/${encodeURIComponent(state.cancelId)}/cancel`,{method:'POST',body:{reason:$('#cancelRequestReason')?.value||''}});
      closeModal('cancelModal');state.cancelId=null;toast(response.message);return refreshCurrent();}
    catch(error){toast(error.message,true);}finally{if(submit)submit.disabled=false;}return;
  }
  if(form.id==='requestForm'){event.preventDefault();await submitRequest(form);return;}
  if(form.dataset.form==='track'){event.preventDefault();try{await track(new FormData(form).get('request_id')||'');}catch(error){toast(error.message,true);}return;}
  if(form.id==='registerForm'){
    event.preventDefault();const submit=$('#registerSubmit');submit.disabled=true;
    try {const response=await api('/api/auth/register',{method:'POST',body:Object.fromEntries(new FormData(form))});state.verificationEmail=response.user.email;state.registerRole=response.user.role;toast('Check your inbox for the verification link.');navigate('verify-email');}
    catch(error){const note=$('#registerError');if(note){note.textContent=error.message;note.classList.remove('hidden');}toast(error.message,true);}finally{submit.disabled=false;}return;
  }
  if(form.id==='verifyEmailForm'){
    event.preventDefault();const submit=$('#verifySubmit');submit.disabled=true;
    const token=new URLSearchParams(location.hash.split('?')[1]||'').get('token')||'';
    try {const response=await api('/api/auth/verify-email',{method:'POST',body:{token}});
      toast(response.message);state.authTab=state.registerRole||'Student';history.replaceState(null,'',location.pathname+location.search+'#login');await render();}
    catch(error){const note=$('#verificationError');if(note){note.textContent=error.message;note.classList.remove('hidden');}toast(error.message,true);}
    finally {if(submit.isConnected)submit.disabled=false;}return;
  }
  if(form.id==='resendVerificationForm'){
    event.preventDefault();const submit=$('#resendSubmit');submit.disabled=true;
    try {const response=await api('/api/auth/resend-verification',{method:'POST',body:Object.fromEntries(new FormData(form))});toast(response.message);}
    catch(error){const note=$('#resendError');if(note){note.textContent=error.message;note.classList.remove('hidden');}toast(error.message,true);}
    finally {submit.disabled=false;}return;
  }
  if(form.id==='requesterLoginForm'){
    event.preventDefault();const submit=$('#requesterLoginSubmit');submit.disabled=true;
    try {const response=await api('/api/auth/requester-login',{method:'POST',body:Object.fromEntries(new FormData(form))});state.user=response.user;state.requestMode='mine';state.requestDate='';state.requestDraft=null;state.pickerOpen=false;state.myRequests=[];toast('Signed in successfully.');navigate('dashboard');}
    catch(error){const note=$('#authError');if(note){note.textContent=error.message;note.classList.remove('hidden');}toast(error.message,true);}finally{submit.disabled=false;}return;
  }
  if(form.id==='loginForm'){
    event.preventDefault();const button=$('#loginSubmit');button.disabled=true;
    try{
      const response=await api('/api/auth/login',{method:'POST',body:Object.fromEntries(new FormData(form))});
      state.user=response.user;state.adminData=null;form.reset();toast('Welcome to the registrar workspace.');navigate('dashboard');
    }catch(error){const notice=$('#authError');if(notice){notice.textContent=error.message;notice.classList.remove('hidden');}toast(error.message,true);}finally{button.disabled=false;}return;
  }
  if(form.id==='passwordForm'){
    event.preventDefault();const button=$('button[type="submit"]',form);button.disabled=true;
    try{
      const response=await api('/api/admin/change-password',{method:'POST',body:Object.fromEntries(new FormData(form))});
      state.user=null;state.adminData=null;toast(response.message);navigate('login');
    }catch(error){toast(error.message,true);}finally{button.disabled=false;}
  }
});
document.addEventListener('input', event=>{
  if(event.target.id==='staffSearch'){state.search=event.target.value;renderStaffRows();}
  if(event.target.id==='claimSearch'){state.claimSearch=event.target.value;renderClaimedRows();}
});
document.addEventListener('change',event=>{
  if(event.target.id==='staffFilter'){state.filter=event.target.value;renderStaffRows();}
  if(event.target.id==='requesterFilter'){state.requesterFilter=event.target.value;renderStaffRows();}
});
$('#helpButton').addEventListener('click',()=>{state.helpTab='student';renderHelp();openModal('helpModal');});
$('#themeButton').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
$('#menuToggle').addEventListener('click',()=>$('#appShell').classList.toggle('menu-open'));
$('#mobileOverlay').addEventListener('click',()=>$('#appShell').classList.remove('menu-open'));
window.addEventListener('hashchange',render);
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();state.installPrompt=event;updateInstallUI();});
window.addEventListener('appinstalled',()=>{state.isInstalled=true;state.installPrompt=null;updateInstallUI();toast('QueueWise installed successfully.');});
async function start() {
  let storedTheme='light'; try { storedTheme=localStorage.getItem('queuewise_theme')||'light'; } catch {}
  setTheme(storedTheme);
  $('#year').textContent=new Date().getFullYear();
  renderHelp();
  updateInstallUI();
  try{
    const boot=await api('/api/bootstrap');
    state.user=boot.user;state.csrf=boot.csrf_token;state.today=boot.today;
    state.documents=boot.documents;state.categories=boot.categories;
    await render();
  }catch(error){$('#page').innerHTML=empty('Unable to connect',escapeHtml(error.message),button('Retry','refresh','primary'));toast(error.message,true);}
  if('serviceWorker' in navigator){navigator.serviceWorker.register('/sw.js').then(reg=>reg.update()).catch(()=>{toast('Offline PWA support is unavailable in this browser.',true);});}
}
start();
