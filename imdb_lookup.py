"""Live movie data from IMDb, for filling in the app's forms on demand.

Uses the same data endpoint the IMDb website itself calls, so the values are current
rather than a periodic dump. It is undocumented and unauthenticated, so treat it as a
convenience: every field it fills can be corrected by hand in the form.
"""
import requests

ENDPOINT = "https://api.graphql.imdb.com/"
HOME = "https://www.imdb.com/"

HEADERS = {
    "content-type": "application/json",
    "origin": "https://www.imdb.com",
    "referer": HOME,
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "x-imdb-client-name": "imdb-web-next-localized",
    "x-imdb-user-language": "en-US",
    "x-imdb-user-country": "US",
}

SEARCH_QUERY = """
query { mainSearch(first: 20, options: {searchTerm: "%(term)s"}) {
  edges { node { entity { ... on Title {
    id titleText { text }
    titleType { id text }
    releaseYear { year }
    ratingsSummary { aggregateRating voteCount }
  } } } } } }
"""

DETAIL_QUERY = """
query { title(id: "%(imdb_id)s") {
  id titleText { text }
  releaseYear { year }
  titleType { id text }
  genres { genres { text } }
  ratingsSummary { aggregateRating voteCount }
  countriesOfOrigin { countries { text } }
  certificate { rating }
  runtime { seconds }
  plot { plotText { plainText } }
} }
"""

MOVIE_TYPES = {"movie", "tvmovie", "tvspecial", "video", "short", "tvmovieepisode"}

COUNTRY_NAMES = {
    "united states": "usa",
    "united kingdom": "uk",
    "south korea": "south-korea",
    "north korea": "north-korea",
    "hong kong": "hong-kong",
    "czech republic": "czech-republic",
    "west germany": "germany",
}

CERTIFICATE_AGES = {
    "g": 0, "u": 0, "ua": 0, "ur": 0, "uncensored": 0,
    "pg": 6, "pg-12": 12, "pg12": 12, "pg-13": 13, "pg13": 13, "g6": 6, "g7": 7, "g3": 3,
    "12": 12, "12a": 12, "13": 13, "14": 14, "15": 15, "15a": 15, "16": 16, "16a": 16,
    "17": 17, "18": 18, "18a": 18, "r": 18, "nc-17": 18, "x": 18, "xxx": 18,
    "tv-y": 0, "tv-y7": 7, "tv-g": 0, "tv-pg": 6, "tv-14": 14, "tv-ma": 18,
}

_session = None


def _client() -> requests.Session:
    """A browser-like session. IMDb answers 403 without these headers."""
    global _session
    if _session is None:
        client = requests.Session()
        client.headers.update(HEADERS)
        try:
            client.get(HOME, timeout=20)
        except requests.RequestException:
            pass
        _session = client
    return _session


def _run(query: str) -> dict:
    try:
        response = _client().post(ENDPOINT, json={"query": query}, timeout=25)
    except requests.RequestException as exc:
        raise RuntimeError(f"could not reach IMDb: {exc}") from exc
    if response.status_code != 200:
        raise RuntimeError(f"IMDb answered {response.status_code}")
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"IMDb rejected the query: {payload['errors'][0]['message'][:120]}")
    return payload["data"]


def _clean_genres(values) -> list[str]:
    return [str(value).strip().lower().replace(" ", "-") for value in values or []]


def _clean_country(values) -> str:
    for value in values or []:
        name = str(value).strip().lower()
        if name:
            return COUNTRY_NAMES.get(name, name.replace(" ", "-"))
    return ""


def _clean_age(certificate) -> int | None:
    """Turn an IMDb certificate such as 'PG-13' or '15A' into a number."""
    if not certificate:
        return None
    text = str(certificate).strip().lower()
    if text in CERTIFICATE_AGES:
        return CERTIFICATE_AGES[text]
    digits = "".join(character for character in text if character.isdigit())
    if digits:
        return min(int(digits), 100)
    return None


def search_titles(term: str, limit: int = 8) -> list[dict]:
    """Movies matching `term`, newest and most relevant first."""
    safe = str(term).replace("\\", "\\\\").replace('"', '\\"')
    data = _run(SEARCH_QUERY % {"term": safe})
    results = []
    for edge in data.get("mainSearch", {}).get("edges", []):
        entity = edge["node"]["entity"]
        if not entity or not entity.get("id"):
            continue
        if str(entity.get("titleType", {}).get("id", "")).lower() not in MOVIE_TYPES:
            continue
        ratings = entity.get("ratingsSummary") or {}
        rating = ratings.get("aggregateRating")
        results.append({
            "imdb_id": entity["id"],
            "title": entity["titleText"]["text"],
            "year": (entity.get("releaseYear") or {}).get("year"),
            "rating": rating,
            "votes": ratings.get("voteCount"),
        })

    # IMDb's own ordering is not by relevance, so put the best known titles first
    results.sort(key=lambda item: item.get("votes") or 0, reverse=True)
    return results[:limit]


def get_title(imdb_id: str) -> dict:
    """Full detail for one IMDb title id, shaped for the app's forms."""
    data = _run(DETAIL_QUERY % {"imdb_id": imdb_id})
    title = data.get("title")
    if not title:
        raise RuntimeError(f"IMDb has no title {imdb_id}")

    ratings = title.get("ratingsSummary") or {}
    certificate = (title.get("certificate") or {}).get("rating")
    runtime = (title.get("runtime") or {}).get("seconds")
    plot = ((title.get("plot") or {}).get("plotText") or {}).get("plainText")
    return {
        "imdb_id": title["id"],
        "title": title["titleText"]["text"],
        "year": (title.get("releaseYear") or {}).get("year"),
        "genres": _clean_genres([genre["text"] for genre in (title.get("genres") or {}).get("genres", [])]),
        "rating": ratings.get("aggregateRating"),
        "votes": ratings.get("voteCount"),
        "country": _clean_country(
            [country["text"] for country in (title.get("countriesOfOrigin") or {}).get("countries", [])]
        ),
        "certificate": certificate,
        "age_rating": _clean_age(certificate),
        "runtime_minutes": round(runtime / 60) if runtime else None,
        "plot": plot,
    }
