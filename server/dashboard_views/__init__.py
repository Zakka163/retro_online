"""Modular per-menu HTML/JS/CSS views for the Accesspoint Admin Dashboard."""

from .layout import BASE_CSS, CORE_JS, MODAL_TOAST_HTML, SIDEBAR_HTML
from .overview import OVERVIEW_HTML, OVERVIEW_JS
from .devices import DEVICES_HTML, DEVICES_JS
from .games import GAMES_HTML, GAMES_JS
from .rooms import ROOMS_HTML, ROOMS_JS
from .logs import LOGS_HTML, LOGS_JS
from .updates import UPDATES_HTML, UPDATES_JS


def build_dashboard_html() -> str:
    """Assemble the complete single-page dashboard HTML from per-menu modules."""
    sections = "\n".join([
        OVERVIEW_HTML,
        DEVICES_HTML,
        GAMES_HTML,
        ROOMS_HTML,
        LOGS_HTML,
        UPDATES_HTML,
    ])
    scripts = "\n".join([
        CORE_JS,
        OVERVIEW_JS,
        DEVICES_JS,
        GAMES_JS,
        ROOMS_JS,
        LOGS_JS,
        UPDATES_JS,
        "refreshAll();\nsetInterval(refreshAll, 15000);",
    ])
    return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accesspoint</title>
<style>
{BASE_CSS}
</style>
</head>
<body>
<div class="layout">
{SIDEBAR_HTML}
  <div class="main">
    <div class="topbar">
      <h2 id="pageTitle">Ringkasan</h2>
      <button class="btn btn-gray" onclick="refreshAll()">Segarkan</button>
    </div>
{sections}
  </div>
</div>
{MODAL_TOAST_HTML}
<script>
{scripts}
</script>
</body>
</html>
"""

