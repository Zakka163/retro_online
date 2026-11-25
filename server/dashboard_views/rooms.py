"""Rooms (Room Aktif) tab HTML & JS."""

ROOMS_HTML = r"""
    <section id="tab-rooms" class="hidden">
      <div class="panel" id="roomsList"></div>
    </section>
"""

ROOMS_JS = r"""
function renderRooms() {
  const el = document.getElementById('roomsList');
  if (!state.rooms.length) {
    el.innerHTML = '<div class="empty">Tidak ada room aktif.</div>';
    return;
  }
  const { slice, pagerHtml } = paginate(state.rooms, 'rooms', 10, 'renderRooms');
  el.innerHTML = slice.map(r => `
    <div class="row">
      <div>
        <div class="title">${esc(r.name)}</div>
        <div class="meta">${esc(r.host_name)}${r.client_name ? ' vs ' + esc(r.client_name) : ''}</div>
      </div>
      <div class="right">
        <span class="pill p-warn">${esc(r.status)}</span>
        <button class="btn btn-red" onclick="closeRoom('${esc(r.room_id)}')">Tutup</button>
      </div>
    </div>
  `).join('') + pagerHtml;
}

function closeRoom(id) {
  openModal({
    title: 'Tutup Room?',
    desc: 'Permainan di room ini akan dihentikan.',
    okText: 'Tutup Room',
    danger: true,
    onOk: async () => {
      await api(`/api/admin/rooms/${encodeURIComponent(id)}`, { method: 'DELETE' });
      showToast('Room ditutup');
      refreshAll();
    }
  });
}
"""

