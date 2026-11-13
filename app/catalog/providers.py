import re

import requests

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


class ProviderError(Exception):
    """Error controlado al consultar una API externa."""


def _get_json(url, params, get):
    response = get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


def _parse_minutes(duration: str) -> int | None:
    match = re.search(r"(\d+)\s*min", duration or "")
    return int(match.group(1)) if match else None


def _jikan_payload(item: dict) -> dict:
    is_movie = item.get("type") == "Movie"
    episodes = item.get("episodes")
    aired_from = (item.get("aired") or {}).get("from") or ""

    seasons = []
    if not is_movie and episodes:
        seasons = [{"number": 1, "episodes": int(episodes)}]

    return {
        "external": {"source": "jikan", "id": int(item["mal_id"])},
        "type": "anime",
        "title": item.get("title") or item.get("title_english") or "Sin título",
        "original_title": item.get("title_japanese")
        or item.get("title_english")
        or item.get("title"),
        "synopsis": item.get("synopsis") or "",
        "genres": [genre["name"] for genre in item.get("genres", [])],
        "release_date": aired_from[:10],
        "year": item.get("year"),
        "runtime_minutes": _parse_minutes(item.get("duration", "")) if is_movie else None,
        "seasons": seasons,
        "episodes_total": None if is_movie else episodes,
        "directors": [],
        "cast": [],
        "studios": [studio["name"] for studio in item.get("studios", [])],
        "poster_url": ((item.get("images") or {}).get("jpg") or {}).get(
            "large_image_url"
        ),
        "external_rating": item.get("score"),
        "awards": [],
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
    year = int(date[:4]) if date[:4].isdigit() else None

    return {
        "external": {"source": "tmdb", "id": int(item["id"])},
        "type": "movie" if media_type == "movie" else "series",
        "media_type": media_type,
        "title": item.get("title") or item.get("name") or "Sin título",
        "year": year,
        "release_date": date,
        "synopsis": item.get("overview") or "",
        "poster_url": _tmdb_poster(item.get("poster_path")),
        "external_rating": item.get("vote_average"),
        "genres": [],
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
        _tmdb_params(api_key, {"append_to_response": "credits"}),
        get,
    )

    credits = payload.get("credits") or {}
    cast = [person["name"] for person in credits.get("cast", [])][:10]
    directors = [
        person["name"]
        for person in credits.get("crew", [])
        if person.get("job") == "Director"
    ]

    if media_type == "movie":
        title = payload.get("title") or "Sin título"
        original_title = payload.get("original_title") or title
        release_date = payload.get("release_date") or ""
        runtime = payload.get("runtime")
        seasons = []
        episodes_total = None
        title_type = "movie"
    else:
        title = payload.get("name") or "Sin título"
        original_title = payload.get("original_name") or title
        release_date = payload.get("first_air_date") or ""
        runtime = None
        seasons = [
            {
                "number": int(season["season_number"]),
                "episodes": int(season["episode_count"]),
                **(
                    {"air_date": season["air_date"]}
                    if season.get("air_date")
                    else {}
                ),
            }
            for season in payload.get("seasons", [])
            if season.get("season_number", 0) > 0 and season.get("episode_count")
        ]
        episodes_total = sum(season["episodes"] for season in seasons)
        title_type = "series"

    return {
        "external": {"source": "tmdb", "id": int(payload["id"])},
        "type": title_type,
        "title": title,
        "original_title": original_title,
        "synopsis": payload.get("overview") or "",
        "genres": [genre["name"] for genre in payload.get("genres", [])],
        "release_date": release_date,
        "year": int(release_date[:4]) if release_date[:4].isdigit() else None,
        "runtime_minutes": runtime,
        "seasons": seasons,
        "episodes_total": episodes_total,
        "directors": directors,
        "cast": cast,
        "studios": [
            company["name"] for company in payload.get("production_companies", [])
        ],
        "poster_url": _tmdb_poster(payload.get("poster_path")),
        "external_rating": payload.get("vote_average"),
        "awards": [],
    }
