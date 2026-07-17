"""Admin audit / metrics dashboard HTML (Chart.js)."""


def render_admin_dashboard_page() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Vela Operations</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.8/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:#0F1218; --panel:#171C26; --panel-2:#1D2430; --line:#2A3344;
    --ink:#E8ECF4; --muted:#8B95A8; --faint:#5C667A;
    --accent:#4F7CFF; --good:#3DCF8E; --bad:#F07178; --warn:#E6B450;
    --mono:'IBM Plex Mono', ui-monospace, monospace;
    --sans:'Inter', system-ui, sans-serif;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);font-family:var(--sans)}
  body{min-height:100vh}
  .wrap{max-width:1200px;margin:0 auto;padding:28px 20px 48px}
  header{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;justify-content:space-between;margin-bottom:22px}
  .brand{display:flex;align-items:center;gap:10px}
  .mark{width:18px;height:18px;border-radius:5px;background:var(--accent)}
  h1{font-size:20px;margin:0;font-weight:700;letter-spacing:-0.02em}
  .sub{color:var(--muted);font-size:13px;margin-top:4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
  .controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
  select,button{
    background:var(--panel);border:1px solid var(--line);color:var(--ink);
    border-radius:8px;padding:8px 12px;font-size:13px;font-family:var(--sans)
  }
  button{cursor:pointer;background:var(--accent);border-color:transparent;font-weight:600}
  button:disabled{opacity:.55;cursor:not-allowed}
  button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid rgba(79,124,255,.38);outline-offset:2px}
  button.ghost{background:transparent;border-color:var(--line);color:var(--muted)}
  button.ghost:hover:not(:disabled){color:var(--ink);border-color:var(--faint)}
  button.danger{color:var(--bad);border-color:rgba(240,113,120,.4)}
  button.danger:hover:not(:disabled){color:#FFB4B9;border-color:var(--bad)}
  .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
  .card .label{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);font-family:var(--mono)}
  .card .value{font-size:24px;font-weight:700;margin-top:8px;font-variant-numeric:tabular-nums}
  .card .hint{font-size:12px;color:var(--muted);margin-top:4px}
  .charts{display:grid;grid-template-columns:1.4fr 1fr;gap:12px;margin-bottom:16px}
  .chart-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;position:relative}
  .chart-card h2{font-size:13px;margin:0 0 12px;font-weight:600;color:var(--muted);display:flex;align-items:center;justify-content:space-between;gap:8px}
  .chart-wrap{position:relative;height:240px}
  .split{display:grid;grid-template-columns:1.1fr .9fr;gap:12px}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
  th{color:var(--faint);font-family:var(--mono);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
  td.mono{font-family:var(--mono);font-size:12px}
  td.empty{color:var(--faint);font-style:italic}
  .badge{display:inline-block;padding:2px 7px;border-radius:999px;font-family:var(--mono);font-size:11px}
  .ok{background:rgba(61,207,142,.12);color:var(--good)}
  .err{background:rgba(240,113,120,.14);color:var(--bad)}
  .panel-error{font-size:11.5px;color:var(--bad);font-family:var(--mono);font-weight:600}
  .login-shell{min-height:100vh;display:grid;place-items:center;padding:24px;position:relative;overflow:hidden}
  .login-shell::before,.login-shell::after{content:"";position:absolute;border-radius:999px;filter:blur(2px);pointer-events:none}
  .login-shell::before{width:560px;height:560px;background:radial-gradient(circle,rgba(79,124,255,.18),transparent 67%);top:-270px;left:-150px}
  .login-shell::after{width:460px;height:460px;background:radial-gradient(circle,rgba(61,207,142,.1),transparent 67%);bottom:-260px;right:-130px}
  .login{width:min(100%,440px);position:relative;background:rgba(23,28,38,.93);border:1px solid var(--line);border-radius:18px;padding:30px;box-shadow:0 24px 70px rgba(0,0,0,.35)}
  .login-brand{display:flex;align-items:center;gap:10px;font:600 12px var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
  .login .mark{width:22px;height:22px;box-shadow:0 0 22px rgba(79,124,255,.65)}
  .login h1{font-size:28px;margin:22px 0 8px}
  .login-copy{color:var(--muted);font-size:14px;line-height:1.55;margin:0 0 24px}
  .login .field{margin:16px 0}
  .login label{display:block;font-size:12px;color:var(--muted);margin-bottom:7px;font-weight:600}
  .input-wrap{position:relative}
  .auth-input{width:100%;background:#111620;border:1px solid var(--line);border-radius:9px;color:var(--ink);padding:11px 42px 11px 12px;font:14px var(--sans);transition:border-color .15s,box-shadow .15s}
  .auth-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(79,124,255,.13);outline:none}
  .auth-input[aria-invalid="true"]{border-color:var(--bad);box-shadow:0 0 0 3px rgba(240,113,120,.13)}
  .auth-input::placeholder{color:var(--faint)}
  .password-toggle{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:transparent;border:0;color:var(--muted);padding:6px 8px;font:600 11px var(--mono)}
  .password-toggle:hover{color:var(--ink)}
  .login-submit{width:100%;display:flex;justify-content:center;align-items:center;gap:8px;margin-top:8px;padding:11px 14px;border-radius:9px;font-size:14px}
  .login-submit[disabled]{opacity:.65;cursor:wait}
  .login-foot{display:flex;gap:8px;align-items:flex-start;margin-top:18px;padding-top:16px;border-top:1px solid var(--line);color:var(--faint);font-size:11.5px;line-height:1.45}
  .shield{width:15px;height:15px;flex:0 0 auto;margin-top:1px;color:var(--good)}
  .error{color:#FFB4B9;background:rgba(240,113,120,.1);border:1px solid rgba(240,113,120,.22);border-radius:8px;padding:9px 10px;font-size:12.5px;margin-top:14px;display:none}
  .toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:var(--panel-2);border:1px solid var(--line);color:var(--ink);padding:10px 16px;border-radius:9px;font-size:13px;box-shadow:0 12px 30px rgba(0,0,0,.4);display:none;z-index:50}
  .status-dot{width:8px;height:8px;border-radius:50%;background:var(--good);display:inline-block;flex:0 0 auto}
  .status-dot.off{background:var(--bad)}
  .status-dot.stale{background:var(--warn)}
  .meta{font-family:var(--mono);font-size:11px;color:var(--faint)}
  .connection-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:16px}
  .connection-card h2{margin-bottom:14px}
  .connection-state{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600}
  .connection-detail{margin:10px 0 0;color:var(--muted);font-size:12px;line-height:1.45}
  .connection-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px}
  .connection-metric{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
  .connection-metric span{display:block;color:var(--faint);font:10px var(--mono);letter-spacing:.04em;text-transform:uppercase}
  .connection-metric strong{display:block;margin-top:4px;font-size:15px;font-variant-numeric:tabular-nums}
  .tool-overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 16px}
  .tool-stat{background:var(--panel-2);border:1px solid var(--line);border-radius:9px;padding:10px 12px}
  .tool-stat .tool-stat-label{display:block;color:var(--faint);font:10px var(--mono);letter-spacing:.05em;text-transform:uppercase}
  .tool-stat strong{display:block;margin-top:5px;font-size:16px;font-variant-numeric:tabular-nums}
  .operations-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:12px;align-items:start}
  .operations-card{min-width:0}
  .operations-card.full-row{grid-column:1 / -1}
  .operations-card h2{margin-bottom:14px}
  .operations-card.failure-block h2{color:#FFB4B9}
  .operations-table{overflow:auto;max-height:280px}
  .sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
  @media (max-width:960px){
    .grid{grid-template-columns:repeat(2,1fr)}
    .charts,.split,.connection-grid,.operations-grid{grid-template-columns:1fr}
  }
  @media (max-width:540px){.tool-overview,.connection-metrics{grid-template-columns:1fr}}
  @media (prefers-reduced-motion:reduce){
    *{animation-duration:.001ms !important;transition-duration:.001ms !important}
  }
</style>
</head>
<body>
<div id="loginView" class="login-shell">
  <main class="login" aria-labelledby="loginTitle">
    <div class="login-brand"><span class="mark"></span><span>Vela</span></div>
    <h1 id="loginTitle">Operations</h1>
    <p class="login-copy">Review request activity, latency, and recent failures for this device.</p>
    <form id="loginForm" novalidate>
      <div class="field">
        <label for="user">Username</label>
        <div class="input-wrap"><input class="auth-input" id="user" type="text" autocomplete="username" placeholder="Your Vela username" required autofocus></div>
      </div>
      <div class="field">
        <label for="pass">Password</label>
        <div class="input-wrap">
          <input class="auth-input" id="pass" type="password" autocomplete="current-password" placeholder="Your Vela password" required>
          <button class="password-toggle" id="passwordToggle" type="button" aria-controls="pass" aria-pressed="false">SHOW</button>
        </div>
      </div>
      <button class="login-submit" id="loginBtn" type="submit"><span id="loginLabel">Open dashboard</span><span aria-hidden="true">→</span></button>
    </form>
    <div class="error" id="loginError" role="alert"></div>
    <div class="login-foot">
      <svg class="shield" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M8 1.5 13 3.4v3.8c0 3-2 5.8-5 7.3-3-1.5-5-4.3-5-7.3V3.4L8 1.5Z" stroke="currentColor" stroke-width="1.25"/><path d="m5.7 7.7 1.5 1.5 3.2-3.2" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>Use the same credentials as the local Vela API. Your session is stored only in this browser.</span>
    </div>
  </main>
</div>

<div id="dashView" class="wrap" style="display:none">
  <header>
    <div>
      <div class="brand"><span class="mark"></span><h1>Vela Operations</h1></div>
      <div class="sub"><span class="status-dot" id="liveDot" role="img" aria-label="Live"></span><span id="liveLabel">Live</span> request audit &amp; latency · <span class="meta" id="updatedAt">—</span></div>
    </div>
    <div class="controls">
      <select id="windowSelect" aria-label="Time window">
        <option value="15">Last 15 min</option>
        <option value="60" selected>Last 60 min</option>
        <option value="360">Last 6 h</option>
        <option value="1440">Last 24 h</option>
        <option value="10080">Last 7 days</option>
        <option value="20160">Last 14 days</option>
        <option value="43200">Last 30 days</option>
      </select>
      <button class="ghost" type="button" id="refreshBtn">Refresh</button>
      <button class="ghost danger" type="button" id="clearHistoryBtn">Clear history</button>
      <button class="ghost" type="button" id="logoutBtn">Log out</button>
    </div>
  </header>

  <div class="grid">
    <div class="card"><div class="label">Requests</div><div class="value" id="statTotal">0</div><div class="hint" id="statWindow">window</div></div>
    <div class="card"><div class="label">Error rate</div><div class="value" id="statErrors">0%</div><div class="hint" id="statErrorCount">0 errors</div></div>
    <div class="card"><div class="label">Median</div><div class="value" id="statMedian">0 ms</div><div class="hint">latency</div></div>
    <div class="card"><div class="label">p95</div><div class="value" id="statP95">0 ms</div><div class="hint">latency</div></div>
  </div>

  <div class="connection-grid" aria-label="Backend and relay health">
    <section class="chart-card connection-card" aria-labelledby="backendStatusHeading">
      <h2 id="backendStatusHeading"><span>Backend status</span><span class="meta" id="backendServerTime">Checking…</span></h2>
      <div class="connection-state"><span class="status-dot" id="backendStatusDot"></span><span id="backendStatus">Online</span></div>
      <p class="connection-detail">The local FastAPI service is responding to this dashboard.</p>
    </section>
    <section class="chart-card connection-card" aria-labelledby="relayStatusHeading">
      <h2 id="relayStatusHeading"><span>Relay connection</span><span class="meta" id="relayStatus">Checking…</span></h2>
      <div class="connection-state"><span class="status-dot stale" id="relayStatusDot"></span><span id="relayState">Checking relay tunnel</span></div>
      <div class="connection-metrics">
        <div class="connection-metric"><span>Broken</span><strong id="relayDisconnects">0</strong></div>
        <div class="connection-metric"><span>Reconnected</span><strong id="relayReconnects">0</strong></div>
        <div class="connection-metric"><span>Connected for</span><strong id="relayUptime">—</strong></div>
      </div>
      <p class="connection-detail" id="relayDetail">Waiting for relay status.</p>
    </section>
  </div>

  <div class="charts">
    <div class="chart-card"><h2><span>Requests / minute</span><span class="panel-error" id="rateChartError"></span></h2><div class="chart-wrap"><canvas id="rateChart"></canvas></div></div>
    <div class="chart-card"><h2><span>Latency (median / p95)</span></h2><div class="chart-wrap"><canvas id="latChart"></canvas></div></div>
  </div>

  <div class="split">
    <div class="chart-card">
      <h2><span>By endpoint</span></h2>
      <div style="overflow:auto;max-height:360px">
        <table>
          <caption class="sr-only">Requests broken down by endpoint</caption>
          <thead><tr><th>Endpoint</th><th>Count</th><th>Err%</th><th>Med</th><th>p95</th></tr></thead>
          <tbody id="endpointBody"></tbody>
        </table>
      </div>
    </div>
    <div class="chart-card">
      <h2><span>Recent activity</span><span class="panel-error" id="eventsError"></span></h2>
      <div style="overflow:auto;max-height:360px">
        <table>
          <caption class="sr-only">Most recent requests</caption>
          <thead><tr><th>When</th><th>Call</th><th>Status</th><th>ms</th></tr></thead>
          <tbody id="eventsBody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="operations-grid" aria-label="Failures and assistant tools">
    <section class="chart-card operations-card full-row" aria-labelledby="requestErrorsHeading">
      <h2 id="requestErrorsHeading"><span>Recent request errors</span></h2>
      <div class="operations-table">
        <table>
          <caption class="sr-only">Most recent request errors</caption>
          <thead><tr><th>When</th><th>Request ID</th><th>Call</th><th>Status</th><th>ms</th></tr></thead>
          <tbody id="errorsBody"></tbody>
        </table>
      </div>
    </section>

    <section class="chart-card operations-card" aria-labelledby="toolHealthHeading">
      <h2 id="toolHealthHeading"><span>Assistant tool health</span><span class="meta" id="assistantToolSummary">No tool calls in this window</span></h2>
      <div class="tool-overview" aria-label="Assistant tool overview">
        <div class="tool-stat"><span class="tool-stat-label">Tool calls</span><strong id="toolCallCount">0</strong></div>
        <div class="tool-stat"><span class="tool-stat-label">Failed</span><strong id="toolFailureCount">0</strong></div>
        <div class="tool-stat"><span class="tool-stat-label">Success rate</span><strong id="toolSuccessRate">—</strong></div>
      </div>
      <div class="operations-table">
        <table>
          <caption class="sr-only">Assistant tool usage and latency by tool</caption>
          <thead><tr><th>Tool</th><th>Calls</th><th>Failure rate</th><th>Typical</th><th>Slow 5%</th></tr></thead>
          <tbody id="toolsBody"></tbody>
        </table>
      </div>
    </section>

    <section class="chart-card operations-card" aria-labelledby="toolActivityHeading">
      <h2 id="toolActivityHeading"><span>Latest tool executions</span></h2>
      <div class="operations-table">
        <table>
          <caption class="sr-only">Latest assistant tool executions</caption>
          <thead><tr><th>When</th><th>Tool</th><th>Outcome</th><th>Duration</th></tr></thead>
          <tbody id="toolEventsBody"></tbody>
        </table>
      </div>
    </section>

    <section class="chart-card operations-card full-row failure-block" id="toolFailurePanel" aria-labelledby="toolFailureHeading">
      <h2 id="toolFailureHeading"><span>Recent tool failures</span></h2>
      <div class="operations-table">
        <table>
          <caption class="sr-only">Recent assistant tool failures</caption>
          <thead><tr><th>Tool</th><th>Request ID</th><th>Error</th></tr></thead>
          <tbody id="toolErrorsBody"></tbody>
        </table>
      </div>
    </section>
  </div>
</div>

<div class="toast" id="toast" role="status" aria-live="polite"></div>
<div class="sr-only" id="liveRegion" aria-live="polite"></div>

<script>
(() => {
  const TOKEN_KEY = 'vela_admin_token';
  const WINDOW_KEY = 'vela_admin_window';
  const POLL_MS = 5000;
  const MAX_BACKOFF_MS = 60000;

  let rateChart, latChart, pollTimer, backoffMs = POLL_MS;
  let inFlightController = null;
  let requestSeq = 0; // guards against out-of-order responses

  function token(){ return localStorage.getItem(TOKEN_KEY) || ''; }
  function setToken(t){ localStorage.setItem(TOKEN_KEY, t); }
  function clearToken(){ localStorage.removeItem(TOKEN_KEY); }

  // --- small utilities -----------------------------------------------

  function esc(value){
    // Prevent stored/reflected XSS: anything server-supplied (paths,
    // error messages, endpoint names, tool names) is untrusted and must
    // never be interpolated into innerHTML unescaped.
    const s = value === null || value === undefined ? '' : String(value);
    return s.replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  function fmtMs(v){ return `${Math.round(v||0).toLocaleString()} ms`; }
  function fmtPct(v){ return `${((v||0)*100).toFixed(1)}%`; }
  function fmtNum(v){ return (v||0).toLocaleString(); }
  function fmtDuration(seconds){
    if (seconds === null || seconds === undefined) return '—';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return mins ? `${mins}m ${secs}s` : `${secs}s`;
  }
  function shortTime(iso){
    try { return new Date(iso).toLocaleTimeString(); } catch { return esc(iso); }
  }
  function rowsOrEmpty(rows, colspan, emptyText){
    return rows || `<tr><td class="empty" colspan="${colspan}">${esc(emptyText)}</td></tr>`;
  }

  let toastTimer;
  function showToast(msg){
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.style.display = 'none'; }, 4000);
  }
  function announce(msg){
    document.getElementById('liveRegion').textContent = msg;
  }

  async function api(path, signal){
    const res = await fetch(path, { headers: { Authorization: `Bearer ${token()}` }, signal });
    if (res.status === 401) throw new Error('unauthorized');
    if (!res.ok) throw new Error(`request_failed:${res.status}`);
    return res.json();
  }

  // --- auth ------------------------------------------------------------

  async function login(){
    const userInput = document.getElementById('user');
    const passInput = document.getElementById('pass');
    const username = userInput.value.trim();
    const password = passInput.value;
    const err = document.getElementById('loginError');
    const button = document.getElementById('loginBtn');
    const label = document.getElementById('loginLabel');
    err.style.display = 'none';
    userInput.removeAttribute('aria-invalid');
    passInput.removeAttribute('aria-invalid');

    if (!username || !password) {
      err.textContent = 'Enter both your Vela username and password.';
      err.style.display = 'block';
      const target = !username ? userInput : passInput;
      target.setAttribute('aria-invalid', 'true');
      target.focus();
      return;
    }
    button.disabled = true;
    label.textContent = 'Signing in…';
    try {
      const res = await fetch('/auth/token', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ username, password })
      });
      if (!res.ok) throw new Error('login_failed');
      const data = await res.json();
      if (!data || !data.access_token) throw new Error('bad_response');
      setToken(data.access_token);
      passInput.value = '';
      showDash();
      backoffMs = POLL_MS;
      await refresh();
      startPoll();
    } catch (e) {
      err.textContent = 'Could not sign in. Check your username and password.';
      err.style.display = 'block';
      passInput.setAttribute('aria-invalid', 'true');
      passInput.focus();
    } finally {
      button.disabled = false;
      label.textContent = 'Open dashboard';
    }
  }

  function showDash(){
    document.getElementById('loginView').style.display = 'none';
    document.getElementById('dashView').style.display = 'block';
  }

  // --- charts ------------------------------------------------------------

  function ensureCharts(){
    if (rateChart) return;
    const common = {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 200 },
      plugins: { legend: { labels: { color: '#8B95A8', boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: '#5C667A', maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { color: '#2A3344' } },
        y: { ticks: { color: '#5C667A' }, grid: { color: '#2A3344' }, beginAtZero: true }
      }
    };
    rateChart = new Chart(document.getElementById('rateChart'), {
      type: 'line',
      data: { labels: [], datasets: [
        { label: 'Requests', data: [], borderColor: '#4F7CFF', backgroundColor: 'rgba(79,124,255,.15)', tension: .3, fill: true, pointRadius: 0 },
        { label: 'Errors', data: [], borderColor: '#F07178', backgroundColor: 'rgba(240,113,120,.12)', tension: .3, fill: true, pointRadius: 0 }
      ]},
      options: common
    });
    latChart = new Chart(document.getElementById('latChart'), {
      type: 'line',
      data: { labels: [], datasets: [
        { label: 'Median', data: [], borderColor: '#3DCF8E', tension: .3, pointRadius: 0 },
        { label: 'p95', data: [], borderColor: '#E6B450', tension: .3, pointRadius: 0 }
      ]},
      options: common
    });
  }

  // --- rendering (all server-supplied strings pass through esc()) -------

  function renderSummary(s){
    document.getElementById('rateChartError').textContent = '';
    document.getElementById('statTotal').textContent = fmtNum(s.total_requests);
    document.getElementById('statWindow').textContent = `${s.window_minutes} min window`;
    document.getElementById('statErrors').textContent = fmtPct(s.error_rate);
    document.getElementById('statErrorCount').textContent = `${fmtNum(s.error_count)} errors`;
    document.getElementById('statMedian').textContent = fmtMs(s.median_ms);
    document.getElementById('statP95').textContent = fmtMs(s.p95_ms);

    ensureCharts();
    const labels = (s.timeline||[]).map(p => shortTime(p.minute));
    rateChart.data.labels = labels;
    rateChart.data.datasets[0].data = (s.timeline||[]).map(p => p.count);
    rateChart.data.datasets[1].data = (s.timeline||[]).map(p => p.errors);
    rateChart.update('none');
    latChart.data.labels = labels;
    latChart.data.datasets[0].data = (s.timeline||[]).map(p => p.median_ms);
    latChart.data.datasets[1].data = (s.timeline||[]).map(p => p.p95_ms);
    latChart.update('none');

    const eb = document.getElementById('endpointBody');
    const endpointRows = (s.by_endpoint||[]).map(row => `
      <tr>
        <td class="mono">${esc(row.endpoint)}</td>
        <td>${fmtNum(row.count)}</td>
        <td>${fmtPct(row.error_rate)}</td>
        <td>${fmtMs(row.median_ms)}</td>
        <td>${fmtMs(row.p95_ms)}</td>
      </tr>`).join('');
    eb.innerHTML = rowsOrEmpty(endpointRows, 5, 'No traffic in this window.');

    const errb = document.getElementById('errorsBody');
    const errorRows = (s.recent_errors||[]).map(e => `
      <tr>
        <td>${shortTime(e.created_at)}</td>
        <td class="mono">${esc((e.request_id||'').slice(0,8))}</td>
        <td class="mono">${esc(e.method)} ${esc(e.path)}</td>
        <td><span class="badge err">${esc(e.status_code)}</span></td>
        <td>${fmtMs(e.duration_ms)}</td>
      </tr>`).join('');
    errb.innerHTML = rowsOrEmpty(errorRows, 5, 'No errors.');
  }

  function renderEvents(payload){
    const body = document.getElementById('eventsBody');
    const rows = (payload.events||[]).map(e => `
      <tr>
        <td>${shortTime(e.created_at)}</td>
        <td class="mono">${esc(e.method)} ${esc(e.path)}</td>
        <td><span class="badge ${e.status_code>=400?'err':'ok'}">${esc(e.status_code)}</span></td>
        <td>${fmtMs(e.duration_ms)}</td>
      </tr>`).join('');
    body.innerHTML = rowsOrEmpty(rows, 4, 'No events yet.');
    document.getElementById('eventsError').textContent = '';
  }

  function renderConnectionStatus(payload){
    const relay = payload.relay;
    document.getElementById('backendServerTime').textContent =
      payload.server_time ? `checked ${shortTime(payload.server_time)}` : 'online';
    document.getElementById('backendStatus').textContent = 'Online';
    document.getElementById('backendStatusDot').className = 'status-dot';

    const status = relay.status || 'unknown';
    const isConnected = status === 'connected';
    const isWaiting = status === 'connecting' || status === 'reconnecting';
    const dot = document.getElementById('relayStatusDot');
    dot.className = `status-dot${isConnected ? '' : isWaiting || status === 'unknown' || status === 'stale' ? ' stale' : ' off'}`;
    document.getElementById('relayStatus').textContent = status.replace('_', ' ');
    document.getElementById('relayState').textContent = isConnected
      ? 'Relay tunnel connected'
      : status === 'unknown'
        ? 'No relay telemetry received yet'
        : isWaiting ? 'Relay tunnel connecting'
          : status === 'stale' ? 'Relay tunnel has stopped reporting'
            : 'Relay tunnel disconnected';
    document.getElementById('relayDisconnects').textContent = fmtNum(relay.disconnect_count);
    document.getElementById('relayReconnects').textContent = fmtNum(relay.reconnect_count);
    document.getElementById('relayUptime').textContent = fmtDuration(relay.connected_seconds);
    document.getElementById('relayDetail').textContent = relay.last_error
      ? `Last issue: ${relay.last_error}`
      : relay.last_message_at
        ? `Last relay message ${shortTime(relay.last_message_at)}`
        : status === 'unknown'
          ? 'Restart the Vela agent once to begin recording relay health.'
          : 'No relay activity recorded yet.';
  }

  function renderConnectionStatusUnavailable(){
    document.getElementById('backendStatus').textContent = 'Status unavailable';
    document.getElementById('backendStatusDot').className = 'status-dot stale';
    document.getElementById('backendServerTime').textContent = 'Failed to load';
    document.getElementById('relayStatus').textContent = 'unavailable';
    document.getElementById('relayStatusDot').className = 'status-dot stale';
    document.getElementById('relayState').textContent = 'Relay status unavailable';
  }

  function renderAssistant(summary, payload){
    document.getElementById('assistantToolSummary').textContent =
      `${fmtNum(summary.total_tool_calls)} calls · ${fmtNum(summary.tool_error_count)} failed · ${fmtPct(summary.tool_error_rate)} error rate`;
    document.getElementById('toolCallCount').textContent = fmtNum(summary.total_tool_calls);
    document.getElementById('toolFailureCount').textContent = fmtNum(summary.tool_error_count);
    document.getElementById('toolSuccessRate').textContent =
      summary.total_tool_calls ? fmtPct(1 - summary.tool_error_rate) : '—';

    const toolRows = (summary.by_tool||[]).map(row => `
      <tr>
        <td class="mono">${esc(row.tool_name)}</td><td>${fmtNum(row.count)}</td><td>${fmtPct(row.error_rate)}</td>
        <td>${fmtMs(row.median_ms)}</td><td>${fmtMs(row.p95_ms)}</td>
      </tr>`).join('');
    document.getElementById('toolsBody').innerHTML = rowsOrEmpty(toolRows, 5, 'No assistant tools executed in this window.');

    const toolEventRows = (payload.events||[]).map(e => `
      <tr>
        <td>${shortTime(e.created_at)}</td><td class="mono">${esc(e.tool_name)}</td>
        <td><span class="badge ${e.succeeded?'ok':'err'}">${e.succeeded?'OK':'FAILED'}</span></td>
        <td>${fmtMs(e.duration_ms)}</td>
      </tr>`).join('');
    document.getElementById('toolEventsBody').innerHTML = rowsOrEmpty(toolEventRows, 4, 'No tool events yet.');

    const toolErrorRows = (summary.recent_failures||[]).map(e => `
      <tr>
        <td class="mono">${esc(e.tool_name)}</td><td class="mono">${esc((e.request_id||'').slice(0,8))}</td>
        <td>${esc(e.error || 'Unknown error')}</td>
      </tr>`).join('');
    document.getElementById('toolErrorsBody').innerHTML = rowsOrEmpty(toolErrorRows, 3, 'No tool failures.');
    document.getElementById('toolFailurePanel').hidden = !(summary.recent_failures||[]).length;
  }

  // --- refresh / polling -------------------------------------------------

  function setLive(state){
    // state: 'live' | 'stale' | 'off'
    const dot = document.getElementById('liveDot');
    const label = document.getElementById('liveLabel');
    dot.classList.remove('off', 'stale');
    if (state === 'off') { dot.classList.add('off'); label.textContent = 'Offline'; }
    else if (state === 'stale') { dot.classList.add('stale'); label.textContent = 'Retrying'; }
    else { label.textContent = 'Live'; }
  }

  async function refresh(){
    const mins = document.getElementById('windowSelect').value;
    const refreshBtn = document.getElementById('refreshBtn');

    if (inFlightController) inFlightController.abort();
    const controller = new AbortController();
    inFlightController = controller;
    const mySeq = ++requestSeq;

    refreshBtn.disabled = true;
    try {
      const results = await Promise.allSettled([
        api(`/admin/summary?since_minutes=${mins}`, controller.signal),
        api(`/admin/events?limit=40&since_minutes=${mins}`, controller.signal),
        api(`/admin/assistant/summary?since_minutes=${mins}`, controller.signal),
        api(`/admin/assistant/events?limit=30&since_minutes=${mins}`, controller.signal),
        api(`/admin/status?since_minutes=${mins}`, controller.signal)
      ]);

      // A newer refresh started while this one was in flight; drop these results.
      if (mySeq !== requestSeq) return;

      const [summaryR, eventsR, assistantSummaryR, toolEventsR, statusR] = results;

      if (summaryR.status === 'rejected' && String(summaryR.reason?.message).includes('unauthorized')) {
        throw new Error('unauthorized');
      }

      if (summaryR.status === 'fulfilled') {
        renderSummary(summaryR.value);
      } else {
        document.getElementById('rateChartError').textContent = 'Failed to load';
      }
      if (eventsR.status === 'fulfilled') {
        renderEvents(eventsR.value);
      } else {
        document.getElementById('eventsError').textContent = 'Failed to load';
      }
      if (assistantSummaryR.status === 'fulfilled' && toolEventsR.status === 'fulfilled') {
        renderAssistant(assistantSummaryR.value, toolEventsR.value);
      }
      if (statusR.status === 'fulfilled') {
        renderConnectionStatus(statusR.value);
      } else {
        renderConnectionStatusUnavailable();
      }

      const anyFailed = results.some(r => r.status === 'rejected');
      document.getElementById('updatedAt').textContent = new Date().toLocaleTimeString();
      setLive(anyFailed ? 'stale' : 'live');
      backoffMs = POLL_MS;
    } catch (e) {
      if (e.name === 'AbortError') return;
      if (String(e.message).includes('unauthorized')) {
        clearToken();
        showToast('Session expired. Please sign in again.');
        setTimeout(() => location.reload(), 900);
        return;
      }
      setLive('off');
      announce('Dashboard refresh failed, retrying.');
      backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS);
    } finally {
      refreshBtn.disabled = false;
    }
  }

  function startPoll(){
    if (pollTimer) clearTimeout(pollTimer);
    const tick = async () => {
      if (!document.hidden) await refresh();
      pollTimer = setTimeout(tick, backoffMs);
    };
    pollTimer = setTimeout(tick, backoffMs);
  }

  async function clearHistory(){
    if (!window.confirm('Clear all request, assistant, and relay monitoring history? This cannot be undone.')) return;
    const button = document.getElementById('clearHistoryBtn');
    button.disabled = true;
    try {
      const res = await fetch('/admin/clear', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token()}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ confirmation: 'CLEAR' })
      });
      if (res.status === 401) throw new Error('unauthorized');
      if (!res.ok) throw new Error(`request_failed:${res.status}`);
      const result = await res.json();
      showToast(`Cleared ${fmtNum(result.deleted)} monitoring records.`);
      await refresh();
    } catch (e) {
      if (String(e.message).includes('unauthorized')) {
        clearToken();
        location.reload();
        return;
      }
      showToast('Could not clear monitoring history.');
    } finally {
      button.disabled = false;
    }
  }

  // --- wiring -------------------------------------------------------------

  document.getElementById('loginForm').addEventListener('submit', e => { e.preventDefault(); login(); });
  document.getElementById('passwordToggle').onclick = () => {
    const input = document.getElementById('pass');
    const toggle = document.getElementById('passwordToggle');
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    toggle.textContent = show ? 'HIDE' : 'SHOW';
    toggle.setAttribute('aria-pressed', String(show));
    input.focus();
  };
  document.getElementById('refreshBtn').onclick = () => { backoffMs = POLL_MS; refresh(); };
  document.getElementById('clearHistoryBtn').onclick = clearHistory;
  document.getElementById('windowSelect').onchange = (e) => {
    localStorage.setItem(WINDOW_KEY, e.target.value);
    backoffMs = POLL_MS;
    refresh();
  };
  document.getElementById('logoutBtn').onclick = () => {
    clearToken();
    if (inFlightController) inFlightController.abort();
    if (pollTimer) clearTimeout(pollTimer);
    location.reload();
  };
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && token()) refresh();
  });

  // Restore persisted window selection, then boot.
  const savedWindow = localStorage.getItem(WINDOW_KEY);
  if (savedWindow) {
    const opt = document.querySelector(`#windowSelect option[value="${CSS.escape(savedWindow)}"]`);
    if (opt) document.getElementById('windowSelect').value = savedWindow;
  }

  if (token()) {
    showDash();
    refresh().then(startPoll);
  }
})();
</script>
</body>
</html>
"""