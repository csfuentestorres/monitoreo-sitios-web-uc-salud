"""
Monitoreo automatizado de sitios web - Escuelas de Ciencias de la Salud UC.

Fase 1: chequeos tecnicos.
- Estado HTTP de paginas
- Links rotos (internos y externos)
- Imagenes que no cargan
- Documentos descargables (PDF, Word, Excel, etc.) que fallan
- Meta titulos y descripciones (ausentes / fuera de rango / duplicados)
- Certificado SSL

Uso:
    source venv/bin/activate
    python3 src/monitor.py
"""

import concurrent.futures
import datetime
import json
import socket
import ssl
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RUNS_DIR = DATA_DIR / "runs"
CONFIG_PATH = BASE_DIR / "config" / "sites.json"

USER_AGENT = "UC-SiteMonitor/1.0 (Marketing Facultad de Medicina UC; contacto: mkt.famed@uc.cl)"
TIMEOUT = 12
MAX_PAGES_PER_SITE = 25
MAX_DISCOVERED_LINKS = 200
MAX_WORKERS = 12

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip")
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "#")

TITLE_MIN, TITLE_MAX = 10, 65
DESC_MIN, DESC_MAX = 50, 165
SSL_WARN_DAYS = 30


def load_sites():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def normalize(url):
    url, _ = urldefrag(url)
    return url.rstrip("/") if url.count("/") > 2 else url


def same_site(url, root_netloc):
    return urlparse(url).netloc == root_netloc


def is_skippable(href):
    return any(href.startswith(s) for s in SKIP_SCHEMES)


def check_ssl(hostname):
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, 443), timeout=TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
        expire = datetime.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        days_left = (expire - datetime.datetime.utcnow()).days
        return {"ok": True, "expires": expire.isoformat(), "days_left": days_left}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def crawl_site(session, name, root_url):
    root_netloc = urlparse(root_url).netloc
    queue = [root_url]
    seen_pages = {root_url}
    pages = []

    while queue and len(pages) < MAX_PAGES_PER_SITE:
        url = queue.pop(0)
        page = {"url": url}
        try:
            resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        except Exception as e:
            page.update(status=None, error=f"{type(e).__name__}: {e}")
            pages.append(page)
            continue

        page["status"] = resp.status_code
        page["final_url"] = resp.url
        page["redirects"] = len(resp.history)

        content_type = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and "text/html" in content_type:
            soup = BeautifulSoup(resp.text, "lxml")

            title_tag = soup.find("title")
            page["title"] = title_tag.get_text(strip=True) if title_tag else None

            desc_tag = soup.find("meta", attrs={"name": "description"})
            page["description"] = (
                desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else None
            )

            links, images = set(), set()
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if not href or is_skippable(href):
                    continue
                links.add(normalize(urljoin(url, href)))
            for img in soup.find_all("img", src=True):
                src = img["src"].strip()
                if not src:
                    continue
                images.add(normalize(urljoin(url, src)))

            page["links"] = sorted(links)
            page["images"] = sorted(images)

            for link in links:
                if (
                    same_site(link, root_netloc)
                    and link not in seen_pages
                    and len(seen_pages) < MAX_DISCOVERED_LINKS
                ):
                    seen_pages.add(link)
                    queue.append(link)
        else:
            page["title"] = None
            page["description"] = None
            page["links"] = []
            page["images"] = []

        pages.append(page)

    return pages


def check_resource(session, url):
    try:
        resp = session.head(url, timeout=TIMEOUT, allow_redirects=True)
        if resp.status_code >= 400 or resp.status_code == 405:
            resp = session.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
            resp.close()
        return {"url": url, "status": resp.status_code, "final_url": resp.url, "error": None}
    except Exception as e:
        return {"url": url, "status": None, "final_url": url, "error": f"{type(e).__name__}: {e}"}


BLOCKED_STATUS_CODES = {401, 403, 429, 999}
DNS_FAILURE_MARKERS = ("NameResolutionError", "nodename nor servname", "Name or service not known")


def classify_failure(status, error):
    """Distingue un recurso confirmado como roto de uno que probablemente
    esta bloqueando el chequeo automatizado (WAF/anti-bot) sin estar
    realmente caido. Devuelve (severidad, sufijo_tipo)."""
    if status is not None:
        if status in BLOCKED_STATUS_CODES:
            return "warning", "no_verificable"
        return "error", "roto"
    if error and any(marker in error for marker in DNS_FAILURE_MARKERS):
        return "error", "roto"
    return "warning", "no_verificable"


def check_resources_bulk(session, urls):
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(check_resource, session, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futures):
            r = fut.result()
            results[r["url"]] = r
    return results


def analyze_site(session, name, root_url):
    root_netloc = urlparse(root_url).netloc
    pages = crawl_site(session, name, root_url)

    all_links, all_images = set(), set()
    for p in pages:
        all_links.update(p.get("links", []))
        all_images.update(p.get("images", []))

    doc_links = {l for l in all_links if urlparse(l).path.lower().endswith(DOC_EXTENSIONS)}
    plain_links = all_links - doc_links

    link_results = check_resources_bulk(session, plain_links)
    image_results = check_resources_bulk(session, all_images)
    doc_results = check_resources_bulk(session, doc_links)

    errors, warnings = [], []

    for p in pages:
        if p.get("status") is None or p.get("status", 200) >= 400:
            severity, suffix = classify_failure(p.get("status"), p.get("error"))
            bucket = errors if severity == "error" else warnings
            detail = p.get("error") or (f"HTTP {p['status']}" if p.get("status") else None)
            bucket.append({"type": f"pagina_{suffix}", "url": p["url"], "detail": detail})
        elif p.get("redirects", 0) >= 3:
            warnings.append({"type": "cadena_redirecciones", "url": p["url"], "detail": f"{p['redirects']} redirecciones"})

        if p.get("status") == 200 and "final_url" in p:
            title = p.get("title")
            desc = p.get("description")
            if not title:
                errors.append({"type": "meta_titulo_ausente", "url": p["url"], "detail": None})
            elif not (TITLE_MIN <= len(title) <= TITLE_MAX):
                warnings.append({"type": "meta_titulo_largo_incorrecto", "url": p["url"], "detail": f"{len(title)} caracteres: \"{title}\""})
            if not desc:
                warnings.append({"type": "meta_descripcion_ausente", "url": p["url"], "detail": None})
            elif not (DESC_MIN <= len(desc) <= DESC_MAX):
                warnings.append({"type": "meta_descripcion_largo_incorrecto", "url": p["url"], "detail": f"{len(desc)} caracteres"})

    titles_seen = {}
    for p in pages:
        t = p.get("title")
        if t:
            titles_seen.setdefault(t, []).append(p["url"])
    for t, urls in titles_seen.items():
        if len(urls) > 1:
            warnings.append({"type": "meta_titulo_duplicado", "url": ", ".join(urls), "detail": f"\"{t}\""})

    for url, r in link_results.items():
        if r["status"] is None or r["status"] >= 400:
            severity, suffix = classify_failure(r["status"], r.get("error"))
            bucket = errors if severity == "error" else warnings
            scope = "interno" if same_site(url, root_netloc) else "externo"
            detail = r.get("error") or f"HTTP {r['status']}"
            bucket.append({"type": f"link_{scope}_{suffix}", "url": url, "detail": detail})

    for url, r in image_results.items():
        if r["status"] is None or r["status"] >= 400:
            severity, suffix = classify_failure(r["status"], r.get("error"))
            bucket = errors if severity == "error" else warnings
            bucket.append({"type": f"imagen_{suffix}", "url": url, "detail": r.get("error") or f"HTTP {r['status']}"})

    for url, r in doc_results.items():
        if r["status"] is None or r["status"] >= 400:
            severity, suffix = classify_failure(r["status"], r.get("error"))
            bucket = errors if severity == "error" else warnings
            bucket.append({"type": f"documento_{suffix}", "url": url, "detail": r.get("error") or f"HTTP {r['status']}"})

    ssl_info = check_ssl(root_netloc)
    if not ssl_info.get("ok"):
        errors.append({"type": "ssl_invalido", "url": root_url, "detail": ssl_info.get("error")})
    elif ssl_info.get("days_left", 999) <= SSL_WARN_DAYS:
        warnings.append({"type": "ssl_por_vencer", "url": root_url, "detail": f"{ssl_info['days_left']} dias restantes"})

    return {
        "name": name,
        "url": root_url,
        "pages_crawled": len(pages),
        "links_checked": len(link_results),
        "images_checked": len(image_results),
        "documents_checked": len(doc_results),
        "ssl": ssl_info,
        "errors": errors,
        "warnings": warnings,
        "summary": {"errors": len(errors), "warnings": len(warnings)},
    }


def main():
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    sites = load_sites()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    run_started = datetime.datetime.utcnow().isoformat() + "Z"
    results = []
    for site in sites:
        print(f"Analizando {site['name']} ({site['url']})...")
        try:
            result = analyze_site(session, site["name"], site["url"])
        except Exception as e:
            result = {
                "name": site["name"],
                "url": site["url"],
                "pages_crawled": 0,
                "links_checked": 0,
                "images_checked": 0,
                "documents_checked": 0,
                "ssl": {"ok": False, "error": "no evaluado"},
                "errors": [{"type": "fallo_analisis", "url": site["url"], "detail": f"{type(e).__name__}: {e}"}],
                "warnings": [],
                "summary": {"errors": 1, "warnings": 0},
            }
        results.append(result)
        print(f"  -> {result['summary']['errors']} errores, {result['summary']['warnings']} advertencias")

    unreachable = [r for r in results if r["pages_crawled"] <= 1 and r["links_checked"] == 0]
    if len(unreachable) == len(results):
        print(
            "\nABORTADO: los 8 sitios devolvieron 0 recursos revisados. "
            "Esto no es un problema real de los sitios, es un fallo sistemico "
            "(bloqueo de red / proxy / DNS del entorno donde corre este script). "
            "No se sobreescribe data/latest.json con datos falsos de 'todo sano'."
        )
        raise SystemExit(1)
    elif len(unreachable) >= max(1, len(results) // 2):
        print(
            f"\nADVERTENCIA: {len(unreachable)}/{len(results)} sitios no devolvieron "
            "ningun recurso revisado (posible problema de red parcial). Revisar antes de confiar en esta corrida."
        )

    run_finished = datetime.datetime.utcnow().isoformat() + "Z"

    output = {
        "run_started": run_started,
        "run_finished": run_finished,
        "sites": results,
    }

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_path = RUNS_DIR / f"{timestamp}.json"
    with open(run_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    latest_path = DATA_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nGuardado: {run_path}")
    print(f"Actualizado: {latest_path}")


if __name__ == "__main__":
    main()
