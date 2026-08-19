"""
Fase 3: chequeos de contenido.
- Contenido posiblemente desactualizado (anios de proceso/admision vencidos)
- Inconsistencias de anio entre paginas de un mismo sitio

Nota sobre ortografia: se evaluaron tres enfoques (API publica de LanguageTool,
diccionario local via pyspellchecker, Hunspell) y ninguno dio resultados
confiables en este entorno - ver notas del proyecto. Queda pendiente para
una iteracion futura con una herramienta mejor (ej. LanguageTool auto-hospedado).
"""

import re

STALE_KEYWORDS = [
    "admisión", "admision", "postulación", "postulacion",
    "proceso de selección", "proceso de seleccion", "convocatoria",
    "matrícula", "matricula", "año académico", "ano academico",
    "cohorte", "versión", "vigente",
]
YEAR_RE = re.compile(r"20\d{2}")

MIN_PLAUSIBLE_YEAR = 2015


def extract_main_text(soup):
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "svg"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)


def find_year_mentions(text, current_year):
    """Devuelve lista de {year, snippet} para anios mencionados cerca de
    palabras clave de proceso/admision. Incluye anios pasados, actuales y futuros
    (la clasificacion desactualizado/inconsistente se hace en el llamador)."""
    mentions = []
    for m in YEAR_RE.finditer(text):
        year = int(m.group())
        if year < MIN_PLAUSIBLE_YEAR or year > current_year + 2:
            continue
        start = max(0, m.start() - 50)
        end = min(len(text), m.end() + 20)
        window = text[start:end].lower()
        if any(k in window for k in STALE_KEYWORDS):
            mentions.append({"year": year, "snippet": text[start:end].strip()})
    return mentions
