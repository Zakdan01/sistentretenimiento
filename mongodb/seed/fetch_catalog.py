"""Genera los snapshots JSON del catálogo desde Wikipedia, Wikidata e IMDb.

No escribe en MongoDB: solo produce `data/movies.json`, `data/series.json` y
`data/animes.json`. La carga corre por separado en `mongodb.seed.load_seed`.

Pipeline:
1. Se recolectan candidatos de las categorías por año de la Wikipedia española.
2. Se resuelven sus QID de Wikidata con `pageprops` (lotes de 50 títulos).
3. Se enriquecen en bloque con SPARQL: IMDb (`P345`), fecha (`P577`), géneros
   (`P136`) y enlace a la Wikipedia inglesa. Una consulta cubre 300 QID.
4. Los géneros se traducen a etiquetas en español (o inglés como respaldo).
5. Se completa el póster desde la Wikipedia inglesa (`pilicense=any`).
6. La sinopsis sale del extracto introductorio de la Wikipedia española.
7. La nota y los votos salen de `title.ratings.tsv.gz` de IMDb.

Uso:
    python -m mongodb.seed.fetch_catalog --limit 500
    python -m mongodb.seed.fetch_catalog --type anime --limit 20 --candidates 60
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

SEED_DIR = Path(__file__).resolve().parent
DATA_DIR = SEED_DIR / "data"
CACHE_DIR = SEED_DIR / ".cache"
WIKI_API = "https://es.wikipedia.org/w/api.php"
WIKI_EN_API = "https://en.wikipedia.org/w/api.php"
SPARQL_API = "https://query.wikidata.org/sparql"
IMDB_RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
USER_AGENT = "CasoEstudioDB3/1.0 (biblioteca virtual, uso academico)"

CATEGORY_TEMPLATES = {
    "movie": ("es", ("Películas de {year}",)),
    "series": ("es", ("Series de televisión iniciadas en {year}",)),
}
ANIME_CLASSES = ("Q63952888", "Q20650540", "Q220898")
OUTPUT_FILES = {
    "movie": "movies.json",
    "series": "series.json",
    "anime": "animes.json",
}
TYPE_ORDER = ("movie", "series", "anime")

# Clase raíz de Wikidata que valida el tipo de cada candidato. El anime se
# descubre ya filtrado por sus clases, así que no necesita validación extra.
TYPE_CLASSES = {
    "movie": "Q11424",      # película
    "series": "Q5398426",   # serie de televisión
    "anime": None,
}

REQUEST_PAUSE = 0.8
PAGE_BATCH = 50
EXTRACT_BATCH = 20
ENTITY_BATCH = 300


class FetchError(RuntimeError):
    """Error controlado al consultar una fuente externa."""


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip",
        }
    )
    return session


def _get_json(session: requests.Session, url: str, params: dict, retries: int = 6) -> dict:
    last_error = None
    for attempt in range(retries):
        try:
            response = session.get(url, params=params, timeout=60)
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", 10))
                print(f"  límite de peticiones; esperando {wait:.0f}s...", flush=True)
                time.sleep(wait)
                continue
            if response.status_code in (500, 502, 503, 504):
                raise FetchError(f"HTTP {response.status_code}")
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError, FetchError) as error:
            last_error = error
            time.sleep(min(2 ** attempt, 30))
    raise FetchError(f"No se pudo consultar {url}: {last_error}")


def _sparql(session: requests.Session, query: str, retries: int = 5) -> list[dict]:
    last_error = None
    for attempt in range(retries):
        try:
            response = session.get(
                SPARQL_API,
                params={"query": query, "format": "json"},
                headers={"Accept": "application/sparql-results+json"},
                timeout=90,
            )
            if response.status_code == 429:
                wait = float(response.headers.get("Retry-After", 10))
                print(f"  Wikidata ocupado; esperando {wait:.0f}s...", flush=True)
                time.sleep(wait)
                continue
            if response.status_code in (500, 502, 503, 504):
                raise FetchError(f"HTTP {response.status_code}")
            response.raise_for_status()
            return response.json().get("results", {}).get("bindings", [])
        except (requests.RequestException, ValueError, FetchError) as error:
            last_error = error
            time.sleep(min(2 ** attempt, 30))
    raise FetchError(f"No se pudo consultar Wikidata: {last_error}")


def collect_anime_candidates(
    session: requests.Session, years: list[int], per_year: int
) -> dict[str, dict]:
    """Descubre series y películas de anime directamente en Wikidata."""
    candidates: dict[str, dict] = {}
    classes = " ".join(f"wd:{qid}" for qid in ANIME_CLASSES)

    for year in years:
        query = (
            "SELECT DISTINCT ?item ?eswiki ?enwiki WHERE {"
            f" VALUES ?class {{ {classes} }}"
            " ?item wdt:P31 ?class ; wdt:P345 ?imdb ."
            " { ?item wdt:P580 ?date } UNION { ?item wdt:P577 ?date }"
            f" FILTER(YEAR(?date) = {year})"
            " OPTIONAL { ?eswiki schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> . }"
            " OPTIONAL { ?enwiki schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }"
            f" }} LIMIT {per_year}"
        )
        rows = _sparql(session, query)
        for row in rows:
            qid = _qid_from_uri(row["item"]["value"])
            eswiki = _title_from_url(row["eswiki"]["value"]) if row.get("eswiki") else None
            enwiki = _title_from_url(row["enwiki"]["value"]) if row.get("enwiki") else None
            title = eswiki or enwiki
            if not title or title in candidates:
                continue
            candidates[title] = {
                "year": year,
                "qid": qid,
                "disambiguation": False,
                "eswiki": eswiki,
                "enwiki": enwiki,
            }
        print(f"  anime {year}: {len(candidates)} candidatos", flush=True)

    return candidates


def collect_candidates(
    session: requests.Session, title_type: str, years: list[int], per_year: int
) -> dict[str, dict]:
    """Devuelve {título: {year, qid, desambiguación}} para un tipo."""
    if title_type == "anime":
        return collect_anime_candidates(session, years, per_year)

    candidates: dict[str, dict] = {}
    lang, templates = CATEGORY_TEMPLATES[title_type]
    api = WIKI_API if lang == "es" else WIKI_EN_API
    prefix = "Categoría:" if lang == "es" else "Category:"

    for template in templates:
        for year in years:
            category = prefix + template.format(year=year)
            params = {
                "action": "query",
                "format": "json",
                "formatversion": "2",
                "generator": "categorymembers",
                "gcmtitle": category,
                "gcmtype": "page",
                "gcmnamespace": "0",
                "gcmlimit": "500",
                "prop": "pageprops",
            }
            found = 0
            while True:
                data = _get_json(session, api, params)
                for page in data.get("query", {}).get("pages", []):
                    title = page.get("title")
                    if not title or title in candidates:
                        continue
                    props = page.get("pageprops") or {}
                    candidates[title] = {
                        "year": year,
                        "qid": props.get("wikibase_item"),
                        "disambiguation": "disambiguation" in props,
                        "wiki": lang,
                    }
                    found += 1
                    if found >= per_year:
                        break
                if found >= per_year:
                    break
                cont = data.get("continue", {}).get("gcmcontinue")
                if not cont:
                    break
                params["gcmcontinue"] = cont
                time.sleep(REQUEST_PAUSE)
            print(f"  {title_type} {year} ({category}): {found}", flush=True)
            time.sleep(REQUEST_PAUSE)

    return candidates


def sample_candidates(
    candidates: dict[str, dict], count: int, seed: int
) -> list[tuple[str, dict]]:
    items = sorted(candidates.items())
    if len(items) <= count:
        return items
    return random.Random(seed).sample(items, count)


def _resolve_titles(data: dict) -> callable:
    mapping = {}
    for key in ("normalized", "redirects"):
        for item in data.get("query", {}).get(key, []):
            mapping[item["from"]] = item["to"]

    def resolve(title: str) -> str:
        seen = set()
        while title in mapping and title not in seen:
            seen.add(title)
            title = mapping[title]
        return title

    return resolve


def _qid_from_uri(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _title_from_url(url: str) -> str:
    path = urlparse(url).path
    return unquote(path.rsplit("/", 1)[-1]).replace("_", " ")


def fetch_entities(
    session: requests.Session, qids: list[str], type_class: str
) -> dict[str, dict]:
    """IMDb, año, géneros (QID), enlaces y validación de tipo vía SPARQL."""
    entities: dict[str, dict] = {}
    if not qids:
        return entities

    for start in range(0, len(qids), ENTITY_BATCH):
        batch = qids[start : start + ENTITY_BATCH]
        values = " ".join(f"wd:{qid}" for qid in batch)
        if type_class:
            type_clause = (
                f" OPTIONAL {{ ?item wdt:P31/wdt:P279* wd:{type_class} . BIND(true AS ?is_type) }}"
            )
        else:
            type_clause = " BIND(true AS ?is_type)"
        query = (
            "SELECT ?item ?imdb ?year ?eswiki ?enwiki ?is_type "
            '(GROUP_CONCAT(DISTINCT ?genre; separator="|") AS ?genres) WHERE {'
            f" VALUES ?item {{ {values} }}"
            " OPTIONAL { ?item wdt:P345 ?imdb . }"
            " OPTIONAL { ?item wdt:P577 ?date . BIND(YEAR(?date) AS ?year) }"
            " OPTIONAL { ?item wdt:P136 ?genre . }"
            " OPTIONAL { ?eswiki schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> . }"
            " OPTIONAL { ?enwiki schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> . }"
            f"{type_clause}"
            " } GROUP BY ?item ?imdb ?year ?eswiki ?enwiki ?is_type"
        )
        rows = _sparql(session, query)
        for row in rows:
            qid = _qid_from_uri(row["item"]["value"])
            entry = entities.setdefault(
                qid,
                {
                    "imdb": None,
                    "year": None,
                    "eswiki": None,
                    "enwiki": None,
                    "genres": [],
                    "is_type": False,
                },
            )
            if row.get("imdb"):
                entry["imdb"] = row["imdb"]["value"]
            if row.get("year"):
                year = int(row["year"]["value"])
                entry["year"] = min(year, entry["year"]) if entry["year"] else year
            if row.get("eswiki"):
                entry["eswiki"] = _title_from_url(row["eswiki"]["value"])
            if row.get("enwiki"):
                entry["enwiki"] = _title_from_url(row["enwiki"]["value"])
            if row.get("is_type", {}).get("value") == "true":
                entry["is_type"] = True
            genres = row.get("genres", {}).get("value", "")
            for raw in genres.split("|"):
                if raw:
                    entry["genres"].append(_qid_from_uri(raw))
        print(f"  wikidata {min(start + ENTITY_BATCH, len(qids))}/{len(qids)}", flush=True)

    return entities


def fetch_labels(session: requests.Session, qids: list[str]) -> dict[str, str]:
    """Etiquetas de género en español, con inglés como respaldo."""
    labels: dict[str, str] = {}
    if not qids:
        return labels

    for start in range(0, len(qids), ENTITY_BATCH):
        batch = qids[start : start + ENTITY_BATCH]
        values = " ".join(f"wd:{qid}" for qid in batch)
        query = (
            "SELECT ?genre ?label ?lang WHERE {"
            f" VALUES ?genre {{ {values} }}"
            ' ?genre rdfs:label ?label . FILTER(LANG(?label) IN ("es", "en"))'
            " BIND(LANG(?label) AS ?lang)"
            " }"
        )
        rows = _sparql(session, query)
        for row in rows:
            qid = _qid_from_uri(row["genre"]["value"])
            lang = row["lang"]["value"]
            if qid not in labels or lang == "es":
                labels[qid] = row["label"]["value"]

    return labels


def fetch_en_images(session: requests.Session, titles: list[str]) -> dict[str, str]:
    """Póster desde la Wikipedia en inglés.

    `pilicense=any` incluye las carátulas no libres alojadas en en.wikipedia,
    que es lo único que existe para la mayoría de las películas.
    """
    images: dict[str, str] = {}

    for start in range(0, len(titles), PAGE_BATCH):
        batch = titles[start : start + PAGE_BATCH]
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "prop": "pageimages",
            "piprop": "thumbnail",
            "pithumbsize": "500",
            "pilicense": "any",
            "titles": "|".join(batch),
        }
        data = _get_json(session, WIKI_EN_API, params)
        resolve = _resolve_titles(data)
        by_final = {resolve(title): title for title in batch}
        for page in data.get("query", {}).get("pages", []):
            original = by_final.get(page.get("title"))
            thumbnail = (page.get("thumbnail") or {}).get("source")
            if original and thumbnail:
                images[original] = thumbnail
        time.sleep(REQUEST_PAUSE)

    return images


def fetch_extracts(
    session: requests.Session, titles: list[str], api: str = WIKI_API
) -> dict[str, str]:
    """Sinopsis introductoria desde la Wikipedia indicada."""
    extracts: dict[str, str] = {}

    for start in range(0, len(titles), EXTRACT_BATCH):
        batch = titles[start : start + EXTRACT_BATCH]
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "exlimit": str(EXTRACT_BATCH),
            "titles": "|".join(batch),
        }
        data = _get_json(session, api, params)
        resolve = _resolve_titles(data)
        by_final = {resolve(title): title for title in batch}
        for page in data.get("query", {}).get("pages", []):
            original = by_final.get(page.get("title"))
            if original and page.get("extract"):
                extracts[original] = page["extract"]
        time.sleep(REQUEST_PAUSE)

    return extracts


def load_imdb_ratings(needed: set[str]) -> dict[str, tuple[float, int]]:
    """Descarga (con caché) las notas de IMDb y filtra por los IDs pedidos."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / "title.ratings.tsv.gz"

    if not path.exists():
        print("descargando notas de IMDb (8 MB)...", flush=True)
        with requests.get(IMDB_RATINGS_URL, stream=True, timeout=120) as response:
            response.raise_for_status()
            with path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    handle.write(chunk)

    ratings: dict[str, tuple[float, int]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        next(handle, None)
        for line in handle:
            fields = line.rstrip("\n").split("\t")
            if len(fields) != 3 or fields[0] not in needed:
                continue
            try:
                ratings[fields[0]] = (float(fields[1]), int(fields[2]))
            except ValueError:
                continue

    return ratings


def clean_title(title: str) -> str:
    cleaned = re.sub(
        r"\s*\((?:pel[ií]cula|serie|series|anime|anim[eé]|film|tv|televisi[oó]n)[^)]*\)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def clean_synopsis(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= 700:
        return text
    cut = text[:700]
    boundary = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[: boundary + 1] if boundary > 300 else cut).strip()


def normalize_genre(label: str) -> str:
    label = re.sub(r"\s+", " ", label).strip()
    if not label:
        return ""
    return label[0].upper() + label[1:]


def prepare_type(
    session: requests.Session,
    title_type: str,
    years: list[int],
    candidates: int,
    seed: int,
    per_year: int,
) -> list[dict]:
    print(f"\n[{title_type}] recolectando candidatos...", flush=True)
    found = collect_candidates(session, title_type, years, per_year)
    sampled = sample_candidates(found, candidates, seed)
    print(f"[{title_type}] {len(found)} candidatos, {len(sampled)} muestreados", flush=True)

    qids = sorted({data["qid"] for _, data in sampled if data.get("qid")})
    entities = fetch_entities(session, qids, TYPE_CLASSES[title_type])

    genre_qids = sorted(
        {qid for entity in entities.values() for qid in entity.get("genres", [])}
    )
    labels = fetch_labels(session, genre_qids)

    stats = {
        "desambiguacion": 0,
        "sin_wikidata": 0,
        "sin_tipo": 0,
        "sin_imdb": 0,
        "sin_generos": 0,
    }

    staged = []
    for title, candidate in sampled:
        if candidate.get("disambiguation"):
            stats["desambiguacion"] += 1
            continue
        qid = candidate.get("qid")
        if not qid:
            stats["sin_wikidata"] += 1
            continue
        entity = entities.get(qid, {})
        if not entity.get("is_type"):
            stats["sin_tipo"] += 1
            continue
        imdb = entity.get("imdb")
        if not imdb:
            stats["sin_imdb"] += 1
            continue
        genres = []
        seen = set()
        for genre_qid in entity.get("genres", []):
            label = normalize_genre(labels.get(genre_qid, ""))
            if label and label.casefold() not in seen:
                seen.add(label.casefold())
                genres.append(label)
        if not genres:
            stats["sin_generos"] += 1
            continue
        staged.append(
            {
                "type": title_type,
                "title": clean_title(entity.get("eswiki") or title),
                "year": candidate.get("year") or entity.get("year"),
                "genres": genres[:5],
                "imdb": imdb,
                "eswiki": entity.get("eswiki") or (title if candidate.get("wiki") == "es" else None),
                "enwiki": entity.get("enwiki") or (title if candidate.get("wiki") == "en" else None),
            }
        )

    print(f"[{title_type}] descartes: {stats}", flush=True)
    return staged


def fill_media(
    session: requests.Session,
    staged: list[dict],
    ratings: dict[str, tuple[float, int]],
    limit: int,
) -> list[dict]:
    """Elige los mejores candidatos y completa póster y sinopsis."""
    title_type = staged[0]["type"] if staged else "?"
    with_rating = [item for item in staged if item["imdb"] in ratings]
    with_rating.sort(key=lambda item: ratings[item["imdb"]][1], reverse=True)

    # Los pósters viven casi siempre en la Wikipedia inglesa.
    image_pool = with_rating[: int(limit * 1.6)]
    missing = [item["enwiki"] for item in image_pool if item.get("enwiki")]
    images = fetch_en_images(session, missing) if missing else {}
    filled = 0
    for item in image_pool:
        image = images.get(item.get("enwiki") or "")
        if image:
            item["image"] = image
            filled += 1
    print(f"[{title_type}] imágenes desde enwiki: {filled}/{len(missing)}", flush=True)

    with_image = [item for item in image_pool if item.get("image")]
    extract_pool = with_image[: int(limit * 1.3)]
    es_titles = [item["eswiki"] for item in extract_pool if item.get("eswiki")]
    en_titles = [
        item["enwiki"]
        for item in extract_pool
        if not item.get("eswiki") and item.get("enwiki")
    ]
    es_extracts = fetch_extracts(session, es_titles, WIKI_API) if es_titles else {}
    en_extracts = fetch_extracts(session, en_titles, WIKI_EN_API) if en_titles else {}
    for item in extract_pool:
        text = es_extracts.get(item.get("eswiki") or "", "")
        if not text:
            text = en_extracts.get(item.get("enwiki") or "", "")
        item["synopsis"] = clean_synopsis(text)

    prepared = [item for item in extract_pool if item.get("synopsis")]
    print(f"[{title_type}] {len(prepared)} fichas completas", flush=True)
    return prepared


def finalize_type(
    prepared: list[dict],
    ratings: dict[str, tuple[float, int]],
    limit: int,
    used_imdb: set[str],
) -> list[dict]:
    stats = {
        "duplicado": 0,
        "sin_imagen": 0,
        "sin_generos": 0,
        "sin_sinopsis": 0,
        "sin_rating": 0,
    }
    valid = []
    for item in prepared:
        if item["imdb"] in used_imdb:
            stats["duplicado"] += 1
            continue
        if not item.get("image"):
            stats["sin_imagen"] += 1
            continue
        if not item.get("genres"):
            stats["sin_generos"] += 1
            continue
        if not item.get("synopsis"):
            stats["sin_sinopsis"] += 1
            continue
        if item["imdb"] not in ratings:
            stats["sin_rating"] += 1
            continue

        rating, votes = ratings[item["imdb"]]
        item = dict(item)
        item["rating"] = round(rating, 1)
        item["votes"] = votes
        valid.append(item)

    print(f"descartes finales: {stats}", flush=True)
    valid.sort(key=lambda item: item["votes"], reverse=True)
    selected = valid[:limit]
    used_imdb.update(item["imdb"] for item in selected)
    return selected


def to_json_document(item: dict) -> dict:
    return {
        "source": "imdb",
        "external_id": item["imdb"],
        "title": item["title"],
        "image": item["image"],
        "synopsis": item["synopsis"],
        "year": int(item["year"]),
        "genres": item["genres"],
        "rating": item["rating"],
    }


def parse_years(raw: str) -> list[int]:
    if "-" in raw:
        start, end = raw.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(raw)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=500, help="títulos por tipo")
    parser.add_argument(
        "--candidates", type=int, default=1500, help="candidatos a enriquecer por tipo"
    )
    parser.add_argument("--years", default="1990-2025", help="rango, por ejemplo 1990-2025")
    parser.add_argument("--per-year", type=int, default=200)
    parser.add_argument("--seed", type=int, default=14)
    parser.add_argument("--type", choices=[*TYPE_ORDER, "all"], default="all")
    parser.add_argument("--dry-run", action="store_true", help="no escribe los JSON")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

    years = parse_years(args.years)
    types = TYPE_ORDER if args.type == "all" else (args.type,)
    session = _session()

    prepared = {}
    staged = {}
    for title_type in types:
        staged[title_type] = prepare_type(
            session,
            title_type,
            years,
            args.candidates,
            args.seed,
            args.per_year,
        )

    needed = {item["imdb"] for items in staged.values() for item in items}
    ratings = load_imdb_ratings(needed)
    print(f"notas IMDb disponibles: {len(ratings)} de {len(needed)}", flush=True)

    for title_type in types:
        prepared[title_type] = fill_media(
            session, staged[title_type], ratings, args.limit
        )

    used_imdb: set[str] = set()
    summary = {}
    for title_type in types:
        selected = finalize_type(prepared[title_type], ratings, args.limit, used_imdb)
        documents = [to_json_document(item) for item in selected]
        summary[title_type] = documents
        print(f"[{title_type}] {len(documents)} títulos seleccionados", flush=True)

        if args.dry_run:
            for document in documents[:3]:
                print(json.dumps(document, ensure_ascii=False)[:300], flush=True)
            continue

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / OUTPUT_FILES[title_type]
        path.write_text(
            json.dumps(documents, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[{title_type}] escrito {path.name}", flush=True)

    if not args.dry_run and len(summary) > 1:
        print("\nresumen:", flush=True)
        for title_type in types:
            print(f"  {title_type}: {len(summary[title_type])}", flush=True)


if __name__ == "__main__":
    main()
