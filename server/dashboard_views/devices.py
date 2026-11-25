"""Devices (Mesin) tab HTML, remote commands, and config.json editor."""

DEVICES_HTML = r"""
    <section id="tab-devices" class="hidden">
      <div class="panel" id="devicesList"></div>
    </section>
"""

DEVICES_JS = r"""
function renderDevices(id, compact) {
  const el = document.getElementById(id);
  if (!state.devices.length) {
    el.innerHTML = '<div class="empty">Belum ada mesin terhubung.</div>';
    return;
  }
  const { slice, pagerHtml } = compact
    ? { slice: state.devices.slice(0, 5), pagerHtml: '' }
    : paginate(state.devices, 'devices', 10, 'renderDevicesPage');
  el.innerHTML = slice.map(d => {
    const statusHtml = d.online
      ? (d.status === 'in_game'
          ? `<span class="status-line"><span class="status-dot sd-warn"></span>Sedang main · ${esc(d.current_game || '')}</span>`
          : `<span class="status-line"><span class="status-dot sd-ok"></span>Aktif</span>`)
      : `<span class="status-line"><span class="status-dot sd-off"></span>Terakhir aktif ${fmtAgo(d.seconds_ago)}</span>`;

    const infoParts = [
      d.launcher_version ? 'v' + d.launcher_version : '',
      d.games_count ? d.games_count + ' game' : '',
      d.ip_local || ''
    ].filter(Boolean).join(' · ');

    const btns = compact ? '' : `
      <div class="right">
        <button class="act-btn act-primary" onclick="editDeviceConfig('${esc(d.machine_id)}')">Pengaturan</button>
        ${d.online ? '' : `<button class="act-btn act-danger" onclick="deleteDevice('${esc(d.machine_id)}', '${esc(d.player_name)}')">Hapus</button>`}
      </div>
    `;

    return `<div class="row">
      <div>
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <span class="title">${esc(d.player_name)}</span>
          ${statusHtml}
        </div>
        <div class="meta">${esc(infoParts)}</div>
      </div>
      ${btns}
    </div>`;
  }).join('') + pagerHtml;
}

function renderDevicesPage() {
  renderDevices('devicesList', false);
}

function deleteDevice(id, name) {
  openModal({
    title: 'Hapus Mesin?',
    desc: `${name} akan dihapus dari daftar mesin.`,
    okText: 'Hapus',
    danger: true,
    onOk: async () => {
      await api(`/api/admin/devices/${encodeURIComponent(id)}`, { method: 'DELETE' });
      showToast('Mesin dihapus');
      await refreshAll();
    }
  });
}

async function sendCmd(id, command, payload) {
  await api(`/api/admin/devices/${encodeURIComponent(id)}/command`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({command, payload})
  });
  showToast('Perintah dikirim ke mesin');
  refreshAll();
}

function editDeviceConfig(id) {
  const dev = state.devices.find(d => d.machine_id === id);
  if (!dev) return;
  const cfg = dev.config || {};
  const client = cfg.client || {};
  const server = cfg.server || {};
  const ra = cfg.retroarch || {};
  const lg = cfg.logging || {};

  openModal({
    title: 'Pengaturan Mesin',
    desc: dev.player_name,
    wide: true,
    fields: [
      {
        label: 'Nama Mesin',
        type: 'text',
        value: client.player_name || dev.player_name,
        hint: 'Nama yang tampil di daftar room dan catatan sesi.'
      },
      {
        label: 'Alamat Server',
        type: 'text',
        value: server.url || 'http://217.216.146.15:8080',
        hint: 'Alamat server utama untuk cari room dan relay.'
      },
      {
        label: 'Core Utama',
        type: 'select',
        options: ['fbneo', 'mame', 'snes9x', 'genesis_plus_gx', 'fceumm'],
        value: ra.preferred_arcade_core || 'fbneo',
        hint: 'Emulator bawaan yang dipakai saat membuka game arcade.'
      },
      {
        label: 'Buffer Input (Frame)',
        type: 'number',
        value: ra.input_latency_frames ?? 5,
        hint: 'Penunda tombol (0-10). Makin besar makin tahan lag WiFi, tapi respon sedikit lebih lambat.'
      },
      {
        label: 'Check Frames',
        type: 'number',
        value: ra.check_frames ?? 0,
        hint: 'Jarak pengecekan sinkronisasi (0 = nonaktif, disarankan agar tidak crash).'
      },
      {
        label: 'Layar Penuh',
        type: 'toggle',
        value: ra.fullscreen !== false,
        hint: 'Buka game langsung memenuhi seluruh layar TV/monitor.'
      },
      {
        label: 'Stateless Mode',
        type: 'toggle',
        value: ra.stateless_mode !== false,
        hint: 'Kirim input saja tanpa save-state agar stabil saat main beda perangkat.'
      },
      {
        label: 'Sync SRAM',
        type: 'toggle',
        value: Boolean(ra.sync_sram),
        hint: 'Samakan data simpanan game dari Host saat permainan dimulai.'
      },
      {
        label: 'Auto Upload Log',
        type: 'toggle',
        value: lg.auto_upload !== false,
        hint: 'Kirim catatan sesi otomatis ke server untuk pengecekan masalah.'
      }
    ],
    okText: 'Simpan',
    onOk: async ([name, srvUrl, core, latency, chkFrames, fullscreen, stateless, syncSram, autoUpload]) => {
      const updates = {
        'client.player_name': String(name || dev.player_name).trim(),
        'server.url': String(srvUrl || '').trim(),
        'retroarch.preferred_arcade_core': core,
        'retroarch.input_latency_frames': parseInt(latency, 10) || 0,
        'retroarch.check_frames': parseInt(chkFrames, 10) || 0,
        'retroarch.fullscreen': Boolean(fullscreen),
        'retroarch.stateless_mode': Boolean(stateless),
        'retroarch.sync_sram': Boolean(syncSram),
        'logging.auto_upload': Boolean(autoUpload)
      };
      await sendCmd(id, 'set_config', updates);
    }
  });
}
"""
