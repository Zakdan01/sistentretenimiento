import pytest

from app.catalog.providers import (
    ProviderError,
    fetch_jikan,
    fetch_tmdb,
    search_jikan,
    search_tmdb,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def make_get(payload):
    def get(url, params=None, timeout=None):
        return FakeResponse(payload)

    return get


JIKAN_ANIME = {
    "mal_id": 16498,
    "title": "Shingeki no Kyojin",
    "title_english": "Attack on Titan",
    "synopsis": "La humanidad sobrevive tras enormes murallas.",
    "type": "TV",
    "episodes": 25,
    "year": 2013,
    "aired": {"from": "2013-04-07T00:00:00+00:00"},
    "score": 8.5,
    "genres": [{"name": "Acción"}, {"name": "Fantasía"}],
    "images": {"jpg": {"large_image_url": "https://cdn.example/poster.jpg"}},
}


def test_jikan_search_maps_results():
    payload = {"data": [JIKAN_ANIME]}

    results = search_jikan("attack", get=make_get(payload))

    assert len(results) == 1
    result = results[0]
    assert result["external"] == {"source": "jikan", "id": 16498}
    assert result["type"] == "anime"
    assert result["title"] == "Shingeki no Kyojin"
    assert result["year"] == 2013
    assert result["genres"] == ["Acción", "Fantasía"]
    assert result["external_rating"] == 8.5
    assert result["poster_url"] == "https://cdn.example/poster.jpg"
    assert "murallas" in result["synopsis"]


def test_jikan_details_builds_importable_payload():
    details = fetch_jikan(16498, get=make_get(JIKAN_ANIME))

    assert details["external"] == {"source": "jikan", "id": 16498}
    assert details["type"] == "anime"
    assert details["year"] == 2013


def test_jikan_year_falls_back_to_aired_date():
    anime = {**JIKAN_ANIME, "year": None, "aired": {"from": "2013-04-07T00:00:00+00:00"}}

    details = fetch_jikan(16498, get=make_get(anime))

    assert details["year"] == 2013


def test_tmdb_search_without_key_raises():
    with pytest.raises(ProviderError, match="TMDB_API_KEY"):
        search_tmdb("inception", api_key="")


def test_tmdb_search_maps_movies_and_series():
    payload = {
        "results": [
            {
                "media_type": "movie",
                "id": 27205,
                "title": "Inception",
                "release_date": "2010-07-16",
                "overview": "Dom Cobb roba secretos dentro de los sueños.",
                "vote_average": 8.4,
                "poster_path": "/poster.jpg",
            },
            {
                "media_type": "tv",
                "id": 1396,
                "name": "Breaking Bad",
                "first_air_date": "2008-01-20",
                "overview": "Un profesor de química con cáncer terminal.",
                "vote_average": 8.9,
                "poster_path": "/bb.jpg",
            },
            {"media_type": "person", "id": 1, "name": "Alguien"},
        ]
    }

    results = search_tmdb("inception", api_key="k", get=make_get(payload))

    assert [result["type"] for result in results] == ["movie", "series"]
    assert results[0]["year"] == 2010
    assert results[1]["year"] == 2008
    assert results[0]["poster_url"] == "https://image.tmdb.org/t/p/w500/poster.jpg"


TMDB_MOVIE = {
    "id": 27205,
    "title": "Inception",
    "overview": "Dom Cobb roba secretos dentro de los sueños.",
    "genres": [{"name": "Ciencia ficción"}],
    "release_date": "2010-07-16",
    "vote_average": 8.4,
    "poster_path": "/poster.jpg",
}


def test_tmdb_movie_details_map_core_fields():
    details = fetch_tmdb("movie", 27205, api_key="k", get=make_get(TMDB_MOVIE))

    assert details["type"] == "movie"
    assert details["title"] == "Inception"
    assert details["year"] == 2010
    assert details["genres"] == ["Ciencia ficción"]
    assert details["external_rating"] == 8.4
    assert details["poster_url"] == "https://image.tmdb.org/t/p/w500/poster.jpg"


TMDB_TV = {
    "id": 1396,
    "name": "Breaking Bad",
    "overview": "Un profesor de química con cáncer terminal.",
    "genres": [{"name": "Drama"}],
    "first_air_date": "2008-01-20",
    "vote_average": 8.9,
    "poster_path": "/bb.jpg",
}


def test_tmdb_series_details_use_series_type():
    details = fetch_tmdb("tv", 1396, api_key="k", get=make_get(TMDB_TV))

    assert details["type"] == "series"
    assert details["title"] == "Breaking Bad"
    assert details["year"] == 2008
    assert details["genres"] == ["Drama"]


def test_tmdb_rejects_invalid_media_type():
    with pytest.raises(ProviderError, match="válido"):
        fetch_tmdb("person", 1, api_key="k", get=make_get({}))
