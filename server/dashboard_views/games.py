"""Games (Game & ROM) tab HTML & JS."""

GAMES_HTML = r"""
    <section id="tab-games" class="hidden">
      <div class="panel">
        <div class="bar">
          <span class="title">Tambah Game</span>
        </div>
        <div class="row" style="flex-wrap:wrap">
          <label class="file-pick">
            <input type="file" id="romFile" accept=".zip,.7z" style="display:none" onchange="onRomFilePick(this)">
            <span class="tag">Pilih File</span>
            <span class="fname" id="romFileLabel">Belum ada file</span>
          </label>
          <input type="text" id="romName" class="field" placeholder="Nama game (opsional)" style="min-width:190px">
          <select id="romCore" class="field">
            <option value="fbneo">fbneo</option>
            <option value="mame">mame</option>
            <option value="snes9x">snes9x</option>
            <option value="genesis_plus_gx">genesis_plus_gx</option>
            <option value="fceumm">fceumm</option>
          </select>
          <button class="btn" id="btnUploadRom" onclick="uploadRom()">Unggah</button>
        </div>
      </div>
      <div class="panel" id="serverRomsList"></div>
    </section>
"""

GAMES_JS = r"""
function renderGames() {
  const srEl = document.getElementById('serverRomsList');
  const onlineDevs = state.devices.filter(d => d.online);

  if (!state.serverRoms.length) {
    srEl.innerHTML = '<div class="empty">Belum ada game di server.</div>';
    return;
  }
  const { slice, pagerHtml } = paginate(state.serverRoms, 'games', 10, 'renderGames');
  srEl.innerHTML = slice.map(r => {
    const hasCount = onlineDevs.filter(d => (d.games || []).some(g => (g.filename || (g.game_id + '.zip')) === r.filename)).length;
    const syncPill = onlineDevs.length === 0
      ? ''
      : (hasCount === onlineDevs.length
          ? `<span class="pill p-ok">Sinkron (${hasCount}/${onlineDevs.length})</span>`
          : `<span class="pill p-warn">Sync ${hasCount}/${onlineDevs.length}</span>`);
    return `
    <div class="row">
      <div>
        <div class="title">${esc(r.display_name)}</div>
        <div class="meta">${esc(r.filename)} · ${esc(r.core)} · ${fmtSize(r.size)}</div>
      </div>
      <div class="right">
        ${syncPill}
        <button class="btn" onclick="editRom('${esc(r.filename)}', '${esc(r.display_name)}', '${esc(r.core)}')">Edit</button>
        <button class="btn btn-red" onclick="deleteRom('${esc(r.filename)}')">Hapus</button>
      </div>
    </div>`;
  }).join('') + pagerHtml;
}

function onRomFilePick(el) {
  document.getElementById('romFileLabel').textContent = (el.files && el.files.length) ? el.files[0].name : 'Belum ada file';
}

async function uploadRom() {
  const fileEl = document.getElementById('romFile');
  if (!fileEl.files || !fileEl.files.length) return showToast('Pilih file game terlebih dahulu');
  const file = fileEl.files[0];
  const name = document.getElementById('romName').value.trim();
  const core = document.getElementById('romCore').value;
  const btn = document.getElementById('btnUploadRom');
  btn.disabled = true;
  btn.textContent = 'Mengunggah...';
  try {
    const url = `/api/admin/roms/upload?filename=${encodeURIComponent(file.name)}&display_name=${encodeURIComponent(name)}&core=${encodeURIComponent(core)}`;
    const res = await fetch(url, { method: 'POST', body: file });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    fileEl.value = '';
    document.getElementById('romFileLabel').textContent = 'Belum ada file';
    document.getElementById('romName').value = '';
    showToast('Game berhasil diunggah');
    await refreshAll();
  } catch (e) {
    showToast('Gagal mengunggah');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Unggah';
  }
}

function editRom(filename, curName, curCore) {
  openModal({
    title: 'Edit Game',
    desc: filename,
    fields: [
      { type: 'text', placeholder: 'Nama game', value: curName },
      { type: 'select', options: ['fbneo', 'mame', 'snes9x', 'genesis_plus_gx', 'fceumm'], value: curCore }
    ],
    okText: 'Simpan',
    onOk: async ([display_name, core]) => {
      await api(`/api/admin/roms/${encodeURIComponent(filename)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: display_name.trim(), core })
      });
      showToast('Game diperbarui');
      await refreshAll();
    }
  });
}

function deleteRom(filename) {
  openModal({
    title: 'Hapus Game?',
    desc: `${filename} akan dihapus dari daftar game.`,
    okText: 'Hapus',
    danger: true,
    onOk: async () => {
      await api(`/api/admin/roms/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      showToast('Game dihapus');
      await refreshAll();
    }
  });
}
"""

