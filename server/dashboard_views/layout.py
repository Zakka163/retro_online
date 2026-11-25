"""Shared Apple-minimal CSS, locked sidebar, modal, toast, and core JS helpers."""

BASE_CSS = r"""
  :root {
    --bg: #f5f5f7;
    --card: #ffffff;
    --text: #1d1d1f;
    --muted: #86868b;
    --line: rgba(0, 0, 0, 0.06);
    --blue: #0071e3;
    --green: #28cd41;
    --orange: #ff9500;
    --red: #ff3b30;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif;
    background: var(--bg);
    color: var(--text);
    -webkit-font-smoothing: antialiased;
  }
  .layout { display: flex; min-height: 100vh; }
  aside {
    width: 220px;
    flex-shrink: 0;
    position: sticky;
    top: 0;
    height: 100vh;
    overflow-y: auto;
    background: rgba(255, 255, 255, 0.72);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-right: 1px solid var(--line);
    padding: 24px 14px;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }
  .sidebar-foot {
    margin-top: auto;
    padding-top: 12px;
    border-top: 1px solid var(--line);
  }
  .sidebar-foot button {
    width: 100%;
    text-align: left;
    border: none;
    background: transparent;
    color: var(--red);
    padding: 9px 12px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
  }
  .sidebar-foot button:hover { background: rgba(255, 59, 48, 0.08); }
  .brand { display: flex; align-items: center; gap: 10px; padding: 0 10px; }
  .brand h1 { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -0.02em; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); }
  .nav { display: flex; flex-direction: column; gap: 4px; }
  .nav button {
    width: 100%;
    text-align: left;
    border: none;
    background: transparent;
    color: var(--text);
    padding: 9px 12px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s ease;
  }
  .nav button:hover { background: rgba(0, 0, 0, 0.04); }
  .nav button.active {
    background: rgba(0, 113, 227, 0.12);
    color: var(--blue);
    font-weight: 600;
  }
  .main { flex: 1; min-width: 0; width: 100%; padding: 28px 32px 60px; }
  .topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 22px;
  }
  .topbar h2 { margin: 0; font-size: 22px; font-weight: 600; letter-spacing: -0.02em; }
  @media (max-width: 720px) {
    .layout { flex-direction: column; }
    aside { width: 100%; height: auto; position: static; border-right: none; border-bottom: 1px solid var(--line); padding: 14px; }
    .nav { flex-direction: row; flex-wrap: wrap; }
    .nav button { width: auto; }
    .sidebar-foot { margin-top: 0; padding-top: 8px; }
    .main { padding: 18px 14px 40px; }
    .row { flex-wrap: wrap; padding: 14px 16px; }
    .modal { padding: 18px; }
    .modal .stack.grid-2 { grid-template-columns: 1fr; }
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 14px;
    margin-bottom: 22px;
  }
  .card {
    background: var(--card);
    border-radius: 16px;
    padding: 18px 20px;
    border: 1px solid var(--line);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
  }
  .card .k { font-size: 12px; color: var(--muted); font-weight: 500; margin-bottom: 6px; }
  .card .v { font-size: 28px; font-weight: 600; letter-spacing: -0.02em; }
  .panel {
    background: var(--card);
    border-radius: 18px;
    border: 1px solid var(--line);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
    overflow: hidden;
    margin-bottom: 18px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 15px 20px;
    border-bottom: 1px solid var(--line);
    gap: 12px;
  }
  .row:last-child { border-bottom: none; }
  .title { font-size: 15px; font-weight: 500; }
  .meta { font-size: 12px; color: var(--muted); margin-top: 2px; }
  .right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .pill {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
  }
  .p-ok { background: rgba(40, 205, 65, 0.12); color: #198754; }
  .p-warn { background: rgba(255, 149, 0, 0.14); color: #b45309; }
  .p-err { background: rgba(255, 59, 48, 0.12); color: var(--red); }
  .p-off { background: rgba(134, 134, 139, 0.12); color: var(--muted); }
  .btn {
    border: none;
    background: rgba(0, 113, 227, 0.1);
    color: var(--blue);
    padding: 6px 12px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
  }
  .btn:hover { background: rgba(0, 113, 227, 0.16); }
  .btn-gray { background: rgba(134, 134, 139, 0.12); color: var(--text); }
  .btn-gray:hover { background: rgba(134, 134, 139, 0.2); }
  .btn-red { background: rgba(255, 59, 48, 0.12); color: var(--red); }
  .btn-red:hover { background: rgba(255, 59, 48, 0.2); }
  .empty { padding: 36px 20px; text-align: center; color: var(--muted); font-size: 14px; }
  .hidden { display: none; }
  pre {
    margin: 0;
    padding: 18px 20px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12px;
    line-height: 1.5;
    max-height: 440px;
    overflow: auto;
    background: #fafafa;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    border-bottom: 1px solid var(--line);
  }
  .field {
    appearance: none;
    -webkit-appearance: none;
    background: #f5f5f7;
    color: var(--text);
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
  }
  .field:focus {
    background: #fff;
    border-color: var(--blue);
    box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.16);
  }
  select.field {
    padding-right: 30px;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2386868b' d='M2.5 4.5 6 8l3.5-3.5'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    cursor: pointer;
  }
  .file-pick {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background: #f5f5f7;
    border: 1px solid rgba(0, 0, 0, 0.08);
    border-radius: 10px;
    padding: 5px 12px 5px 6px;
    cursor: pointer;
    font-size: 13px;
  }
  .file-pick:hover { background: #ececef; }
  .file-pick span.tag {
    background: #fff;
    padding: 4px 10px;
    border-radius: 7px;
    font-weight: 500;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06);
  }
  .file-pick span.fname { color: var(--muted); max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .switch {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 12px;
    color: var(--muted);
    user-select: none;
  }
  .switch input { position: absolute; opacity: 0; width: 0; height: 0; }
  .slider {
    width: 34px;
    height: 20px;
    background: rgba(120, 120, 128, 0.24);
    border-radius: 999px;
    position: relative;
    transition: background 0.2s ease;
  }
  .slider::after {
    content: "";
    position: absolute;
    top: 2px; left: 2px;
    width: 16px; height: 16px;
    border-radius: 50%;
    background: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    transition: transform 0.2s ease;
  }
  .switch input:checked + .slider { background: var(--green); }
  .switch input:checked + .slider::after { transform: translateX(14px); }
  .modal-bg {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.28);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    z-index: 100;
  }
  .modal-bg.hidden { display: none; }
  .modal {
    width: 100%;
    max-width: 420px;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    background: rgba(255, 255, 255, 0.96);
    border-radius: 18px;
    padding: 22px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.6);
  }
  .modal.wide { max-width: 620px; }
  .modal .stack.grid-2 {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
  }
  .f-item { display: flex; flex-direction: column; gap: 6px; position: relative; }
  .f-item.full { grid-column: 1 / -1; }
  .f-head { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; color: var(--text); }
  .info-wrap { position: relative; display: inline-flex; align-items: center; }
  .info-icon {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 1px solid rgba(0, 0, 0, 0.18);
    background: #fff;
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    padding: 0;
  }
  .info-icon:hover, .info-wrap.open .info-icon {
    border-color: var(--blue);
    color: var(--blue);
    background: rgba(0, 113, 227, 0.08);
  }
  .info-tip {
    display: none;
    position: absolute;
    left: 0;
    top: calc(100% + 6px);
    width: 230px;
    background: rgba(29, 29, 31, 0.94);
    color: #fff;
    font-size: 12px;
    font-weight: 400;
    line-height: 1.4;
    padding: 8px 10px;
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
    z-index: 300;
  }
  .info-wrap:hover .info-tip, .info-wrap.open .info-tip { display: block; }
  .status-line {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
    color: var(--muted);
  }
  .status-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
  .sd-ok { background: var(--green); }
  .sd-warn { background: var(--orange); }
  .sd-off { background: #c7c7cc; }
  .act-btn {
    border: 1px solid rgba(0, 0, 0, 0.1);
    background: #fff;
    color: var(--text);
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  }
  .act-btn:hover { background: #f5f5f7; }
  .act-primary { background: var(--blue); color: #fff; border-color: var(--blue); }
  .act-primary:hover { opacity: 0.92; background: var(--blue); }
  .act-danger { color: var(--red); border-color: rgba(255, 59, 48, 0.28); }
  .act-danger:hover { background: rgba(255, 59, 48, 0.06); }
  .modal h3 { margin: 0 0 6px; font-size: 17px; font-weight: 600; }
  .modal p { margin: 0 0 16px; font-size: 13px; color: var(--muted); }
  .modal .stack { display: flex; flex-direction: column; gap: 10px; margin-bottom: 18px; }
  .modal .actions { display: flex; justify-content: flex-end; gap: 8px; }
  .toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(29, 29, 31, 0.88);
    backdrop-filter: blur(12px);
    color: #fff;
    padding: 9px 18px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 500;
    z-index: 200;
    box-shadow: 0 6px 20px rgba(0,0,0,0.18);
  }
  .toast.hidden { display: none; }
  .pager {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    border-top: 1px solid var(--line);
    background: #fafafa;
    font-size: 12px;
    color: var(--muted);
  }
  .pager .right { gap: 6px; }
  .act-btn:disabled { opacity: 0.4; cursor: default; }
"""

SIDEBAR_HTML = r"""
  <aside>
    <div class="brand">
      <span class="dot" id="srvDot"></span>
      <h1>Accesspoint</h1>
    </div>
    <div class="nav" id="tabs">
      <button class="active" data-tab="overview" data-title="Ringkasan">Ringkasan</button>
      <button data-tab="devices" data-title="Mesin">Mesin</button>
      <button data-tab="games" data-title="Game">Game</button>
      <button data-tab="rooms" data-title="Room">Room</button>
      <button data-tab="logs" data-title="Log">Log</button>
      <button data-tab="updates" data-title="Update">Update</button>
    </div>
    <div class="sidebar-foot">
      <button onclick="logoutAdmin()">Keluar</button>
    </div>
  </aside>
"""

MODAL_TOAST_HTML = r"""
<div class="modal-bg hidden" id="modalBg" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <h3 id="modalTitle"></h3>
    <p id="modalDesc" class="hidden"></p>
    <div class="stack" id="modalFields"></div>
    <div class="actions">
      <button class="btn btn-gray" onclick="closeModal()">Batal</button>
      <button class="btn" id="modalOk">Simpan</button>
    </div>
  </div>
</div>
<div class="toast hidden" id="toast"></div>
"""

CORE_JS = r"""
let state = { overview: {}, devices: [], games: [], serverRoms: [], rooms: [], logs: [], selectedLog: null, page: { devices: 1, games: 1, rooms: 1, logs: 1 } };

function paginate(items, key, perPage, renderFnName) {
  const totalPages = Math.max(1, Math.ceil(items.length / perPage));
  let cur = state.page[key] || 1;
  if (cur > totalPages) cur = totalPages;
  if (cur < 1) cur = 1;
  state.page[key] = cur;
  const start = (cur - 1) * perPage;
  const slice = items.slice(start, start + perPage);
  const pagerHtml = items.length <= perPage ? '' : `
    <div class="pager">
      <span>Halaman ${cur} dari ${totalPages} · ${items.length} item</span>
      <div class="right">
        <button class="act-btn" ${cur <= 1 ? 'disabled' : ''} onclick="setPage('${key}', ${cur - 1}, '${renderFnName}')">Sebelumnya</button>
        <button class="act-btn" ${cur >= totalPages ? 'disabled' : ''} onclick="setPage('${key}', ${cur + 1}, '${renderFnName}')">Berikutnya</button>
      </div>
    </div>`;
  return { slice, pagerHtml };
}

function setPage(key, p, fnName) {
  state.page[key] = p;
  if (typeof window[fnName] === 'function') window[fnName]();
}

document.querySelectorAll('#tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#tabs button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    document.getElementById('pageTitle').textContent = btn.dataset.title || btn.textContent;
    document.querySelectorAll('section').forEach(s => s.classList.add('hidden'));
    document.getElementById('tab-' + tab).classList.remove('hidden');
  });
});

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function fmtAgo(sec) {
  if (sec < 60) return 'baru saja';
  if (sec < 3600) return Math.round(sec / 60) + ' menit lalu';
  return Math.round(sec / 3600) + ' jam lalu';
}

function fmtSize(b) {
  if (!b) return '0 KB';
  if (b < 1048576) return (b / 1024).toFixed(0) + ' KB';
  return (b / 1048576).toFixed(1) + ' MB';
}

async function api(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return await res.json();
}

async function refreshAll() {
  try {
    const [ov, dv, gm, sr, rm, lg] = await Promise.all([
      api('/api/admin/overview'),
      api('/api/admin/devices'),
      api('/api/admin/games'),
      api('/api/admin/roms'),
      api('/api/rooms?status=all'),
      api('/api/admin/logs')
    ]);
    state.overview = ov;
    state.devices = dv.devices || [];
    state.games = gm.games || [];
    state.serverRoms = sr.roms || [];
    state.rooms = rm.rooms || [];
    state.logs = lg.logs || [];
    document.getElementById('srvDot').style.background = 'var(--green)';
    render();
  } catch (e) {
    document.getElementById('srvDot').style.background = 'var(--red)';
  }
}

function render() {
  renderOverview();
  renderDevices('overviewDevices', true);
  renderDevices('devicesList', false);
  renderGames();
  renderRooms();
  renderLogs();
  renderUpdate(state.overview.update || {});
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => t.classList.add('hidden'), 2600);
}

function makeInfoBadge(hint) {
  const wrap = document.createElement('span');
  wrap.className = 'info-wrap';
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'info-icon';
  btn.textContent = 'i';
  btn.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const wasOpen = wrap.classList.contains('open');
    document.querySelectorAll('.info-wrap.open').forEach(el => el.classList.remove('open'));
    if (!wasOpen) wrap.classList.add('open');
  };
  const tip = document.createElement('div');
  tip.className = 'info-tip';
  tip.textContent = hint;
  wrap.appendChild(btn);
  wrap.appendChild(tip);
  return wrap;
}

function openModal({ title, desc = '', fields = [], okText = 'Simpan', danger = false, wide = false, onOk }) {
  document.getElementById('modalTitle').textContent = title;
  const modalEl = document.querySelector('#modalBg .modal');
  modalEl.classList.toggle('wide', Boolean(wide));
  const d = document.getElementById('modalDesc');
  d.textContent = desc;
  d.classList.toggle('hidden', !desc);
  const box = document.getElementById('modalFields');
  box.innerHTML = '';
  box.className = wide ? 'stack grid-2' : 'stack';
  box.style.maxHeight = '65vh';
  box.style.overflowY = 'auto';
  box.style.paddingRight = '2px';
  const inputs = [];
  for (const f of fields) {
    const item = document.createElement('div');
    item.className = 'f-item' + (f.type === 'toggle' ? ' full' : '');
    if (f.type === 'toggle') {
      const row = document.createElement('label');
      row.className = 'switch';
      row.style.justifyContent = 'space-between';
      row.style.width = '100%';
      row.style.color = 'var(--text)';
      row.style.fontSize = '13px';
      row.style.fontWeight = '500';
      row.style.padding = '4px 0';
      const left = document.createElement('span');
      left.style.display = 'inline-flex';
      left.style.alignItems = 'center';
      left.style.gap = '6px';
      const txt = document.createElement('span');
      txt.textContent = f.label || '';
      left.appendChild(txt);
      if (f.hint) left.appendChild(makeInfoBadge(f.hint));
      const chk = document.createElement('input');
      chk.type = 'checkbox';
      chk.checked = Boolean(f.value);
      const sld = document.createElement('span');
      sld.className = 'slider';
      row.appendChild(left);
      row.appendChild(chk);
      row.appendChild(sld);
      item.appendChild(row);
      box.appendChild(item);
      inputs.push({ get: () => chk.checked, focus: () => {} });
      continue;
    }
    if (f.label) {
      const head = document.createElement('div');
      head.className = 'f-head';
      const lbl = document.createElement('span');
      lbl.textContent = f.label;
      head.appendChild(lbl);
      if (f.hint) head.appendChild(makeInfoBadge(f.hint));
      item.appendChild(head);
    }
    let el;
    if (f.type === 'select') {
      el = document.createElement('select');
      el.className = 'field';
      for (const opt of f.options) {
        const o = document.createElement('option');
        o.value = opt; o.textContent = opt;
        if (opt === f.value) o.selected = true;
        el.appendChild(o);
      }
    } else {
      el = document.createElement('input');
      el.type = f.type || 'text';
      el.className = 'field';
      el.placeholder = f.placeholder || '';
      el.value = f.value ?? '';
    }
    item.appendChild(el);
    box.appendChild(item);
    inputs.push({ get: () => el.value, focus: () => el.focus() });
  }
  const okBtn = document.getElementById('modalOk');
  okBtn.textContent = okText;
  okBtn.className = danger ? 'btn btn-red' : 'btn';
  okBtn.onclick = async () => {
    await onOk(inputs.map(i => i.get()));
    closeModal();
  };
  document.getElementById('modalBg').classList.remove('hidden');
  if (inputs[0]) inputs[0].focus();
}

function closeModal() {
  document.getElementById('modalBg').classList.add('hidden');
}

function logoutAdmin() {
  openModal({
    title: 'Keluar dari Accesspoint?',
    okText: 'Keluar',
    danger: true,
    onOk: async () => {
      try {
        await fetch('/admin/logout', {
          headers: { 'Authorization': 'Basic ' + btoa('logout:logout') }
        });
      } catch (e) {}
      document.body.innerHTML = '<div style="display:flex;min-height:100vh;align-items:center;justify-content:center;flex-direction:column;gap:14px;font-family:-apple-system,sans-serif;background:#f5f5f7;color:#1d1d1f"><div style="font-size:20px;font-weight:600">Anda telah keluar</div><button onclick="location.reload()" style="border:none;background:#0071e3;color:#fff;padding:9px 18px;border-radius:999px;font-size:14px;font-weight:500;cursor:pointer">Masuk Kembali</button></div>';
    }
  });
}
"""

