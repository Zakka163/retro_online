"""Overview (Ringkasan) tab HTML & JS."""

OVERVIEW_HTML = r"""
    <section id="tab-overview">
      <div class="cards" id="overviewCards"></div>
      <div class="panel" id="overviewDevices"></div>
    </section>
"""

OVERVIEW_JS = r"""
function renderOverview() {
  const ov = state.overview;
  const upd = ov.update || {};
  document.getElementById('overviewCards').innerHTML = `
    <div class="card"><div class="k">Mesin Aktif</div><div class="v">${ov.devices_online || 0}</div></div>
    <div class="card"><div class="k">Room</div><div class="v">${ov.rooms_active || 0}</div></div>
    <div class="card"><div class="k">Game</div><div class="v">${state.serverRoms.length || state.games.length}</div></div>
    <div class="card"><div class="k">Versi</div><div class="v">${esc(upd.version || '1.0')}</div></div>
  `;
}
"""

