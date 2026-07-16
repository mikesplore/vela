import html
import json


def render_pairing_page(state: dict) -> str:
    pairing_code = str(state.get("pairing_code") or "")
    pairing_pin = state.get("pairing_pin")
    vps_url = str(state.get("vps_url") or "")

    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Vela Pairing</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
    <style>
      body {{ margin: 0; font-family: Inter, system-ui, sans-serif; background: #f7f8fb; color: #111827; }}
      .wrap {{ max-width: 560px; margin: 26px auto; padding: 0 14px; }}
      .card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 14px; padding: 16px; }}
      h1 {{ margin: 0 0 6px; font-size: 1.25rem; }}
      .muted {{ color: #6b7280; margin: 0 0 10px; }}
      .status {{ margin: 8px 0 12px; padding: 8px 10px; border: 1px solid #e5e7eb; border-radius: 9px; background: #f9fafb; }}
      .status strong {{ font-size: .92rem; }}
      #qrcode {{ margin: 0 auto; width: 260px; min-height: 260px; display: flex; align-items: center; justify-content: center; border: 1px solid #e5e7eb; border-radius: 10px; padding: 8px; background: #fff; }}
      .manual {{ margin-top: 12px; }}
      .row {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 8px 0; padding: 8px 10px; border: 1px solid #e5e7eb; border-radius: 9px; }}
      .label {{ color: #6b7280; font-size: .84rem; }}
      .value {{ font-size: .93rem; font-weight: 600; word-break: break-word; }}
      .copy-btn {{ border: 1px solid #d1d5db; background: #fff; border-radius: 8px; padding: 6px 9px; cursor: pointer; font-size: .8rem; }}
      .ok {{ margin-top: 10px; padding: 10px; border-radius: 9px; background: #ecfdf3; border: 1px solid #bbf7d0; color: #166534; display: none; font-weight: 600; }}
      .hidden {{ display: none !important; }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="card">
        <h1>Pair Vela</h1>
        <p class="muted">Scan this QR in the Android app or enter the details manually.</p>
        <div class="status">
          <strong id="statusText">Waiting for pairing</strong>
          <div class="muted">Expires in <span id="expiresIn">--</span></div>
        </div>
        <div id="qrcode"></div>
        <div id="manualSection" class="manual">
          <div class="row">
            <span class="label">VPS URL</span>
            <span id="vpsUrlText" class="value">{html.escape(vps_url)}</span>
            <button class="copy-btn" type="button" data-copy="vps-url">Copy</button>
          </div>
          <div class="row">
            <span class="label">Pairing code</span>
            <span id="pairingCodeText" class="value">{html.escape(pairing_code)}</span>
            <button class="copy-btn" type="button" data-copy="code">Copy</button>
          </div>
          <div class="row">
            <span class="label">Pairing PIN</span>
            <span id="pairingPinText" class="value">{html.escape(pairing_pin or "N/A")}</span>
            <button class="copy-btn" type="button" data-copy="pin">Copy</button>
          </div>
        </div>
        <div id="successBox" class="ok">Pairing successful. You can close this tab.</div>
      </div>
    </div>

    <script>
      const initialState = {json.dumps(state)};
      let currentState = initialState;

      function statusText(status) {{
        if (status === 'PAIRED') return 'Paired, activating';
        if (status === 'ACTIVE') return 'Pairing complete';
        if (status === 'EXPIRED') return 'Code expired';
        if (status === 'REVOKED') return 'Pairing revoked';
        return 'Waiting for pairing';
      }}

      function renderQr(payload) {{
        const container = document.getElementById('qrcode');
        container.innerHTML = '';
        if (!payload) {{
          container.textContent = 'No QR payload';
          return;
        }}
        new QRCode(container, {{
          text: payload,
          width: 240,
          height: 240,
          correctLevel: QRCode.CorrectLevel.M
        }});
      }}

      function updateExpiry() {{
        const started = currentState.started_at_epoch || 0;
        const ttl = currentState.pairing_expires_in || 0;
        const left = Math.max(0, ttl - (Math.floor(Date.now() / 1000) - started));
        const mins = Math.floor(left / 60);
        const secs = String(left % 60).padStart(2, '0');
        document.getElementById('expiresIn').textContent = `${{mins}}:${{secs}}`;
      }}

      function applyState(data) {{
        currentState = {{ ...currentState, ...data }};
        const status = currentState.status || 'AWAITING_PAIR';
        document.getElementById('statusText').textContent = statusText(status);
        updateExpiry();

        const manual = document.getElementById('manualSection');
        const success = document.getElementById('successBox');
        const qr = document.getElementById('qrcode');
        if (status === 'ACTIVE') {{
          manual.classList.add('hidden');
          qr.classList.add('hidden');
          success.style.display = 'block';
        }} else {{
          manual.classList.remove('hidden');
          qr.classList.remove('hidden');
          success.style.display = 'none';
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
          let text = '';
          if (which === 'vps-url') text = document.getElementById('vpsUrlText').textContent;
          else if (which === 'code') text = document.getElementById('pairingCodeText').textContent;
          else text = document.getElementById('pairingPinText').textContent;
          try {{
            await navigator.clipboard.writeText(text);
            const old = btn.textContent;
            btn.textContent = 'Copied';
            setTimeout(() => {{ btn.textContent = old; }}, 1200);
          }} catch (_) {{}}
        }});
      }});

      renderQr(initialState.qr_payload);
      applyState(initialState);
      setInterval(refreshStatus, 1500);
    </script>
  </body>
</html>
"""

