import html
import json


def render_pairing_page(state: dict) -> str:
    pairing_code = str(state.get("pairing_code") or "")
    pairing_pin = state.get("pairing_pin")

    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Vela Pairing</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <style>
      :root {{
        --bg: #f3f5fb;
        --bg-accent: #e8edfb;
        --panel: #ffffff;
        --text: #1a2233;
        --muted: #64748b;
        --border: #e6eaf3;
        --accent: #2f6bff;
        --accent-soft: #eef3ff;
        --amber: #b7791f;
        --amber-soft: #fff6e5;
        --green: #0f9d63;
        --green-soft: #e9fbf3;
        --red: #d64545;
        --red-soft: #fdecec;
        --shadow: 0 10px 30px -12px rgba(30, 41, 82, .18);
      }}
      * {{ box-sizing: border-box; }}
      @media (prefers-reduced-motion: reduce) {{
        *, *::before, *::after {{
          animation-duration: .001ms !important;
          transition-duration: .001ms !important;
        }}
      }}
      body {{
        margin: 0;
        font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        color: var(--text);
        background: radial-gradient(circle at top right, var(--bg-accent) 0, var(--bg) 55%);
        min-height: 100vh;
      }}
      .shell {{
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 1rem;
      }}
      .panel {{
        width: 100%;
        max-width: 520px;
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 1.4rem 1.2rem;
        box-shadow: var(--shadow);
        animation: panelIn .5s cubic-bezier(.16,1,.3,1);
      }}
      @keyframes panelIn {{
        from {{ opacity: 0; transform: translateY(10px) scale(.98); }}
        to {{ opacity: 1; transform: translateY(0) scale(1); }}
      }}
      h1 {{
        margin: 0 0 .35rem;
        font-size: 1.25rem;
        text-align: center;
        letter-spacing: -.01em;
      }}
      .hint {{
        margin: 0 0 1rem;
        color: var(--muted);
        text-align: center;
        font-size: .95rem;
      }}
      .status {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: .7rem;
        gap: .5rem;
      }}
      .badge {{
        display: inline-flex;
        align-items: center;
        gap: .4rem;
        padding: .28rem .7rem;
        border-radius: 999px;
        font-size: .8rem;
        font-weight: 700;
        transition: background-color .25s ease, color .25s ease;
      }}
      .badge-dot {{
        width: .45rem;
        height: .45rem;
        border-radius: 50%;
        background: currentColor;
        flex-shrink: 0;
      }}
      .badge-awaiting {{ background: var(--accent-soft); color: var(--accent); }}
      .badge-awaiting .badge-dot {{ animation: pulseDot 1.6s ease-in-out infinite; }}
      .badge-paired {{ background: var(--amber-soft); color: var(--amber); }}
      .badge-paired .badge-dot {{ animation: spinDot 1s linear infinite; border-radius: 2px; }}
      .badge-active {{ background: var(--green-soft); color: var(--green); }}
      .badge-expired, .badge-revoked {{ background: var(--red-soft); color: var(--red); }}
      @keyframes pulseDot {{
        0%, 100% {{ opacity: 1; transform: scale(1); }}
        50% {{ opacity: .35; transform: scale(.7); }}
      }}
      @keyframes spinDot {{
        from {{ transform: rotate(0deg); }}
        to {{ transform: rotate(360deg); }}
      }}
      .meta {{
        font-size: .86rem;
        color: var(--muted);
        text-align: center;
      }}
      .meta strong {{ color: var(--text); font-variant-numeric: tabular-nums; }}
      #qrWrap {{
        position: relative;
        width: 280px;
        margin: .35rem auto .9rem;
      }}
      #qrcode {{
        width: 280px;
        height: 280px;
        background: #fff;
        border-radius: 14px;
        border: 1px solid var(--border);
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        transition: opacity .35s ease, filter .35s ease;
        animation: qrIn .4s cubic-bezier(.16,1,.3,1);
      }}
      @keyframes qrIn {{
        from {{ opacity: 0; transform: scale(.92); }}
        to {{ opacity: 1; transform: scale(1); }}
      }}
      #qrcode.stale {{ opacity: .35; filter: grayscale(.4); }}
      #qrStaleNote {{
        text-align: center;
        font-size: .82rem;
        color: var(--amber);
        margin: -.5rem 0 .7rem;
        min-height: 1.1em;
      }}
      .manual {{
        margin-top: .8rem;
        border-top: 1px solid var(--border);
        padding-top: .7rem;
      }}
      .manual summary {{
        cursor: pointer;
        color: var(--muted);
        font-size: .92rem;
      }}
      .manual summary:hover {{ color: var(--text); }}
      .manual-body {{
        margin-top: .6rem;
        display: flex;
        flex-direction: column;
        gap: .5rem;
      }}
      .code-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: .6rem;
        padding: .5rem .7rem;
        background: var(--bg);
        border: 1px solid var(--border);
        border-radius: 10px;
        font-size: .88rem;
      }}
      .code-row span.label {{ color: var(--muted); }}
      .code-row strong {{
        font-variant-numeric: tabular-nums;
        letter-spacing: .03em;
      }}
      .copy-btn {{
        border: 1px solid var(--border);
        background: var(--panel);
        color: var(--accent);
        font-size: .78rem;
        font-weight: 600;
        padding: .3rem .6rem;
        border-radius: 7px;
        cursor: pointer;
        transition: background-color .15s ease, transform .1s ease;
      }}
      .copy-btn:hover {{ background: var(--accent-soft); }}
      .copy-btn:active {{ transform: scale(.94); }}
      #statusHint {{
        margin: .2rem 0 .7rem;
        text-align: center;
        color: var(--muted);
        font-size: .9rem;
        transition: opacity .2s ease;
      }}
      .hidden {{ display: none !important; }}
      .success-box {{
        margin-top: .8rem;
        padding: 1.1rem .9rem;
        border-radius: 12px;
        background: var(--green-soft);
        border: 1px solid #b7ecd4;
        color: #0b6b48;
        text-align: center;
        font-weight: 600;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: .5rem;
        animation: successIn .45s cubic-bezier(.16,1,.3,1);
      }}
      @keyframes successIn {{
        from {{ opacity: 0; transform: translateY(6px) scale(.97); }}
        to {{ opacity: 1; transform: translateY(0) scale(1); }}
      }}
      .check-circle {{
        width: 44px;
        height: 44px;
        border-radius: 50%;
        background: var(--green);
        display: flex;
        align-items: center;
        justify-content: center;
        animation: popIn .4s cubic-bezier(.34,1.56,.64,1) .1s both;
      }}
      @keyframes popIn {{
        from {{ transform: scale(0); }}
        to {{ transform: scale(1); }}
      }}
      .check-circle svg {{ stroke-dasharray: 20; stroke-dashoffset: 20; animation: draw .35s ease .3s forwards; }}
      @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
    </style>
  </head>
  <body>
    <div class="shell">
      <section class="panel">
        <h1>Scan to Pair Android</h1>
        <p class="hint">Open the Android app and scan this QR. It contains only the pairing fields the app needs.</p>
        <div class="status">
          <span id="statusLabel" class="badge badge-awaiting"><span class="badge-dot"></span>Waiting for pairing</span>
          <span class="meta">Expires in <strong id="expiresIn">--</strong></span>
        </div>
        <p id="statusHint" aria-live="polite">Scan the QR in Android to continue.</p>
        <div id="qrWrap">
          <div id="qrcode"></div>
        </div>
        <p id="qrStaleNote"></p>
        <details class="manual" id="manualSection">
          <summary>Use another device instead</summary>
          <div class="manual-body">
            <div class="code-row">
              <span class="label">Pairing code</span>
              <strong id="pairingCodeText">{html.escape(pairing_code)}</strong>
              <button class="copy-btn" type="button" data-copy="code">Copy</button>
            </div>
            <div class="code-row">
              <span class="label">Pairing PIN</span>
              <strong id="pairingPinText">{html.escape(pairing_pin or "N/A")}</strong>
              <button class="copy-btn" type="button" data-copy="pin">Copy</button>
            </div>
          </div>
        </details>
        <div id="successBox" class="success-box hidden">
          <span class="check-circle">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path d="M5 13l4 4L19 7" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </span>
          Pairing successful. You can now close this tab.
        </div>
      </section>
    </div>

    <script>
      const initialState = {json.dumps(state)};
      let currentState = initialState;
      let countdownTimerId = null;
      let pollTimerId = null;

      function statusClass(status) {{
        if (status === 'PAIRED') return 'badge badge-paired';
        if (status === 'ACTIVE') return 'badge badge-active';
        if (status === 'EXPIRED') return 'badge badge-expired';
        if (status === 'REVOKED') return 'badge badge-revoked';
        return 'badge badge-awaiting';
      }}

      function statusText(status) {{
        if (status === 'AWAITING_PAIR') return 'Waiting for pairing';
        if (status === 'PAIRED') return 'Paired, activating';
        if (status === 'ACTIVE') return 'Pairing complete';
        if (status === 'EXPIRED') return 'Code expired';
        if (status === 'REVOKED') return 'Pairing revoked';
        return 'Pending';
      }}

      function statusHint(status) {{
        if (status === 'AWAITING_PAIR') return 'Scan the QR in Android to continue.';
        if (status === 'PAIRED') return 'Android confirmed. Finishing activation...';
        if (status === 'ACTIVE') return 'Connected successfully. You can close this page.';
        if (status === 'EXPIRED') return 'Session expired. Waiting for a new pairing code.';
        if (status === 'REVOKED') return 'This pairing was revoked. Start pairing again.';
        return 'Waiting for status update.';
      }}

      function renderQr(payload) {{
        const container = document.getElementById('qrcode');
        container.innerHTML = '';
        if (!payload) {{
          container.textContent = 'No QR payload';
          return;
        }}
        if (window.QRCode) {{
          new QRCode(container, {{
            text: payload,
            width: 260,
            height: 260,
            correctLevel: QRCode.CorrectLevel.M
          }});
          return;
        }}
        container.innerHTML = '<div style="padding:1rem;color:#111;text-align:center;font-size:.9rem;">QR unavailable. Enter code/PIN manually.</div>';
      }}

      function updateExpiry() {{
        const expiresNode = document.getElementById('expiresIn');
        const staleNote = document.getElementById('qrStaleNote');
        const qrEl = document.getElementById('qrcode');
        const started = currentState.started_at_epoch || 0;
        const ttl = currentState.pairing_expires_in || 0;
        const left = Math.max(0, ttl - (Math.floor(Date.now() / 1000) - started));
        const mins = Math.floor(left / 60);
        const secs = String(left % 60).padStart(2, '0');
        expiresNode.textContent = `${{mins}}:${{secs}}`;

        // If the local countdown hits zero but the backend hasn't confirmed
        // EXPIRED yet (poll interval lag), hint that rather than leaving a
        // frozen, unexplained "0:00" on screen.
        if (left <= 0 && currentState.status === 'AWAITING_PAIR') {{
          qrEl.classList.add('stale');
          staleNote.textContent = 'This code may have expired, confirming...';
        }} else {{
          qrEl.classList.remove('stale');
          staleNote.textContent = '';
        }}
      }}

      function startCountdown() {{
        if (countdownTimerId) return;
        countdownTimerId = setInterval(updateExpiry, 1000);
      }}

      function stopCountdown() {{
        if (!countdownTimerId) return;
        clearInterval(countdownTimerId);
        countdownTimerId = null;
      }}

      function stopPolling() {{
        if (!pollTimerId) return;
        clearInterval(pollTimerId);
        pollTimerId = null;
      }}

      function applyState(data) {{
        const previousStatus = currentState.status;
        currentState = {{ ...currentState, ...data }};
        const status = currentState.status || 'UNKNOWN';
        const statusLabel = document.getElementById('statusLabel');
        statusLabel.className = statusClass(status);
        statusLabel.innerHTML = '<span class="badge-dot"></span>' + statusText(status);
        document.getElementById('statusHint').textContent = statusHint(status);
        updateExpiry();

        const qrWrap = document.getElementById('qrWrap');
        const staleNote = document.getElementById('qrStaleNote');
        const manual = document.getElementById('manualSection');
        const successBox = document.getElementById('successBox');

        if (status === 'ACTIVE') {{
          qrWrap.classList.add('hidden');
          staleNote.classList.add('hidden');
          manual.classList.add('hidden');
          successBox.classList.remove('hidden');
          // Pairing is done: stop both timers so the page doesn't keep
          // ticking a countdown or polling the server forever.
          stopCountdown();
          stopPolling();
        }} else {{
          qrWrap.classList.remove('hidden');
          staleNote.classList.remove('hidden');
          manual.classList.remove('hidden');
          successBox.classList.add('hidden');
          if (status !== previousStatus) {{
            renderQr(currentState.qr_payload);
          }}
          if (status === 'AWAITING_PAIR') {{
            startCountdown();
          }} else {{
            // No point counting down while paired/expired/revoked.
            stopCountdown();
          }}
        }}
      }}

      async function refreshStatus() {{
        try {{
          const res = await fetch('/state');
          const data = await res.json();
          applyState(data);
        }} catch (_) {{}}
      }}

      document.querySelectorAll('.copy-btn').forEach((btn) => {{
        btn.addEventListener('click', async () => {{
          const which = btn.getAttribute('data-copy');
          const text = which === 'code'
            ? document.getElementById('pairingCodeText').textContent
            : document.getElementById('pairingPinText').textContent;
          try {{
            await navigator.clipboard.writeText(text);
            const original = btn.textContent;
            btn.textContent = 'Copied';
            setTimeout(() => {{ btn.textContent = original; }}, 1200);
          }} catch (_) {{}}
        }});
      }});

      renderQr(initialState.qr_payload);
      applyState(initialState);
      pollTimerId = setInterval(refreshStatus, 1500);
      refreshStatus();
    </script>
  </body>
</html>
"""