import html


def render_setup_wizard_page(defaults: dict[str, str]) -> str:
    values = {
        "USERNAME": html.escape(defaults.get("username", "")),
        "VPS_URL": html.escape(defaults.get("vps_url", "")),
        "AGENT_LABEL": html.escape(defaults.get("agent_label", "")),
        "HOST": html.escape(defaults.get("host", "")),
        "PORT": html.escape(defaults.get("port", "")),
        "DIRS": html.escape(defaults.get("allowed_dirs_csv", "")),
        "PIN": html.escape(defaults.get("assistant_pin", "")),
        "FIREWORKS_API_KEY": html.escape(defaults.get("fireworks_api_key", "")),
        "IPINFO_TOKEN": html.escape(defaults.get("ipinfo_token", "")),
        "RESEND_API_KEY": html.escape(defaults.get("resend_api_key", "")),
        "RESEND_FROM_EMAIL": html.escape(defaults.get("resend_from_email", "")),
        "RECIPIENT_EMAIL": html.escape(defaults.get("recipient_email", "")),
        "SPOTIFY_CLIENT_ID": html.escape(defaults.get("spotify_client_id", "")),
        "SPOTIFY_CLIENT_SECRET": html.escape(defaults.get("spotify_client_secret", "")),
    }

    template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Vela Setup Wizard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<style>
  :root{
    --bg:#F3F6FC; --paper:#FFFFFF; --panel:#F8FAFE; --line:#DCE3F0; --line-soft:#EAF0F8;
    --ink:#172033; --ink-soft:#64718A; --ink-faint:#8995AA; --accent:#4F7CFF;
    --accent-soft:#EAF0FF; --good:#248C62; --warn:#B7791F; --bad:#C94954;
    --mono:'IBM Plex Mono', ui-monospace, monospace; --sans:'Inter', -apple-system, sans-serif;
  }
  *{box-sizing:border-box;} html,body{margin:0;padding:0;}
  body{background:radial-gradient(circle at 12% 5%,rgba(79,124,255,.12),transparent 30%),radial-gradient(circle at 88% 92%,rgba(36,140,98,.08),transparent 28%),var(--bg);font-family:var(--sans);color:var(--ink);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:40px 20px;}
  .card{width:100%;max-width:520px;background:rgba(255,255,255,.96);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:0 20px 50px rgba(36,55,93,.12);}
  .progress{display:flex;gap:6px;padding:22px 26px 0;} .progress .seg{flex:1;height:3px;border-radius:2px;background:var(--line-soft);}
  .progress .seg::after{content:"";display:block;height:100%;width:0%;background:var(--accent);transition:width .35s ease;}
  .progress .seg.done::after,.progress .seg.active::after{width:100%;}
  .head{padding:20px 26px 0;} .eyebrow{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-faint);display:flex;align-items:center;gap:8px;margin-bottom:8px;}
  .brand-mark{width:18px;height:18px;border-radius:5px;background:var(--accent);flex-shrink:0;box-shadow:0 0 14px rgba(79,124,255,.32);}
  h1{font-size:21px;letter-spacing:-0.01em;margin:0 0 6px;font-weight:700;} .sub{color:var(--ink-soft);font-size:13.5px;line-height:1.5;margin:0 0 22px;}
  .step{display:none;padding:0 26px 26px;} .step.active{display:block;}
  .field{margin-bottom:16px;} .field label{display:block;font-size:12.5px;font-weight:600;margin-bottom:6px;}
  .hint{font-size:11.5px;color:var(--ink-faint);margin-top:6px;line-height:1.4;} .row2{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
  input[type=text],input[type=password],input[type=email]{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:8px;font-family:var(--sans);font-size:13.5px;color:var(--ink);background:var(--panel);transition:border-color .15s, box-shadow .15s;}
  input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);} input.mono{font-family:var(--mono);}
  .pin-field{position:relative;} .pin-field input{padding-right:60px;}
  .pin-toggle{position:absolute;right:8px;top:50%;transform:translateY(-50%);font-family:var(--mono);font-size:10.5px;text-transform:uppercase;color:var(--accent);background:none;border:none;cursor:pointer;padding:4px 6px;}
  .actions{display:flex;align-items:center;justify-content:space-between;margin-top:22px;}
  .btn-primary{background:var(--accent);color:#fff;border:none;padding:11px 20px;border-radius:8px;font-size:13.5px;font-weight:600;cursor:pointer;display:inline-flex;align-items:center;gap:7px;box-shadow:0 5px 12px rgba(79,124,255,.22);}
  .btn-primary:hover{background:#3F6DEE;}.btn-primary:focus-visible,.btn-ghost:focus-visible,.pin-toggle:focus-visible{outline:3px solid rgba(79,124,255,.32);outline-offset:2px;}
  .btn-primary svg,.btn-ghost svg{width:13px;height:13px;}
  .btn-ghost{background:none;border:none;color:var(--ink-soft);font-size:13px;font-weight:500;cursor:pointer;padding:8px 4px;display:inline-flex;align-items:center;gap:6px;}
  .review-list{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:6px;background:var(--panel);}
  .review-row{display:flex;justify-content:space-between;gap:12px;padding:10px 14px;font-size:12.5px;border-bottom:1px solid var(--line-soft);}
  .review-row:last-child{border-bottom:none;} .review-row span:first-child{color:var(--ink-faint);} .review-row span:last-child{font-family:var(--mono);font-weight:500;text-align:right;word-break:break-all;}
  .dependency-panel{display:none;margin:16px 0 6px;padding:14px;border:1px solid rgba(79,124,255,.28);border-radius:10px;background:var(--accent-soft);}
  .dependency-panel h2{font-size:14px;margin:0 0 6px;}.dependency-panel p{font-size:12px;color:var(--ink-soft);line-height:1.45;margin:0 0 10px;}
  .dependency-list{margin:0 0 12px;padding:0;list-style:none;}.dependency-list li{padding:8px 0;border-top:1px solid rgba(79,124,255,.14);font-size:12px;}
  .dependency-list li:first-child{border-top:0;}.dependency-list strong{display:block;font-size:12.5px;}.dependency-list span{display:block;margin-top:2px;color:var(--ink-soft);}
  .dependency-actions{display:flex;justify-content:flex-end;gap:10px;}.dependency-actions .btn-primary{padding:9px 12px;font-size:12.5px;}
  .status-pill{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);font-size:11px;font-weight:600;padding:5px 11px;border-radius:20px;background:#FFF6E6;color:var(--warn);text-transform:uppercase;letter-spacing:.05em;margin-bottom:18px;}
  .status-pill .dot{width:6px;height:6px;border-radius:50%;background:var(--warn);animation:blink 1.4s infinite;}
  .status-pill.paired{background:#E8F7F0;color:var(--good);} .status-pill.paired .dot{background:var(--good);animation:none;}
  @keyframes blink{0%,100%{opacity:1;}50%{opacity:.3;}}
  .qr-wrap{border:1px solid var(--line);border-radius:12px;padding:18px;background:var(--panel);text-align:center;max-width:220px;margin:0 auto 20px;}
  #qrRender{width:180px;height:180px;margin:0 auto 10px;display:flex;align-items:center;justify-content:center;background:#fff;border:1px solid var(--line);border-radius:8px;}
  .qr-caption{font-size:10.5px;color:var(--ink-faint);font-family:var(--mono);}
  .code-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;}
  .code-grid .full{grid-column:1 / -1;}
  .code-card{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--panel);text-align:center;}
  .code-card .node-label{font-family:var(--mono);font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-faint);margin-bottom:6px;}
  .code-value{font-family:var(--mono);font-size:19px;font-weight:600;letter-spacing:.02em;word-break:break-all;}
  .expiry-note{display:flex;align-items:flex-start;gap:7px;font-size:11.5px;color:var(--ink-faint);line-height:1.5;}
  .expiry-note svg{width:13px;height:13px;flex-shrink:0;margin-top:1px;}
  .done-wrap{text-align:center;padding:8px 0 4px;} .done-icon{width:46px;height:46px;border-radius:50%;background:#E8F7F0;color:var(--good);display:flex;align-items:center;justify-content:center;margin:0 auto 16px;}
  .done-icon svg{width:20px;height:20px;} .done-title{font-size:16px;font-weight:700;margin-bottom:6px;} .done-sub{font-size:13px;color:var(--ink-soft);margin-bottom:22px;line-height:1.5;}
  .error-banner{display:none;margin:0 26px 14px;padding:10px 12px;border:1px solid rgba(201,73,84,.25);background:#FFF1F2;color:var(--bad);border-radius:10px;font-size:12.5px;line-height:1.45;}
</style>
</head>
<body>
<div class="card">
  <div class="progress">
    <div class="seg" id="seg1"></div>
    <div class="seg" id="seg2"></div>
    <div class="seg" id="seg3"></div>
    <div class="seg" id="seg4"></div>
  </div>
  <div class="head"><div class="eyebrow"><div class="brand-mark"></div>Vela Setup</div></div>
  <div id="errorBanner" class="error-banner"></div>
  <form id="setupForm">
    <div class="step" id="step1">
      <h1>Configure this device</h1>
      <p class="sub">Set identity and access scope. Integrations come next.</p>
      <div class="field"><label for="user">Username</label><input name="username" type="text" id="user" value="__USERNAME__" required></div>
      <div class="field"><label for="pass">Password</label><input name="password" type="password" id="pass" value="" required></div>
      <div class="field"><label for="vps">VPS URL</label><input name="vps_url" type="text" id="vps" class="mono" value="__VPS_URL__" required></div>
      <div class="row2">
        <div class="field"><label for="label">Agent label</label><input name="agent_label" type="text" id="label" value="__AGENT_LABEL__" required></div>
        <div class="field"><label for="bind">Bind host</label><input name="host" type="text" id="bind" class="mono" value="__HOST__" required></div>
      </div>
      <div class="row2">
        <div class="field"><label for="port">Port</label><input name="port" type="text" id="port" class="mono" value="__PORT__" required></div>
        <div class="field"><label for="pin">Assistant PIN <span style="font-weight:400;color:var(--ink-faint)">(optional)</span></label>
          <div class="pin-field"><input name="assistant_pin" type="password" id="pin" class="mono" value="__PIN__"><button type="button" class="pin-toggle" id="pinToggle">Show</button></div>
        </div>
      </div>
      <div class="field" style="margin-bottom:0;"><label for="dirs">Allowed base directories</label><input name="allowed_dirs_csv" type="text" id="dirs" class="mono" value="__DIRS__" required><div class="hint">Comma-separated. Setup always starts fresh and re-pairs.</div></div>
      <div class="actions" style="justify-content:flex-end;">
        <button type="button" class="btn-primary" id="toIntegrationsBtn">Next <svg viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
      </div>
    </div>
    <div class="step" id="step2">
      <h1>Optional integrations</h1>
      <p class="sub">Skip anything you do not have yet. You can edit these later in <span class="mono">.env</span>.</p>
      <div class="field"><label for="fireworks">Fireworks API key</label><input name="fireworks_api_key" type="password" id="fireworks" class="mono" value="__FIREWORKS_API_KEY__" autocomplete="off"><div class="hint">Needed for the LLM assistant.</div></div>
      <div class="field"><label for="ipinfoToken">IPinfo token</label><input name="ipinfo_token" type="password" id="ipinfoToken" class="mono" value="__IPINFO_TOKEN__" autocomplete="off"><div class="hint">Optional fallback for network-location lookups.</div></div>
      <div class="field"><label for="resendKey">Resend API key</label><input name="resend_api_key" type="password" id="resendKey" class="mono" value="__RESEND_API_KEY__" autocomplete="off"></div>
      <div class="field"><label for="resendFrom">Resend from email</label><input name="resend_from_email" type="text" id="resendFrom" value="__RESEND_FROM_EMAIL__" placeholder="Vela &lt;alerts@example.com&gt;"></div>
      <div class="field"><label for="recipient">Alert recipient email</label><input name="recipient_email" type="email" id="recipient" value="__RECIPIENT_EMAIL__"></div>
      <div class="field"><label for="spotifyId">Spotify client ID</label><input name="spotify_client_id" type="text" id="spotifyId" class="mono" value="__SPOTIFY_CLIENT_ID__" autocomplete="off"></div>
      <div class="field" style="margin-bottom:0;"><label for="spotifySecret">Spotify client secret</label><input name="spotify_client_secret" type="password" id="spotifySecret" class="mono" value="__SPOTIFY_CLIENT_SECRET__" autocomplete="off"></div>
      <div class="actions">
        <button type="button" class="btn-ghost" id="backToConfigBtn"><svg viewBox="0 0 16 16" fill="none"><path d="M13 8H3M7 4L3 8l4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>Back</button>
        <button type="button" class="btn-primary" id="toReviewBtn">Review <svg viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
      </div>
    </div>
  </form>
  <div class="step" id="step3">
    <h1>Review &amp; confirm</h1>
    <p class="sub">Confirm details before setup and registration.</p>
    <div class="review-list">
      <div class="review-row"><span>Username</span><span id="r-user"></span></div>
      <div class="review-row"><span>VPS URL</span><span id="r-vps"></span></div>
      <div class="review-row"><span>Agent label</span><span id="r-label"></span></div>
      <div class="review-row"><span>Bind host : port</span><span id="r-bind"></span></div>
      <div class="review-row"><span>Allowed dirs</span><span id="r-dirs"></span></div>
      <div class="review-row"><span>Assistant PIN</span><span id="r-pin"></span></div>
      <div class="review-row"><span>Fireworks API key</span><span id="r-fireworks"></span></div>
      <div class="review-row"><span>IPinfo token</span><span id="r-ipinfo"></span></div>
      <div class="review-row"><span>Resend API key</span><span id="r-resend"></span></div>
      <div class="review-row"><span>Resend from email</span><span id="r-resend-from"></span></div>
      <div class="review-row"><span>Recipient email</span><span id="r-recipient"></span></div>
      <div class="review-row"><span>Spotify client ID</span><span id="r-spotify-id"></span></div>
      <div class="review-row"><span>Spotify client secret</span><span id="r-spotify-secret"></span></div>
    </div>
    <p class="hint" id="phaseText">[collect] Waiting for form submission...</p>
    <section class="dependency-panel" id="dependencyPanel" aria-labelledby="dependencyTitle">
      <h2 id="dependencyTitle">Optional system tools are missing</h2>
      <p id="dependencyMessage"></p>
      <ul class="dependency-list" id="dependencyList"></ul>
      <div class="dependency-actions">
        <button type="button" class="btn-ghost" id="skipDependenciesBtn">Skip for now</button>
        <button type="button" class="btn-primary" id="installDependenciesBtn">Install packages</button>
      </div>
    </section>
    <div class="actions">
      <button type="button" class="btn-ghost" id="backToIntegrationsBtn"><svg viewBox="0 0 16 16" fill="none"><path d="M13 8H3M7 4L3 8l4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>Back</button>
      <button type="button" class="btn-primary" id="startSetupBtn">Start setup <svg viewBox="0 0 16 16" fill="none"><path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
    </div>
  </div>
  <div class="step" id="step4">
    <h1>Pair your mobile app</h1>
    <p class="sub">Open the Vela app and use these pairing details.</p>
    <span class="status-pill" id="statusPill"><span class="dot"></span><span id="statusPillText">Awaiting pairing</span></span>
    <div class="qr-wrap">
      <div id="qrRender">Waiting QR...</div>
      <div class="qr-caption" id="agentIdText">pending...</div>
    </div>
    <div class="code-grid">
      <div class="code-card full">
        <div class="node-label">VPS URL</div>
        <div class="code-value" id="pairVpsText">--------</div>
      </div>
      <div class="code-card"><div class="node-label">Pairing code</div><div class="code-value" id="pairCodeText">--------</div></div>
      <div class="code-card"><div class="node-label">Pairing PIN</div><div class="code-value" id="pairPinText">------</div></div>
    </div>
    <div class="expiry-note"><svg viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.2"/><path d="M8 5v3.3l2.2 1.3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg><span id="expiryText">Waiting for pairing session...</span></div>
  </div>
  <div class="step" id="step5">
    <div class="done-wrap">
      <div class="done-icon"><svg viewBox="0 0 16 16" fill="none"><path d="M3 8.5l3 3 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>
      <div class="done-title" id="doneTitle">Agent paired</div>
      <div class="done-sub" id="doneSub">Setup complete.</div>
    </div>
  </div>
</div>
<script>
  const total = 4;
  let qr = null;
  let currentPairing = null;
  let currentQrPayload = null;
  let localErrorMessage = '';
  let serverErrorMessage = '';
  let userStep = 1;

  function goTo(n){
    document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
    const target = document.getElementById('step'+n);
    if (target) target.classList.add('active');
    for(let i=1;i<=total;i++){
      const seg = document.getElementById('seg'+i);
      seg.classList.remove('active','done');
      if(i < n) seg.classList.add('done');
      else if(i === n) seg.classList.add('active');
    }
    if(n === 5) for(let i=1;i<=total;i++) document.getElementById('seg'+i).classList.add('done');
    if (n <= 3) userStep = n;
  }

  function maskOrUnset(value){
    return value ? '•••• set' : 'Not set';
  }

  function fillReview(){
    document.getElementById('r-user').textContent = document.getElementById('user').value;
    document.getElementById('r-vps').textContent = document.getElementById('vps').value;
    document.getElementById('r-label').textContent = document.getElementById('label').value;
    document.getElementById('r-bind').textContent = document.getElementById('bind').value + ' : ' + document.getElementById('port').value;
    document.getElementById('r-dirs').textContent = document.getElementById('dirs').value;
    document.getElementById('r-pin').textContent = document.getElementById('pin').value ? '••••' : 'Not set';
    document.getElementById('r-fireworks').textContent = maskOrUnset(document.getElementById('fireworks').value);
    document.getElementById('r-ipinfo').textContent = maskOrUnset(document.getElementById('ipinfoToken').value);
    document.getElementById('r-resend').textContent = maskOrUnset(document.getElementById('resendKey').value);
    document.getElementById('r-resend-from').textContent = document.getElementById('resendFrom').value || 'Not set';
    document.getElementById('r-recipient').textContent = document.getElementById('recipient').value || 'Not set';
    document.getElementById('r-spotify-id').textContent = document.getElementById('spotifyId').value || 'Not set';
    document.getElementById('r-spotify-secret').textContent = maskOrUnset(document.getElementById('spotifySecret').value);
  }

  function renderQr(payload){
    const box = document.getElementById('qrRender');
    if(!payload || !window.QRCode){ return; }
    box.innerHTML = '';
    qr = new QRCode(box, { text: payload, width: 160, height: 160, correctLevel: QRCode.CorrectLevel.M });
    currentQrPayload = payload;
  }

  function updatePairingDisplay(data){
    const pairing = data.pairing || currentPairing;
    if (!pairing) return;
    currentPairing = pairing;
    document.getElementById('pairVpsText').textContent = pairing.vps_url || document.getElementById('vps').value || '--------';
    document.getElementById('agentIdText').textContent = pairing.agent_id || 'pending...';
    document.getElementById('pairCodeText').textContent = pairing.pairing_code || '--------';
    document.getElementById('pairPinText').textContent = pairing.pairing_pin || 'N/A';
    if (pairing.qr_payload && pairing.qr_payload !== currentQrPayload) {
      renderQr(pairing.qr_payload);
    }
    const status = data.pairing_status || pairing.status || 'AWAITING_PAIR';
    document.getElementById('statusPillText').textContent = status.toLowerCase().replace('_', ' ');
    if (status === 'ACTIVE') {
      document.getElementById('statusPill').classList.add('paired');
      goTo(5);
      document.getElementById('doneTitle').textContent = (document.getElementById('label').value || 'Agent') + ' is paired';
      document.getElementById('doneSub').textContent = 'Your mobile app is now connected to this device. Open Operations with: vela --dashboard';
    }
  }

  function renderDependencyPrompt(data){
    const panel = document.getElementById('dependencyPanel');
    const required = Boolean(data.dependency_decision_required);
    panel.style.display = required ? 'block' : 'none';
    if (!required) return;

    const dependency = data.dependency || {};
    const manager = dependency.package_manager || 'your package manager';
    const packages = dependency.packages || [];
    document.getElementById('dependencyMessage').textContent = packages.length
      ? `Install ${packages.join(', ')} using ${manager}. The terminal may ask for your system password.`
      : `No install command is available for ${manager}; install these tools manually or skip for now.`;
    const list = document.getElementById('dependencyList');
    list.replaceChildren();
    (dependency.missing || []).forEach(group => {
      const item = document.createElement('li');
      const title = document.createElement('strong');
      title.textContent = group.feature || 'Optional feature';
      const detail = document.createElement('span');
      const commands = (group.missing_commands || []).join(', ');
      detail.textContent = `${group.description || ''}${commands ? ` Missing: ${commands}.` : ''}`;
      item.append(title, detail);
      list.append(item);
    });
    document.getElementById('installDependenciesBtn').disabled = !packages.length || manager === 'unknown';
    document.getElementById('skipDependenciesBtn').disabled = false;
  }

  async function submitDependencyDecision(decision){
    const install = document.getElementById('installDependenciesBtn');
    const skip = document.getElementById('skipDependenciesBtn');
    install.disabled = true;
    skip.disabled = true;
    try {
      const res = await fetch('/dependency-decision', {
        method: 'POST',
        body: new URLSearchParams({ decision }),
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });
      if (!res.ok) throw new Error('Dependency decision failed');
      document.getElementById('dependencyPanel').style.display = 'none';
    } catch (_) {
      showError('Could not save the dependency choice. Please try again.', 'local');
      install.disabled = false;
      skip.disabled = false;
    }
  }

  function validateRequired(){
    const form = document.getElementById('setupForm');
    if (!form.reportValidity()) {
      showError('Please fill all required fields before continuing.', 'local');
      goTo(1);
      return false;
    }
    clearLocalError();
    return true;
  }

  async function submitSetup(){
    if (!validateRequired()) return;
    const form = document.getElementById('setupForm');
    const formData = new FormData(form);
    try {
      const res = await fetch('/submit', { method: 'POST', body: new URLSearchParams(formData), headers: { 'Content-Type': 'application/x-www-form-urlencoded' }});
      if (!res.ok) {
        const body = await res.text();
        throw new Error(body || `Submit failed with status ${res.status}`);
      }
      goTo(3);
      document.getElementById('phaseText').textContent = '[configuring] Setup submitted. Continuing...';
    } catch (_) {
      showError('Failed to submit setup form. Please try again.', 'local');
      document.getElementById('phaseText').textContent = '[error] Failed to submit setup form.';
    }
  }

  function updateErrorBanner(){
    const banner = document.getElementById('errorBanner');
    const activeMessage = localErrorMessage || serverErrorMessage;
    if (activeMessage) {
      banner.textContent = activeMessage;
      banner.style.display = 'block';
    } else {
      banner.textContent = '';
      banner.style.display = 'none';
    }
  }

  function showError(message, source){
    if (source === 'server') serverErrorMessage = message;
    else localErrorMessage = message;
    updateErrorBanner();
  }

  function clearLocalError(){
    localErrorMessage = '';
    updateErrorBanner();
  }

  async function refreshState(){
    try {
      const res = await fetch('/wizard-state');
      const data = await res.json();
      const phase = data.phase || 'collect';
      const msg = data.message || '';
      document.getElementById('phaseText').textContent = `[${phase}] ${msg}` + (data.error ? ` (${data.error})` : '');
      if (data.error) serverErrorMessage = String(data.error);
      else if (phase !== 'error') serverErrorMessage = '';
      updateErrorBanner();
      if (data.done) {
        goTo(5);
        if (msg) document.getElementById('doneSub').textContent = msg;
      } else if (data.pairing || phase === 'pairing') {
        goTo(4);
      } else if (phase === 'collect') {
        // keep user on config / integrations / review while editing
      } else {
        goTo(3);
      }
      renderDependencyPrompt(data);
      updatePairingDisplay(data);
    } catch (_) {}
  }

  document.getElementById('pinToggle').addEventListener('click', function(){
    const i = document.getElementById('pin');
    i.type = i.type === 'password' ? 'text' : 'password';
    this.textContent = i.type === 'password' ? 'Show' : 'Hide';
  });
  document.getElementById('toIntegrationsBtn').addEventListener('click', function(){
    if (!validateRequired()) return;
    goTo(2);
  });
  document.getElementById('toReviewBtn').addEventListener('click', function(){
    fillReview();
    goTo(3);
  });
  document.getElementById('backToConfigBtn').addEventListener('click', function(){ goTo(1); });
  document.getElementById('backToIntegrationsBtn').addEventListener('click', function(){ goTo(2); });
  document.getElementById('startSetupBtn').addEventListener('click', submitSetup);
  document.getElementById('installDependenciesBtn').addEventListener('click', function(){ submitDependencyDecision('install'); });
  document.getElementById('skipDependenciesBtn').addEventListener('click', function(){ submitDependencyDecision('skip'); });
  setInterval(refreshState, 1500);
  refreshState();
  goTo(1);
</script>
</body>
</html>
"""

    for key, value in values.items():
        template = template.replace(f"__{key}__", value)
    return template
