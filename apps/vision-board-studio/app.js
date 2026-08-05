/* Vision Board Studio — dependency-free client app.
   Model: a board = { name, banner, aspect, tiles[] }.
   Each tile carries a `faithful` layer (the restored 2017 image) and a `fork`
   layer (your 2026 re-imagining), plus a `salvage` fragment we can always revert to.
   Everything lives client-side; Save/Load is JSON, persistence is localStorage. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const LS_KEY = 'vbs.board.v1';

const state = {
  board: null,
  layer: 'faithful',     // faithful | fork | split
  output: 'canvas',      // canvas | poster | kit
  editing: null,         // tile id
};

/* ---------- load ---------- */
async function boot() {
  const saved = localStorage.getItem(LS_KEY);
  if (saved) {
    try { state.board = JSON.parse(saved); } catch { /* ignore */ }
  }
  if (!state.board) {
    const res = await fetch('boards/tony-2017.json');
    state.board = await res.json();
  }
  wireUI();
  render();
}

/* ---------- render ---------- */
function render() {
  const b = state.board;
  $('#boardName').value = b.name || 'Untitled board';
  $('#banner').textContent = b.banner || '';
  $('#originNote').textContent = b.origin?.note || '';
  const board = $('#board');
  board.style.aspectRatio = String(b.aspect || 1.6);
  board.innerHTML = '';

  b.tiles.forEach((t) => board.appendChild(renderTile(t)));

  // toggle output sections
  $('#stage').hidden = state.output === 'kit';
  $('#kit').hidden = state.output !== 'kit';
  if (state.output === 'kit') renderKit();

  // active states
  $$('.seg-btn').forEach((el) => el.classList.toggle('is-active', el.dataset.layer === state.layer));
  ['btnPoster', 'btnKit', 'btnCanvas'].forEach((id) => {
    const map = { btnPoster: 'poster', btnKit: 'kit', btnCanvas: 'canvas' };
    $('#' + id).classList.toggle('is-active', state.output === map[id]);
  });
  save();
}

function layerImg(t, which) {
  const l = t[which] || {};
  return l.img || (which === 'faithful' ? t.salvage : '');
}

function renderTile(t) {
  const el = document.createElement('div');
  el.className = 'tile';
  el.style.left = t.pos.left + '%';
  el.style.top = t.pos.top + '%';
  el.style.width = t.pos.width + '%';
  el.style.height = t.pos.height + '%';
  el.dataset.id = t.id;

  const faith = layerImg(t, 'faithful');
  const fork = layerImg(t, 'fork');

  if (state.layer === 'split') {
    el.classList.add('split');
    el.innerHTML =
      `<div class="half faithful">${imgOrPh(faith, t)}<span class="tag">2017</span></div>` +
      `<div class="half fork">${imgOrPh(fork, t, true)}<span class="tag">2026</span></div>`;
  } else {
    const src = state.layer === 'fork' ? fork : faith;
    const isForkEmpty = state.layer === 'fork' && !fork;
    el.innerHTML = imgOrPh(src, t, isForkEmpty) +
      `<span class="pin"></span>` +
      (state.layer === 'faithful' && (t.faithful?.img || t.salvage) === t.salvage
        ? `<span class="badge">salvaged</span>` : '') +
      `<span class="cap">${escapeHtml(currentCaption(t))}</span>`;
  }

  el.addEventListener('click', () => openEditor(t.id));
  return el;
}

function imgOrPh(src, t, isFork) {
  if (src) return `<img src="${src}" alt="${escapeHtml(t.title)}" loading="lazy" />`;
  const label = isFork ? (t.fork?.prompt || t.theme) : (t.desc || t.title);
  return `<div class="ph">${escapeHtml(label)}</div>`;
}
function currentCaption(t) {
  if (state.layer === 'fork') return t.fork?.caption || t.title;
  return t.faithful?.caption || t.title;
}
function tileById(id) { return state.board.tiles.find((x) => x.id === id); }

/* ---------- reprint kit ---------- */
function renderKit() {
  const b = state.board;
  const kit = $('#kit');
  const map = b.tiles.map((t) =>
    `<div class="m" style="left:${t.pos.left}%;top:${t.pos.top}%;width:${t.pos.width}%;height:${t.pos.height}%">${escapeHtml(t.title)}</div>`
  ).join('');
  const cards = b.tiles.map((t, i) => {
    const src = layerImg(t, 'faithful') || t.salvage;
    return `<div class="kit-card">
      <img src="${src}" alt="${escapeHtml(t.title)}" />
      <div class="k-t">${i + 1}. ${escapeHtml(t.faithful?.caption || t.title)}</div>
      <div class="k-s">${escapeHtml(t.theme || '')} — ${escapeHtml(t.desc || '')}</div>
    </div>`;
  }).join('');
  kit.innerHTML = `<h2>Reprint kit — ${escapeHtml(b.name)}</h2>
    <p class="muted">Layout map (pin positions), then each tile at cut size. Print this page, cut, and pin to a corkboard.</p>
    <div class="kit-map" style="aspect-ratio:${b.aspect}">${map}</div>
    <div class="kit-list">${cards}</div>`;
}

/* ---------- editor ---------- */
function openEditor(id) {
  state.editing = id;
  const t = tileById(id);
  const which = state.layer === 'fork' ? 'fork' : 'faithful';
  $('#editor').hidden = false;
  $('#edTitle').textContent = t.title;
  $('#edLayer').textContent = which === 'fork' ? '2026 Fork' : 'Faithful (2017)';
  $('#edCaption').value = (t[which]?.caption) || (which === 'faithful' ? t.title : '');
  $('#edTheme').value = t.theme || '';
  $('#edUrl').value = t[which]?.img && !t[which].img.startsWith('data:') ? t[which].img : '';
  $('#edImg').src = layerImg(t, which) || t.salvage;
  $('#edDesc').textContent = t.desc || '';
  const q = encodeURIComponent(t.faithful?.search || t.title);
  $('#edSearch').href = `https://www.google.com/search?tbm=isch&q=${q}`;
}
function closeEditor() { $('#editor').hidden = true; state.editing = null; }

function applyEdit(patch) {
  const t = tileById(state.editing);
  const which = state.layer === 'fork' ? 'fork' : 'faithful';
  t[which] = t[which] || {};
  Object.assign(t[which], patch.layer || {});
  if (patch.theme !== undefined) t.theme = patch.theme;
  render();
  openEditor(state.editing); // refresh preview
}

/* ---------- ingest: new board from a photo ---------- */
const ingest = { img: null, boxes: [], drawing: null };
function startIngest(file) {
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    ingest.img = img; ingest.boxes = [];
    $('#ingest').hidden = false;
    $('#stage').hidden = true; $('#kit').hidden = true;
    const wrap = $('#ingestCanvasWrap');
    wrap.innerHTML = '';
    wrap.appendChild(img);
    img.style.maxWidth = '100%';
    bindIngestDraw(wrap, img);
    updateIngestCount();
  };
  img.src = url;
}
function bindIngestDraw(wrap, img) {
  let start = null, boxEl = null;
  const rectOf = () => img.getBoundingClientRect();
  wrap.onmousedown = (e) => {
    if (e.target.classList.contains('x')) return;
    const r = rectOf();
    start = { x: e.clientX - r.left, y: e.clientY - r.top };
    boxEl = document.createElement('div');
    boxEl.className = 'ingest-box';
    wrap.appendChild(boxEl);
  };
  wrap.onmousemove = (e) => {
    if (!start) return;
    const r = rectOf();
    const x = e.clientX - r.left, y = e.clientY - r.top;
    const l = Math.min(start.x, x), t = Math.min(start.y, y);
    boxEl.style.left = l + 'px'; boxEl.style.top = t + 'px';
    boxEl.style.width = Math.abs(x - start.x) + 'px';
    boxEl.style.height = Math.abs(y - start.y) + 'px';
  };
  wrap.onmouseup = (e) => {
    if (!start || !boxEl) { start = null; return; }
    const r = rectOf();
    const w = parseFloat(boxEl.style.width) || 0, h = parseFloat(boxEl.style.height) || 0;
    if (w < 14 || h < 14) { boxEl.remove(); start = null; return; }
    const box = {
      left: (parseFloat(boxEl.style.left) / r.width) * 100,
      top: (parseFloat(boxEl.style.top) / r.height) * 100,
      width: (w / r.width) * 100,
      height: (h / r.height) * 100,
    };
    ingest.boxes.push(box);
    const x = document.createElement('span'); x.className = 'x'; x.textContent = '×';
    x.onclick = (ev) => { ev.stopPropagation(); const i = ingest.boxes.indexOf(box); if (i > -1) ingest.boxes.splice(i, 1); boxEl.remove(); updateIngestCount(); };
    boxEl.appendChild(x);
    start = null; boxEl = null;
    updateIngestCount();
  };
}
function updateIngestCount() { $('#ingestCount').textContent = `${ingest.boxes.length} tile${ingest.boxes.length === 1 ? '' : 's'}`; }

function buildBoardFromIngest() {
  const img = ingest.img;
  const aspect = img.naturalWidth / img.naturalHeight;
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const tiles = ingest.boxes.map((box, i) => {
    const sx = box.left / 100 * img.naturalWidth;
    const sy = box.top / 100 * img.naturalHeight;
    const sw = box.width / 100 * img.naturalWidth;
    const sh = box.height / 100 * img.naturalHeight;
    // upscale 2x for a crisper salvage fragment
    canvas.width = Math.round(sw * 2); canvas.height = Math.round(sh * 2);
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
    const data = canvas.toDataURL('image/png');
    return {
      id: 'tile-' + (i + 1), theme: '', title: 'Tile ' + (i + 1), desc: '',
      salvage: data,
      faithful: { img: data, caption: '', search: '' },
      fork: { img: '', caption: '', prompt: '2026: what does this become now?' },
      pos: box,
    };
  });
  state.board = {
    schema: 1, id: 'ingested-' + tiles.length, name: 'New board',
    banner: 'WHAT ARE YOU GRATEFUL FOR?', aspect: Math.round(aspect * 1e4) / 1e4,
    origin: { note: 'Built from an uploaded photo. Draw-mapped tiles; swap in high-res images.' },
    tiles,
  };
  $('#ingest').hidden = true;
  state.output = 'canvas'; state.layer = 'faithful';
  render();
  toast(`Built a board with ${tiles.length} tiles`);
}

/* ---------- persistence ---------- */
function save() { try { localStorage.setItem(LS_KEY, JSON.stringify(state.board)); } catch { /* quota */ } }
function exportJson() {
  const blob = new Blob([JSON.stringify(state.board, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = (state.board.name || 'vision-board').replace(/\s+/g, '-').toLowerCase() + '.json';
  a.click();
}
function importJson(file) {
  const r = new FileReader();
  r.onload = () => { try { state.board = JSON.parse(r.result); state.output = 'canvas'; render(); toast('Loaded'); } catch { toast('Not a valid board file'); } };
  r.readAsText(file);
}

/* ---------- util ---------- */
function escapeHtml(s) { return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function fileToDataUrl(file, cb) { const r = new FileReader(); r.onload = () => cb(r.result); r.readAsDataURL(file); }
let toastT;
function toast(msg) { const el = $('#toast'); el.textContent = msg; el.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => (el.hidden = true), 2200); }

/* ---------- wiring ---------- */
function wireUI() {
  $$('.seg-btn').forEach((el) => el.addEventListener('click', () => { state.layer = el.dataset.layer; state.output = state.output === 'kit' ? 'canvas' : state.output; render(); }));
  $('#btnCanvas').addEventListener('click', () => { state.output = 'canvas'; render(); });
  $('#btnKit').addEventListener('click', () => { state.output = 'kit'; render(); });
  $('#btnPoster').addEventListener('click', () => { state.output = 'canvas'; render(); setTimeout(() => window.print(), 60); });

  $('#boardName').addEventListener('input', (e) => { state.board.name = e.target.value; save(); });
  $('#banner').addEventListener('input', (e) => { state.board.banner = e.target.textContent; save(); });

  $('#edClose').addEventListener('click', closeEditor);
  $('#edCaption').addEventListener('input', (e) => applyEdit({ layer: { caption: e.target.value } }));
  $('#edTheme').addEventListener('input', (e) => applyEdit({ theme: e.target.value }));
  $('#edUrl').addEventListener('change', (e) => applyEdit({ layer: { img: e.target.value.trim() } }));
  $('#edUpload').addEventListener('change', (e) => { const f = e.target.files[0]; if (f) fileToDataUrl(f, (d) => applyEdit({ layer: { img: d } })); });
  $('#edRevert').addEventListener('click', () => { const t = tileById(state.editing); const which = state.layer === 'fork' ? 'fork' : 'faithful'; t[which].img = which === 'faithful' ? t.salvage : ''; render(); openEditor(state.editing); });

  $('#ingestFile').addEventListener('change', (e) => { const f = e.target.files[0]; if (f) startIngest(f); });
  $('#ingestDone').addEventListener('click', () => { if (ingest.boxes.length) buildBoardFromIngest(); else toast('Draw at least one tile'); });
  $('#ingestCancel').addEventListener('click', () => { $('#ingest').hidden = true; state.output = 'canvas'; render(); });

  $('#btnExport').addEventListener('click', exportJson);
  $('#importFile').addEventListener('change', (e) => { const f = e.target.files[0]; if (f) importJson(f); });

  window.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeEditor(); });
}

boot();
