"""
Genera resumenes en CSV a partir de data/latest.json, pensados para
alimentar una Google Sheet via IMPORTDATA.

Uso:
    source venv/bin/activate
    python3 src/export_csv.py
"""

import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "latest.json"
SUMMARY_PATH = BASE_DIR / "reports" / "resumen.csv"
DETAIL_PATH = BASE_DIR / "reports" / "detalle_issues.csv"


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    with open(SUMMARY_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "escuela", "url", "errores", "advertencias", "paginas_rastreadas",
            "ssl_ok", "ssl_dias_restantes", "corrida",
        ])
        for site in data["sites"]:
            ssl = site.get("ssl", {})
            writer.writerow([
                site["name"],
                site["url"],
                site["summary"]["errors"],
                site["summary"]["warnings"],
                site["pages_crawled"],
                "si" if ssl.get("ok") else "no",
                ssl.get("days_left", ""),
                data["run_finished"],
            ])

    with open(DETAIL_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["escuela", "severidad", "tipo", "url", "detalle", "corrida"])
        for site in data["sites"]:
            for e in site["errors"]:
                writer.writerow([site["name"], "error", e["type"], e["url"], e.get("detail") or "", data["run_finished"]])
            for w in site["warnings"]:
                writer.writerow([site["name"], "advertencia", w["type"], w["url"], w.get("detail") or "", data["run_finished"]])

    print(f"Generado: {SUMMARY_PATH}")
    print(f"Generado: {DETAIL_PATH}")


if __name__ == "__main__":
    main()
