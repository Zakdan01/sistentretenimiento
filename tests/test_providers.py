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
    "title_japanese": "進撃の巨人",
    "synopsis": "La humanidad sobrevive tras enormes murallas.",
    "type": "TV",
    "episodes": 25,
    "duration": "24 min per ep",
    "year": 2013,
    "aired": {"from": "2013-04-07T00:00:00+00:00"},
    "score": 8.5,
    "genres": [{"name": "Action"}, {"name": "Fantasy"}],
    "studios": [{"name": "Wit Studio"}],
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
    assert result["poster_url"] == "https://cdn.example/poster.jpg"


def test_jikan_details_builds_importable_payload():
    details = fetch_jikan(16498, get=make_get(JIKAN_ANIME))

    assert details["release_date"] == "2013-04-07"
    assert details["episodes_total"] == 25
    assert details["seasons"] == [{"number": 1, "episodes": 25}]
    assert details["studios"] == ["Wit Studio"]
    assert details["runtime_minutes"] is None


def test_jikan_movie_details_use_runtime():
    movie = {
        **JIKAN_ANIME,
        "type": "Movie",
        "episodes": 1,
        "duration": "125 min",
    }

    details = fetch_jikan(199, get=make_get(movie))

    assert details["runtime_minutes"] == 125
    assert details["seasons"] == []
    assert details["episodes_total"] is None


def test_tmdb_search_without_key_raises():
    with pytest.raises(ProviderError, match="TMDB_API_KEY"):
        search_tmdb("inception", api_key="")


TMDB_MOVIE = {
    "id": 27205,
    "title": "Inception",
    "original_title": "Inception",
    "overview": "Dom Cobb roba secretos dentro de los sueños.",
    "genres": [{"name": "Ciencia ficción"}],
    "release_date": "2010-07-16",
    "runtime": 148,
    "vote_average": 8.4,
    "poster_path": "/poster.jpg",
    "credits": {
        "cast": [{"name": "Leonardo DiCaprio"}, {"name": "Elliot Page"}],
        "crew": [{"job": "Director", "name": "Christopher Nolan"}],
    },
    "production_companies": [{"name": "Warner Bros."}],
}


def test_tmdb_movie_details_maps_credits_and_runtime():
    details = fetch_tmdb("movie", 27205, api_key="k", get=make_get(TMDB_MOVIE))

    assert details["type"] == "movie"
    assert details["directors"] == ["Christopher Nolan"]
    assert details["cast"] == ["Leonardo DiCaprio", "Elliot Page"]
    assert details["runtime_minutes"] == 148
    assert details["seasons"] == []
    assert details["poster_url"] == "https://image.tmdb.org/t/p/w500/poster.jpg"


TMDB_TV = {
    "id": 1396,
    "name": "Breaking Bad",
    "original_name": "Breaking Bad",
    "overview": "Un profesor de química con cáncer terminal.",
    "genres": [{"name": "Drama"}],
    "first_air_date": "2008-01-20",
    "vote_average": 8.9,
    "poster_path": "/bb.jpg",
    "seasons": [
        {"season_number": 1, "episode_count": 7, "air_date": "2008-01-20"},
        {"season_number": 2, "episode_count": 13, "air_date": "2009-03-08"},
    ],
    "credits": {
        "cast": [{"name": "Bryan Cranston"}],
        "crew": [{"job": "Director", "name": "Vince Gilligan"}],
    },
    "production_companies": [{"name": "Sony Pictures Television"}],
}


def test_tmdb_series_details_map_seasons():
    details = fetch_tmdb("tv", 1396, api_key="k", get=make_get(TMDB_TV))

    assert details["type"] == "series"
    assert details["runtime_minutes"] is None
    assert details["episodes_total"] == 20
    assert details["seasons"] == [
        {"number": 1, "episodes": 7, "air_date": "2008-01-20"},
        {"number": 2, "episodes": 13, "air_date": "2009-03-08"},
    ]
