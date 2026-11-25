"""Updates (Update Rilis) tab HTML & JS."""

UPDATES_HTML = r"""
    <section id="tab-updates" class="hidden">
      <div class="panel">
        <div class="bar"><span class="title">Terbitkan Update</span></div>
        <div class="row" style="flex-wrap:wrap">
          <input type="text" id="updVer" class="field" placeholder="Versi baru (mis. 1.2.2)" style="min-width:170px">
          <input type="text" id="updNotes" class="field" placeholder="Catatan update (opsional)" style="flex:1;min-width:200px">
          <button class="act-btn act-primary" id="btnPublishUpd" onclick="publishUpdate()">Terbitkan</button>
        </div>
      </div>
      <div class="panel" id="updateCard"></div>
    </section>
"""

UPDATES_JS = r"""
function renderUpdate(upd) {
  const el = document.getElementById('updateCard');
  if (!upd || !upd.update_available) {
    el.innerHTML = '<div class="empty">Belum ada rilis update.</div>';
    return;
  }
  el.innerHTML = `
    <div class="row"><div class="title">Versi Aktif</div><div class="right"><span class="pill p-ok">v${esc(upd.version)}</span></div></div>
    <div class="row"><div class="title">Game di Server</div><div class="meta">${state.serverRoms.length} game</div></div>
    <div class="row"><div class="title">Catatan</div><div class="meta">${esc(upd.notes || '-')}</div></div>
  `;
}

async function publishUpdate() {
  const ver = document.getElementById('updVer').value.trim();
  const notes = document.getElementById('updNotes').value.trim();
  if (!ver) return showToast('Isi nomor versi terlebih dahulu');
  const btn = document.getElementById('btnPublishUpd');
  btn.disabled = true;
  btn.textContent = 'Menerbitkan...';
  try {
    await api('/api/admin/updates/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version: ver, notes })
    });
    document.getElementById('updVer').value = '';
    document.getElementById('updNotes').value = '';
    showToast(`Update v${ver} diterbitkan ke semua mesin`);
    await refreshAll();
  } catch (e) {
    showToast('Gagal menerbitkan update');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Terbitkan';
  }
}
"""
