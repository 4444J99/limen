/**
 * The buyer-facing checkout PAGE — MONETA's own storefront, so the mint is one
 * self-contained deployable (API + page) with no third-party checkout in the
 * path. A product's "Buy Pro" button opens this page; it drives the whole
 * sovereign flow against the same-origin API:
 *
 *   POST /checkout        -> an order (reserved | pending)
 *   GET  /order/:id (poll) -> mints + returns the licence once the chain confirms
 *
 * Three states, mirroring {@link MintService.describe}:
 *   reserved  the valve is still closed (no receive address yet) — pool the
 *             buyer in line and keep polling; the key mints the moment it opens.
 *   pending   show the exact BTC address + amount + a BIP21 `bitcoin:` link the
 *             buyer's wallet opens directly; poll until the payment confirms.
 *   paid      redirect back to the product with `?ce_license_key=…` (the return
 *             contract the Exporter already captures), or show the key inline.
 *
 * Zero external assets: no fonts, no CDNs, no analytics — sovereignty extends to
 * the page itself. The dynamic values are written with `textContent`, never
 * `innerHTML`, so a licence/address can never inject markup.
 */

/** Render the self-contained checkout page. All dynamic data comes from the API. */
export function renderCheckoutPage(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Unlock Pro — sovereign checkout</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    background: #0b0d10; color: #e7ecf2;
  }
  main { width: min(92vw, 460px); padding: 28px; }
  .card {
    background: #14181d; border: 1px solid #232a31; border-radius: 14px;
    padding: 24px; box-shadow: 0 10px 40px rgba(0,0,0,.35);
  }
  h1 { font-size: 19px; margin: 0 0 4px; letter-spacing: .2px; }
  .sub { color: #93a1b0; font-size: 13px; margin: 0 0 18px; }
  .field { margin: 14px 0; }
  .label { color: #93a1b0; font-size: 12px; text-transform: uppercase; letter-spacing: .6px; margin-bottom: 4px; }
  .val {
    display: flex; gap: 8px; align-items: center;
    background: #0e1216; border: 1px solid #232a31; border-radius: 9px; padding: 10px 12px;
  }
  .val code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; word-break: break-all; flex: 1; }
  button {
    font: inherit; cursor: pointer; border: 1px solid #2b3742; background: #1b232b; color: #e7ecf2;
    border-radius: 8px; padding: 7px 12px;
  }
  button:hover { background: #222c36; }
  .pay {
    display: block; width: 100%; text-align: center; text-decoration: none; margin-top: 8px;
    background: #f7931a; color: #10130f; border: none; border-radius: 10px; padding: 13px; font-weight: 600;
  }
  .pay:hover { background: #ffa733; }
  .pill { display: inline-block; font-size: 12px; padding: 3px 9px; border-radius: 999px; }
  .pill.reserved { background: #2a2410; color: #e8c766; }
  .pill.pending  { background: #10222a; color: #63c8e8; }
  .pill.paid     { background: #10251a; color: #6fe6a2; }
  .pill.expired  { background: #2a1414; color: #e88686; }
  .muted { color: #6d7b88; font-size: 12px; }
  .center { text-align: center; }
  a { color: #63c8e8; }
</style>
</head>
<body>
<main>
  <div class="card">
    <h1>Unlock Pro</h1>
    <p class="sub">Sovereign checkout — paid in Bitcoin, straight to the seller. No card, no account, no processor.</p>
    <div id="body"><p class="muted">Preparing your order…</p></div>
  </div>
  <p class="center muted" style="margin-top:14px">Powered by <strong>MONETA</strong> · your key is signed offline and verified on your device.</p>
</main>
<script>
(function () {
  var orderId = null, timer = null;
  var body = document.getElementById('body');

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  function copyBtn(getText) {
    var b = el('button', null, 'Copy');
    b.addEventListener('click', function () {
      navigator.clipboard && navigator.clipboard.writeText(getText());
      b.textContent = 'Copied'; setTimeout(function () { b.textContent = 'Copy'; }, 1200);
    });
    return b;
  }
  function field(label, value) {
    var f = el('div', { 'class': 'field' });
    f.appendChild(el('div', { 'class': 'label' }, label));
    var row = el('div', { 'class': 'val' });
    row.appendChild(el('code', null, value));
    row.appendChild(copyBtn(function () { return value; }));
    f.appendChild(row);
    return f;
  }
  function qsParam(name) {
    try { return new URL(location.href).searchParams.get(name) || undefined; } catch (e) { return undefined; }
  }
  function reqJson(method, path, payload) {
    var opts = { method: method, headers: {} };
    if (payload) { opts.headers['content-type'] = 'application/json'; opts.body = JSON.stringify(payload); }
    return fetch(path, opts).then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); });
  }

  function render(o) {
    body.textContent = '';
    if (!o || !o.status) { body.appendChild(el('p', { 'class': 'muted' }, 'Could not reach the mint. Refresh to retry.')); return; }

    if (o.status === 'reserved') {
      body.appendChild(el('span', { 'class': 'pill reserved' }, 'In line'));
      body.appendChild(el('p', { 'class': 'sub', style: 'margin-top:12px' },
        o.message || 'You are in line. Your Pro key mints automatically the moment the mint opens.'));
      body.appendChild(el('p', { 'class': 'muted' }, 'Order ' + (o.orderId || '') + ' — keep this tab open; it claims your key automatically.'));
      return;
    }

    if (o.status === 'pending') {
      body.appendChild(el('span', { 'class': 'pill pending' }, 'Awaiting payment'));
      body.appendChild(field('Amount (BTC)', String(o.amountBtc)));
      body.appendChild(field('Send to address', String(o.address)));
      if (o.payUri) {
        var pay = el('a', { 'class': 'pay', href: o.payUri }, 'Open in wallet →');
        body.appendChild(pay);
      }
      body.appendChild(el('p', { 'class': 'muted center', style: 'margin-top:14px' },
        'Send the exact amount. This page confirms on-chain and unlocks Pro automatically.'));
      return;
    }

    if (o.status === 'paid') {
      // Prefer the mint's server-configured return; else honor a ?return= the
      // product passed (http(s) only — never redirect to a javascript: URI).
      if (o.returnUrl) { location.href = o.returnUrl; return; }
      var back = qsParam('return');
      if (back && o.license) {
        try {
          var bu = new URL(back);
          if (bu.protocol === 'https:' || bu.protocol === 'http:') {
            var sep = back.indexOf('?') === -1 ? '?' : '&';
            location.href = back + sep + 'ce_license_key=' + encodeURIComponent(o.license);
            return;
          }
        } catch (e) { /* fall through to inline display */ }
      }
      body.appendChild(el('span', { 'class': 'pill paid' }, 'Paid — Pro unlocked'));
      body.appendChild(field('Your Pro licence key', String(o.license || '')));
      body.appendChild(el('p', { 'class': 'muted' }, 'Paste this into the product to activate Pro. It is signed offline — no server check needed.'));
      return;
    }

    if (o.status === 'expired') {
      body.appendChild(el('span', { 'class': 'pill expired' }, 'Expired'));
      body.appendChild(el('p', { 'class': 'sub', style: 'margin-top:12px' }, 'This order timed out before payment landed.'));
      var retry = el('button', { 'class': 'pay' }, 'Start over');
      retry.addEventListener('click', function () { start(); });
      body.appendChild(retry);
      return;
    }

    body.appendChild(el('p', { 'class': 'muted' }, 'Status: ' + o.status));
  }

  function poll() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (!orderId) return;
      reqJson('GET', '/order/' + encodeURIComponent(orderId)).then(function (r) {
        render(r.data);
        if (r.data && r.data.status !== 'paid' && r.data.status !== 'expired') poll();
      }).catch(function () { poll(); });
    }, 5000);
  }

  function start() {
    var email = qsParam('email');
    reqJson('POST', '/checkout', email ? { email: email } : {}).then(function (r) {
      orderId = r.data && r.data.orderId;
      render(r.data);
      if (orderId) poll();
    }).catch(function () {
      body.textContent = '';
      body.appendChild(el('p', { 'class': 'muted' }, 'Could not reach the mint. Refresh to retry.'));
    });
  }

  window.start = start;
  start();
})();
</script>
</body>
</html>`
}
