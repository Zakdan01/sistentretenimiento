import requests

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


class ProviderError(Exception):
    """Error controlado al consultar una API externa."""


def _get_json(url, params, get):
    response = get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _year_from_date(value: str) -> int | None:
    value = value or ""
    return int(value[:4]) if value[:4].isdigit() else None


def _jikan_payload(item: dict) -> dict:
    aired_from = (item.get("aired") or {}).get("from") or ""

    return {
        "external": {"source": "jikan", "id": int(item["mal_id"])},
        "type": "anime",
        "title": item.get("title") or item.get("title_english") or "Sin título",
        "synopsis": item.get("synopsis") or "",
        "genres": [genre["name"] for genre in item.get("genres", [])],
        "year": item.get("year") or _year_from_date(aired_from),
        "poster_url": ((item.get("images") or {}).get("jpg") or {}).get(
            "large_image_url"
        ),
        "external_rating": item.get("score"),
    }


def search_jikan(
    query: str,
    base_url: str = "https://api.jikan.moe/v4",
    get=requests.get,
) -> list[dict]:
    payload = _get_json(
        f"{base_url}/anime",
        {"q": query, "limit": 10, "sfw": "true"},
        get,
    )
    return [_jikan_payload(item) for item in payload.get("data", [])]


def fetch_jikan(
    external_id: int,
    base_url: str = "https://api.jikan.moe/v4",
    get=requests.get,
) -> dict:
    payload = _get_json(f"{base_url}/anime/{external_id}", {}, get)
    return _jikan_payload(payload.get("data", payload))


def _require_tmdb_key(api_key: str) -> None:
    if not api_key:
        raise ProviderError(
            "Falta TMDB_API_KEY en el archivo .env para consultar TMDB."
        )


def _tmdb_params(api_key: str, extra: dict | None = None) -> dict:
    params = {"api_key": api_key, "language": "es-ES"}
    if extra:
        params.update(extra)
    return params


def _tmdb_poster(path: str | None) -> str | None:
    return f"{TMDB_IMAGE_BASE}{path}" if path else None


def _tmdb_search_result(item: dict) -> dict:
    media_type = item["media_type"]
    date = item.get("release_date") or item.get("first_air_date") or ""

    return {
        "external": {"source": "tmdb", "id": int(item["id"])},
        "type": "movie" if media_type == "movie" else "series",
        "media_type": media_type,
        "title": item.get("title") or item.get("name") or "Sin título",
        "year": _year_from_date(date),
        "synopsis": item.get("overview") or "",
        "genres": [],
        "poster_url": _tmdb_poster(item.get("poster_path")),
        "external_rating": item.get("vote_average"),
    }


def search_tmdb(
    query: str,
    api_key: str,
    base_url: str = "https://api.themoviedb.org/3",
    get=requests.get,
) -> list[dict]:
    _require_tmdb_key(api_key)
    payload = _get_json(
        f"{base_url}/search/multi",
        _tmdb_params(api_key, {"query": query, "include_adult": "false"}),
        get,
    )

    return [
        _tmdb_search_result(item)
        for item in payload.get("results", [])
        if item.get("media_type") in ("movie", "tv")
    ]


def fetch_tmdb(
    media_type: str,
    external_id: int,
    api_key: str,
    base_url: str = "https://api.themoviedb.org/3",
    get=requests.get,
) -> dict:
    _require_tmdb_key(api_key)
    if media_type not in ("movie", "tv"):
        raise ProviderError("Tipo de TMDB inválido: usá movie o tv.")

    payload = _get_json(
        f"{base_url}/{media_type}/{external_id}",
        _tmdb_params(api_key),
        get,
    )

    if media_type == "movie":
        title = payload.get("title") or "Sin título"
        date = payload.get("release_date") or ""
        title_type = "movie"
    else:
        title = payload.get("name") or "Sin título"
        date = payload.get("first_air_date") or ""
        title_type = "series"

    return {
        "external": {"source": "tmdb", "id": int(payload["id"])},
        "type": title_type,
        "title": title,
        "synopsis": payload.get("overview") or "",
        "genres": [genre["name"] for genre in payload.get("genres", [])],
        "year": _year_from_date(date),
        "poster_url": _tmdb_poster(payload.get("poster_path")),
        "external_rating": payload.get("vote_average"),
    }
