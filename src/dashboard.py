"""
Genera un dashboard HTML a partir de data/latest.json.

Uso:
    source venv/bin/activate
    python3 src/dashboard.py
"""

import datetime
import json
from collections import OrderedDict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "latest.json"
OUTPUT_PATH = BASE_DIR / "reports" / "dashboard.html"

ISSUE_LABELS = {
    "pagina_roto": "Página con error HTTP",
    "pagina_no_verificable": "Página no verificable (posible bloqueo anti-bot)",
    "cadena_redirecciones": "Cadena larga de redirecciones",
    "meta_titulo_ausente": "Meta título ausente",
    "meta_titulo_largo_incorrecto": "Meta título fuera de rango",
    "meta_titulo_duplicado": "Meta título duplicado",
    "meta_descripcion_ausente": "Meta descripción ausente",
    "meta_descripcion_largo_incorrecto": "Meta descripción fuera de rango",
    "link_interno_roto": "Link interno roto",
    "link_interno_no_verificable": "Link interno no verificable (posible bloqueo anti-bot)",
    "link_externo_roto": "Link externo roto",
    "link_externo_no_verificable": "Link externo no verificable (posible bloqueo anti-bot)",
    "imagen_roto": "Imagen rota",
    "imagen_no_verificable": "Imagen no verificable (posible bloqueo anti-bot)",
    "documento_roto": "Documento roto",
    "documento_no_verificable": "Documento no verificable (posible bloqueo anti-bot)",
    "ssl_invalido": "Certificado SSL inválido",
    "ssl_por_vencer": "Certificado SSL por vencer",
    "fallo_analisis": "Fallo al analizar el sitio",
}


def esc(s):
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt_dt(iso_str):
    dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    return dt.strftime("%d-%m-%Y %H:%M UTC")


def group_issues(issues):
    grouped = OrderedDict()
    for issue in issues:
        grouped.setdefault(issue["type"], []).append(issue)
    return grouped


def render_issue_group(issue_type, items, severity_class):
    label = ISSUE_LABELS.get(issue_type, issue_type)
    rows = []
    for it in items[:40]:
        url = esc(it.get("url", ""))
        detail = esc(it.get("detail", "") or "")
        detail_html = f'<span class="issue-detail">{detail}</span>' if detail else ""
        rows.append(
            f'<li class="issue-row"><span class="issue-url">{url}</span>{detail_html}</li>'
        )
    more = ""
    if len(items) > 40:
        more = f'<li class="issue-row issue-more">+ {len(items) - 40} más</li>'
    return f"""
    <details class="issue-group">
      <summary><span class="issue-dot {severity_class}"></span>{esc(label)} <span class="issue-count">{len(items)}</span></summary>
      <ul class="issue-list">{''.join(rows)}{more}</ul>
    </details>
    """


def render_site_card(site):
    errors = site["errors"]
    warnings = site["warnings"]
    n_err, n_warn = len(errors), len(warnings)

    if n_err > 0:
        status_class, status_label = "status-critical", "Atención requerida"
    elif n_warn > 0:
        status_class, status_label = "status-warning", "Revisar"
    else:
        status_class, status_label = "status-ok", "Sin novedades"

    ssl = site.get("ssl", {})
    if ssl.get("ok"):
        ssl_text = f"Vigente · {ssl.get('days_left', '?')} días"
        ssl_class = "ssl-ok" if ssl.get("days_left", 999) > 30 else "ssl-warn"
    else:
        ssl_text = "Inválido"
        ssl_class = "ssl-bad"

    err_groups = group_issues(errors)
    warn_groups = group_issues(warnings)

    groups_html = "".join(
        render_issue_group(t, items, "dot-error") for t, items in err_groups.items()
    ) + "".join(
        render_issue_group(t, items, "dot-warning") for t, items in warn_groups.items()
    )

    if not groups_html:
        groups_html = '<p class="no-issues">No se detectaron problemas en esta corrida.</p>'

    return f"""
    <article class="card {status_class}">
      <header class="card-header">
        <div class="card-title-row">
          <h3>{esc(site['name'])}</h3>
          <span class="status-pill {status_class}">{status_label}</span>
        </div>
        <a class="card-url" href="{esc(site['url'])}" target="_blank" rel="noopener">{esc(site['url'])}</a>
      </header>
      <div class="card-metrics">
        <div class="metric"><span class="metric-value metric-error">{n_err}</span><span class="metric-label">Errores</span></div>
        <div class="metric"><span class="metric-value metric-warning">{n_warn}</span><span class="metric-label">Advertencias</span></div>
        <div class="metric"><span class="metric-value">{site['pages_crawled']}</span><span class="metric-label">Páginas</span></div>
        <div class="metric"><span class="metric-value ssl-badge {ssl_class}">{ssl_text}</span><span class="metric-label">SSL</span></div>
      </div>
      <div class="card-body">
        {groups_html}
      </div>
    </article>
    """


def build_html(data):
    sites = data["sites"]
    total_errors = sum(s["summary"]["errors"] for s in sites)
    total_warnings = sum(s["summary"]["warnings"] for s in sites)
    total_pages = sum(s["pages_crawled"] for s in sites)
    sites_ok = sum(1 for s in sites if s["summary"]["errors"] == 0 and s["summary"]["warnings"] == 0)
    sites_sorted = sorted(sites, key=lambda s: (-s["summary"]["errors"], -s["summary"]["warnings"]))

    cards_html = "".join(render_site_card(s) for s in sites_sorted)
    run_finished = fmt_dt(data["run_finished"])

    return f"""<!doctype html>
<title>Monitoreo de Sitios — Ciencias de la Salud UC</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Source+Sans+3:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #eef1f5;
    --surface: #ffffff;
    --surface-sunken: #f4f6f9;
    --border: #dbe1ea;
    --text: #1c2733;
    --text-muted: #5b6b7d;
    --text-faint: #8695a7;
    --accent: #1e3a5f;
    --accent-soft: #e3eaf2;
    --error: #b3412c;
    --error-soft: #fbeae6;
    --warning: #9c6b0f;
    --warning-soft: #fbf1de;
    --ok: #2f7a52;
    --ok-soft: #e6f3ec;
    --shadow: 0 1px 2px rgba(28, 39, 51, 0.06), 0 8px 24px -12px rgba(28, 39, 51, 0.12);
  }}

  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #10161f;
      --surface: #182130;
      --surface-sunken: #131a25;
      --border: #2a3648;
      --text: #e7ecf3;
      --text-muted: #9aabc0;
      --text-faint: #6b7c92;
      --accent: #7fa6d6;
      --accent-soft: #1f3350;
      --error: #e2836c;
      --error-soft: #3a231f;
      --warning: #e0b45c;
      --warning-soft: #3a2f18;
      --ok: #74c99a;
      --ok-soft: #1c3327;
      --shadow: 0 1px 2px rgba(0, 0, 0, 0.3), 0 8px 24px -12px rgba(0, 0, 0, 0.5);
    }}
  }}

  :root[data-theme="dark"] {{
    --bg: #10161f;
    --surface: #182130;
    --surface-sunken: #131a25;
    --border: #2a3648;
    --text: #e7ecf3;
    --text-muted: #9aabc0;
    --text-faint: #6b7c92;
    --accent: #7fa6d6;
    --accent-soft: #1f3350;
    --error: #e2836c;
    --error-soft: #3a231f;
    --warning: #e0b45c;
    --warning-soft: #3a2f18;
    --ok: #74c99a;
    --ok-soft: #1c3327;
    --shadow: 0 1px 2px rgba(0, 0, 0, 0.3), 0 8px 24px -12px rgba(0, 0, 0, 0.5);
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: "Source Sans 3", ui-sans-serif, system-ui, sans-serif;
    font-size: 15px;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 1240px; margin: 0 auto; padding: 40px 28px 80px; }}

  .top {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 28px;
  }}
  .eyebrow {{
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-faint);
    margin: 0 0 6px;
  }}
  h1 {{
    font-family: "Archivo", ui-sans-serif, sans-serif;
    font-weight: 800;
    font-size: 28px;
    letter-spacing: -0.01em;
    margin: 0;
    text-wrap: balance;
    color: var(--text);
  }}
  .run-meta {{
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12.5px;
    color: var(--text-muted);
    text-align: right;
  }}

  .summary-row {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 32px;
  }}
  .summary-tile {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 18px;
    box-shadow: var(--shadow);
  }}
  .summary-tile .n {{
    font-family: "Archivo", sans-serif;
    font-weight: 700;
    font-size: 26px;
    font-variant-numeric: tabular-nums;
    display: block;
  }}
  .summary-tile .l {{
    font-size: 12.5px;
    color: var(--text-muted);
  }}
  .summary-tile.err .n {{ color: var(--error); }}
  .summary-tile.warn .n {{ color: var(--warning); }}
  .summary-tile.ok .n {{ color: var(--ok); }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 18px;
  }}

  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: var(--shadow);
    overflow: hidden;
    border-left: 4px solid var(--border);
  }}
  .card.status-critical {{ border-left-color: var(--error); }}
  .card.status-warning {{ border-left-color: var(--warning); }}
  .card.status-ok {{ border-left-color: var(--ok); }}

  .card-header {{ padding: 18px 20px 14px; border-bottom: 1px solid var(--border); }}
  .card-title-row {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
  .card-title-row h3 {{
    font-family: "Archivo", sans-serif;
    font-weight: 700;
    font-size: 17px;
    margin: 0;
    color: var(--text);
  }}
  .card-url {{
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 12px;
    color: var(--accent);
    text-decoration: none;
  }}
  .card-url:hover {{ text-decoration: underline; }}

  .status-pill {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.02em;
    padding: 3px 9px;
    border-radius: 999px;
    white-space: nowrap;
  }}
  .status-pill.status-critical {{ background: var(--error-soft); color: var(--error); }}
  .status-pill.status-warning {{ background: var(--warning-soft); color: var(--warning); }}
  .status-pill.status-ok {{ background: var(--ok-soft); color: var(--ok); }}

  .card-metrics {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border-bottom: 1px solid var(--border);
  }}
  .metric {{
    padding: 12px 10px;
    text-align: center;
    border-right: 1px solid var(--border);
  }}
  .metric:last-child {{ border-right: none; }}
  .metric-value {{
    display: block;
    font-family: "Archivo", sans-serif;
    font-weight: 700;
    font-size: 18px;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }}
  .metric-value.metric-error {{ color: var(--error); }}
  .metric-value.metric-warning {{ color: var(--warning); }}
  .metric-label {{ font-size: 10.5px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.04em; }}
  .ssl-badge {{ font-size: 13px !important; }}
  .ssl-badge.ssl-ok {{ color: var(--ok); }}
  .ssl-badge.ssl-warn {{ color: var(--warning); }}
  .ssl-badge.ssl-bad {{ color: var(--error); }}

  .card-body {{ padding: 8px 12px 14px; }}
  .no-issues {{ color: var(--text-muted); font-size: 13.5px; padding: 10px 8px; margin: 0; }}

  .issue-group {{ border-bottom: 1px solid var(--border); }}
  .issue-group:last-child {{ border-bottom: none; }}
  .issue-group summary {{
    list-style: none;
    cursor: pointer;
    padding: 9px 8px;
    font-size: 13.5px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text);
  }}
  .issue-group summary::-webkit-details-marker {{ display: none; }}
  .issue-group summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }}
  .issue-count {{
    font-family: "JetBrains Mono", monospace;
    font-size: 11.5px;
    color: var(--text-faint);
    background: var(--surface-sunken);
    padding: 1px 6px;
    border-radius: 999px;
    margin-left: auto;
  }}
  .issue-dot {{ width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }}
  .dot-error {{ background: var(--error); }}
  .dot-warning {{ background: var(--warning); }}

  .issue-list {{ list-style: none; margin: 0; padding: 0 8px 10px 24px; display: flex; flex-direction: column; gap: 6px; }}
  .issue-row {{ font-size: 12.5px; }}
  .issue-url {{
    font-family: "JetBrains Mono", monospace;
    color: var(--text-muted);
    word-break: break-all;
    display: block;
  }}
  .issue-detail {{ color: var(--text-faint); display: block; }}
  .issue-more {{ color: var(--text-faint); font-style: italic; }}

  footer {{
    margin-top: 40px;
    padding-top: 18px;
    border-top: 1px solid var(--border);
    font-size: 12px;
    color: var(--text-faint);
  }}

  @media (max-width: 640px) {{
    .summary-row {{ grid-template-columns: repeat(2, 1fr); }}
    .grid {{ grid-template-columns: 1fr; }}
    .top {{ align-items: flex-start; }}
    .run-meta {{ text-align: left; }}
  }}
</style>

<div class="wrap">
  <div class="top">
    <div>
      <p class="eyebrow">Ciencias de la Salud UC · Marketing</p>
      <h1>Monitoreo de Sitios Web</h1>
    </div>
    <div class="run-meta">Última corrida<br>{run_finished}</div>
  </div>

  <div class="summary-row">
    <div class="summary-tile err"><span class="n">{total_errors}</span><span class="l">Errores totales</span></div>
    <div class="summary-tile warn"><span class="n">{total_warnings}</span><span class="l">Advertencias totales</span></div>
    <div class="summary-tile ok"><span class="n">{sites_ok}/{len(sites)}</span><span class="l">Sitios sin novedades</span></div>
    <div class="summary-tile"><span class="n">{total_pages}</span><span class="l">Páginas rastreadas</span></div>
  </div>

  <div class="grid">
    {cards_html}
  </div>

  <footer>Generado automáticamente · UC-SiteMonitor Fase 1 (estado HTTP, links, imágenes, documentos, meta tags, SSL)</footer>
</div>
"""


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    html = build_html(data)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard generado: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
