"""Logs (Log VPS) tab HTML & JS."""

LOGS_HTML = r"""
    <section id="tab-logs" class="hidden">
      <div class="panel" id="logsList"></div>
      <div class="panel hidden" id="logViewer">
        <div class="bar">
          <span class="title" id="logTitle">Log</span>
          <div class="right">
            <label class="switch"><input type="checkbox" id="logErrOnly" onchange="reloadLog()"><span class="slider"></span><span>Error saja</span></label>
            <button class="btn btn-gray" onclick="document.getElementById('logViewer').classList.add('hidden')">Tutup</button>
          </div>
        </div>
        <pre id="logBody"></pre>
      </div>
    </section>
"""

LOGS_JS = r"""
function renderLogs() {
  const el = document.getElementById('logsList');
  if (!state.logs.length) {
    el.innerHTML = '<div class="empty">Belum ada log.</div>';
    return;
  }
  const { slice, pagerHtml } = paginate(state.logs, 'logs', 12, 'renderLogs');
  el.innerHTML = slice.map(l => `
    <div class="row">
      <div>
        <div class="title">${esc(l.filename)}</div>
        <div class="meta">${fmtSize(l.size)}</div>
      </div>
      <div class="right">
        <button class="btn" onclick="viewLog('${esc(l.filename)}')">Lihat</button>
        <a class="btn btn-gray" href="/api/admin/logs/${encodeURIComponent(l.filename)}?download=1">Unduh</a>
      </div>
    </div>
  `).join('') + pagerHtml;
}

async function viewLog(f) {
  state.selectedLog = f;
  await reloadLog();
}

async function reloadLog() {
  if (!state.selectedLog) return;
  const errOnly = document.getElementById('logErrOnly').checked ? '1' : '0';
  const d = await api(`/api/admin/logs/${encodeURIComponent(state.selectedLog)}?errors_only=${errOnly}`);
  document.getElementById('logTitle').textContent = d.filename;
  document.getElementById('logBody').textContent = d.content || '(Kosong)';
  document.getElementById('logViewer').classList.remove('hidden');
}
"""

