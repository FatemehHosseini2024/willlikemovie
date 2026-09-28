"""
Streamlit frontend for willLikeMovie.py

Runs the pipeline once, then lets you work with it interactively:

  * `Predict a movie` - enter genres / year / imdb / country / agerating and get
    the like class, the score, the class probabilities and the KMeans cluster
    from the trained RandomForest models, reusing the pipeline's own
    `mlb_transformer` + `preprocessor` transforms.
  * `Add a movie with your rating` - write a new row (title, genres, year, imdb,
    country, agerating, your score, your like verdict) into the `movieforme`
    table, including genres that are not in the training vocabulary.

Nothing is pre-filled from the `data` variable; every value comes from the form.
"""

import contextlib
import hmac
import importlib.util
import io
import linecache
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from sqlalchemy import MetaData, Table, select

APP_DIR = Path(__file__).resolve().parent
TARGET_SCRIPT = APP_DIR / "willLikeMovie.py"
RUN_LOCK = threading.Lock()

TABLE_NAME = "movieforme"
NON_GENRE_COLUMNS = ("country", "year", "imdb", "agerating", "like", "score", "title", "cluster")
DEFAULT_PASSWORD = "fatemeh138322"
PAGE_TITLE = "willLikeMovie - movie predictions"

CAPTURE_POINTS = {"x": "preprocessor.fit_transform("}


def _capture_lines() -> dict[str, int]:
    """Line numbers where a variable still holds its pre-transform value."""
    source = TARGET_SCRIPT.read_text(encoding="utf-8", errors="ignore").splitlines()
    found: dict[str, int] = {}
    for number in range(1, len(source) + 1):
        line = (linecache.getline(str(TARGET_SCRIPT), number) or "").strip()
        if "=" not in line:
            continue
        name, _, call = line.partition("=")
        name = name.strip()
        for key, marker in CAPTURE_POINTS.items():
            if key not in found and name == key and marker in call:
                found[key] = number
    return found


def _load_pipeline():
    """Execute willLikeMovie.py, keeping everything the dashboard needs."""
    spec = importlib.util.spec_from_file_location("willlikemovie_pipeline", TARGET_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_pipeline() -> dict:
    """Run the script, keeping its printed output and the trained models."""
    stdout, stderr = io.StringIO(), io.StringIO()
    captured: dict = {}
    watch = _capture_lines()

    def tracer(frame, event, arg):
        if frame.f_code.co_filename != str(TARGET_SCRIPT):
            return None
        if event == "line":
            for name, number in watch.items():
                if frame.f_lineno == number:
                    value = frame.f_locals.get(name)
                    if isinstance(value, pd.DataFrame):
                        captured[name] = value.copy()
        return tracer

    with RUN_LOCK:
        plt.close("all")
        sys.settrace(tracer)
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    module = _load_pipeline()
                    error = None
                except Exception:  # surfaced in the UI, never swallowed silently
                    module = None
                    error = sys.exc_info()[1]
        finally:
            sys.settrace(None)

    return {
        "module": module,
        "features": captured.get("x"),
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "error": error,
        "finished_at": datetime.now(),
    }


def get(ns, name, default=None):
    return ns.get(name, default) if ns else default


def metric_row(items) -> None:
    items = [(label, value) for label, value in items if value is not None]
    if not items:
        return
    for column, (label, value) in zip(st.columns(len(items)), items):
        column.metric(label, value)


def genre_options(features) -> list[str]:
    """Genre flag columns the models know about, taken from the training layout."""
    if features is None:
        return []
    return [column for column in features.columns if column not in NON_GENRE_COLUMNS]


def normalize_genre(genre: str) -> str:
    return str(genre).strip().lower().replace(" ", "-")


def clean_genre_list(genres) -> list[str]:
    """Lowercased, hyphenated, de-duplicated genres, order preserved."""
    seen: list[str] = []
    for genre in genres:
        normalized = normalize_genre(genre)
        if normalized and normalized not in seen:
            seen.append(normalized)
    return seen


def build_prediction(ns, features: pd.DataFrame, row: dict) -> dict:
    """Apply the pipeline's own transforms to `row`, then predict like/score/cluster."""
    mlb_transformer = get(ns, "mlb_transformer")
    preprocessor = get(ns, "preprocessor")
    clf_like = get(ns, "clf_like")
    clf_score = get(ns, "clf_score")
    kmeans = get(ns, "kmeans")
    if None in (mlb_transformer, preprocessor, clf_like, clf_score):
        raise RuntimeError("The pipeline did not expose its transforms and models.")

    frame = pd.DataFrame([{
        "genres": clean_genre_list(row.get("genres", [])),
        "year": int(row["year"]),
        "imdb": float(row["imdb"]),
        "country": str(row["country"]).strip().lower(),
        "agerating": float(row["agerating"]),
    }])
    frame = mlb_transformer(frame)
    if features is not None:
        # `mlb_transformer` only emits the genre columns present in the row, so align it
        # on the training layout (same columns, same order) before transforming.
        frame = frame.reindex(columns=list(features.columns), fill_value=0)
    matrix = preprocessor.transform(frame)

    classes = [str(c) for c in clf_like.classes_]
    probabilities = np.asarray(clf_like.predict_proba(matrix), dtype=float)[0]
    return {
        "like": str(clf_like.predict(matrix)[0]),
        "score": f"{float(clf_score.predict(matrix)[0]):.3f}",
        "cluster": str(int(kmeans.predict(matrix)[0])) if kmeans is not None else None,
        "probabilities": pd.DataFrame(
            {"class": classes[:len(probabilities)], "probability": np.round(probabilities, 4)}
        ),
        "row": row,
    }


def show_prediction_result(result: dict, heading: str) -> None:
    """Render a prediction dict: like class, score, cluster and probabilities."""
    st.markdown(heading)
    metric_row([
        ("predicted like (y_pred_new)", result.get("like")),
        ("predicted score (y_pred_new_score)", result.get("score")),
        ("cluster (new_cls)", result.get("cluster")),
    ])
    probability_frame = result.get("probabilities")
    if probability_frame is not None and len(probability_frame):
        st.markdown("**`clf_like.predict_proba(...)`**")
        st.dataframe(probability_frame, width="stretch")
        st.bar_chart(
            probability_frame.set_index("class")["probability"], y_label="probability"
        )


def show_predict_form(ns, features) -> None:
    """Predict like / score / cluster for the values entered in the form."""
    st.subheader("Predict a movie")
    st.caption("Enter the fields the models were trained on. Every value comes from the form; "
               "nothing is pre-filled.")

    options = genre_options(features)
    with st.form("predict_movie"):
        left, right = st.columns(2)
        with left:
            genres = st.multiselect("genres", options)
            year = st.number_input("year", min_value=1888, max_value=2100, value=None, step=1)
            imdb = st.number_input("imdb", min_value=0.0, max_value=10.0, value=None, step=0.1)
        with right:
            country = st.text_input("country")
            age_rating = st.number_input("agerating", min_value=0, max_value=100, value=None, step=1)
        submitted = st.form_submit_button("Predict", type="primary")

    if not submitted:
        st.session_state.pop("custom_prediction", None)
        return

    missing = [
        name for name, value in (("genres", genres), ("year", year), ("imdb", imdb),
                                 ("country", country.strip()), ("agerating", age_rating))
        if value is None or value == "" or (isinstance(value, list) and not value)
    ]
    if missing:
        st.warning("Fill in: " + ", ".join(f"`{name}`" for name in missing) + ".")
        st.session_state.pop("custom_prediction", None)
        return

    row = {
        "genres": clean_genre_list(genres),
        "year": int(year),
        "imdb": float(imdb),
        "country": country.strip(),
        "agerating": float(age_rating),
    }
    try:
        with st.spinner("Predicting..."):
            st.session_state["custom_prediction"] = build_prediction(ns, features, row)
    except Exception as exc:
        st.session_state.pop("custom_prediction", None)
        st.error(f"Prediction failed: `{type(exc).__name__}: {exc}`")

    result = st.session_state.get("custom_prediction")
    if result is not None:
        st.divider()
        show_prediction_result(result, "**Prediction for the entered values**")


def insert_movie(engine, record: dict) -> dict:
    """Insert one row into `movieforme` and read it back."""
    metadata = MetaData()
    table = Table(TABLE_NAME, metadata, autoload_with=engine)
    with engine.begin() as connection:
        result = connection.execute(table.insert().values(**record))
        row = connection.execute(
            select(table).where(table.c.idmovieforme == result.inserted_primary_key[0])
        ).mappings().first()
    return dict(row) if row else dict(record)


def show_add_movie(ns, features) -> None:
    """Form to store a new movie together with the rating the user gave it."""
    st.subheader("Add a movie with your rating")
    st.caption(f"Writes a row to `{TABLE_NAME}` with the fields the pipeline reads: genres, year, "
               "imdb, country, agerating, title, your `score` and your `like` verdict.")

    engine = get(ns, "engine")
    if engine is None:
        st.warning("The pipeline did not expose its database engine.")
        return

    options = genre_options(features)
    with st.form("add_movie"):
        left, right = st.columns(2)
        with left:
            title = st.text_input("title")
            year = st.number_input("year", min_value=1888, max_value=2100, value=None, step=1)
            imdb = st.number_input("imdb", min_value=0.0, max_value=10.0, value=None, step=0.1)
        with right:
            country = st.text_input("country")
            age_rating = st.number_input("agerating", min_value=0, max_value=100, value=None, step=1)
            score = st.number_input("your score", min_value=0.0, max_value=10.0, value=None, step=0.1)
            like = st.selectbox("did you like it?", ["yes", "no"])
        known = st.multiselect("genres", options)
        extra = st.text_input(
            "genres not in the list",
            placeholder="type new genres, comma separated",
        )
        submitted = st.form_submit_button("Add to the database", type="primary")

    if not submitted:
        return

    genres = clean_genre_list(known + [part for part in extra.split(",") if part.strip()])
    new_genres = [genre for genre in genres if genre not in options]

    problems = []
    if not title.strip():
        problems.append("`title` is required.")
    elif len(title.strip()) > 100:
        problems.append("`title` must be at most 100 characters.")
    if not genres:
        problems.append("Pick at least one genre, or type new ones below.")
    genres_value = "|".join(genres)
    if len(genres_value) > 200:
        problems.append(f"The genres string is {len(genres_value)} characters, the column allows 200.")
    if not country.strip():
        problems.append("`country` is required.")
    elif len(country.strip()) > 100:
        problems.append("`country` must be at most 100 characters.")
    for name, value in (("year", year), ("imdb", imdb), ("agerating", age_rating),
                        ("your score", score)):
        if value is None:
            problems.append(f"`{name}` is required.")
    if problems:
        for problem in problems:
            st.error(problem)
        return

    record = {
        "title": title.strip(),
        "genres": genres_value,
        "year": int(year),
        "imdb": float(imdb),
        "country": country.strip().lower(),
        "agerating": int(age_rating),
        "score": float(score),
        "like": like,
    }
    try:
        with st.spinner("Writing to the database..."):
            stored = insert_movie(engine, record)
    except Exception as exc:
        st.error(f"Could not insert the row: `{type(exc).__name__}: {exc}`")
        return

    st.success(f"Added **{stored.get('title')}** to `{TABLE_NAME}` "
               f"(id {stored.get('idmovieforme')}).")
    if new_genres:
        st.warning(
            "These genres are new to the models: " + ", ".join(f"`{genre}`" for genre in new_genres)
            + ". The next run of willLikeMovie.py will fail at `preprocessor.transform(data)`, "
            "because the training data gains a column the sample rows do not have. The sample "
            "rows in willLikeMovie.py have to be aligned on the training columns."
        )
    st.dataframe(pd.DataFrame([stored]), width="stretch")
    st.info("Press `Re-run pipeline` in the sidebar to retrain the models on the new row.")


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_movies(engine, query: str, limit: int = 100) -> pd.DataFrame:
    """Movies whose title matches `query`; the most recent ones when it is empty."""
    metadata = MetaData()
    table = Table(TABLE_NAME, metadata, autoload_with=engine)
    columns = [column.name for column in table.columns]
    with engine.connect() as connection:
        if query.strip():
            statement = (
                select(table)
                .where(table.c.title.like(f"%{escape_like(query.strip())}%", escape="\\"))
                .order_by(table.c.title)
                .limit(limit)
            )
        else:
            statement = select(table).order_by(table.c.idmovieforme.desc()).limit(limit)
        rows = connection.execute(statement).mappings().all()
    return pd.DataFrame(list(rows), columns=columns)


def update_movie(engine, movie_id: int, record: dict) -> dict:
    """Overwrite the editable columns of one `movieforme` row and read it back."""
    metadata = MetaData()
    table = Table(TABLE_NAME, metadata, autoload_with=engine)
    with engine.begin() as connection:
        connection.execute(
            table.update().where(table.c.idmovieforme == movie_id).values(**record)
        )
        row = connection.execute(
            select(table).where(table.c.idmovieforme == movie_id)
        ).mappings().first()
    return dict(row) if row else dict(record)


def show_search_and_edit(ns, features) -> None:
    """Look a movie up by name and edit the row stored in the database."""
    st.subheader("Search and edit an existing movie")
    st.caption(f"Search `{TABLE_NAME}` by title, pick a result and change any field. "
               "The update is written straight to the database.")

    engine = get(ns, "engine")
    if engine is None:
        st.warning("The pipeline did not expose its database engine.")
        return

    query = st.text_input("movie name", key="search_query", placeholder="type part of a title")
    try:
        results = search_movies(engine, query)
    except Exception as exc:
        st.error(f"Search failed: `{type(exc).__name__}: {exc}`")
        return

    st.caption(f"{len(results)} matching row(s)"
               + ("" if query.strip() else " - showing the most recent, type to search"))
    st.dataframe(results, width="stretch")

    if results.empty:
        st.info("No movie matches that title.")
        return

    labels = {
        int(row.idmovieforme): f"{row.title} ({row.year}) - id {row.idmovieforme}"
        for row in results.itertuples()
    }
    movie_id = st.selectbox(
        "movie to edit", list(labels), format_func=lambda key: labels[key], key="movie_to_edit"
    )
    current = results[results["idmovieforme"] == movie_id].iloc[0]

    options = genre_options(features)
    current_genres = clean_genre_list(str(current.get("genres", "")).split("|"))
    known = [genre for genre in current_genres if genre in options]
    extra = [genre for genre in current_genres if genre not in options]

    with st.form(f"edit_movie_{movie_id}"):
        left, right = st.columns(2)
        with left:
            title = st.text_input("title", value=str(current.get("title", "")),
                                  key=f"title_{movie_id}")
            year = st.number_input("year", min_value=1888, max_value=2100,
                                   value=int(current.get("year") or 1888), step=1,
                                   key=f"year_{movie_id}")
            imdb = st.number_input("imdb", min_value=0.0, max_value=10.0,
                                   value=float(current.get("imdb") or 0.0), step=0.1,
                                   key=f"imdb_{movie_id}")
        with right:
            country = st.text_input("country", value=str(current.get("country", "")),
                                    key=f"country_{movie_id}")
            age_rating = st.number_input("agerating", min_value=0, max_value=100,
                                         value=int(float(current.get("agerating") or 0)), step=1,
                                         key=f"agerating_{movie_id}")
            score = st.number_input("score", min_value=0.0, max_value=10.0,
                                    value=float(current.get("score") or 0.0), step=0.1,
                                    key=f"score_{movie_id}")
            like = st.selectbox("did you like it?", ["yes", "no"],
                                index=0 if str(current.get("like", "yes")).lower() == "yes" else 1,
                                key=f"like_{movie_id}")
        known_genres = st.multiselect("genres", options, default=known, key=f"genres_{movie_id}")
        new_genres = st.text_input("genres not in the list",
                                   value=", ".join(extra),
                                   placeholder="type new genres, comma separated",
                                   key=f"extra_genres_{movie_id}")
        submitted = st.form_submit_button("Save changes", type="primary")

    if not submitted:
        st.session_state.pop("edit_result", None)
        return

    genres = clean_genre_list(known_genres + [part for part in new_genres.split(",") if part.strip()])

    problems = []
    if not title.strip():
        problems.append("`title` is required.")
    elif len(title.strip()) > 100:
        problems.append("`title` must be at most 100 characters.")
    if not genres:
        problems.append("Pick at least one genre, or type new ones below.")
    genres_value = "|".join(genres)
    if len(genres_value) > 200:
        problems.append(f"The genres string is {len(genres_value)} characters, the column allows 200.")
    if not country.strip():
        problems.append("`country` is required.")
    elif len(country.strip()) > 100:
        problems.append("`country` must be at most 100 characters.")
    if problems:
        for problem in problems:
            st.error(problem)
        return

    record = {
        "title": title.strip(),
        "genres": genres_value,
        "year": int(year),
        "imdb": float(imdb),
        "country": country.strip().lower(),
        "agerating": int(age_rating),
        "score": float(score),
        "like": like,
    }
    try:
        with st.spinner("Updating the database..."):
            st.session_state["edit_result"] = update_movie(engine, movie_id, record)
    except Exception as exc:
        st.session_state.pop("edit_result", None)
        st.error(f"Could not update the row: `{type(exc).__name__}: {exc}`")
        return

    added_genres = [genre for genre in genres if genre not in options]
    st.success(f"Updated **{record['title']}** (id {movie_id}).")
    if added_genres:
        st.warning(
            "These genres are new to the models: " + ", ".join(f"`{genre}`" for genre in added_genres)
            + ". The next run of willLikeMovie.py will fail at `preprocessor.transform(data)`, "
            "because the training data gains a column the sample rows do not have. The sample "
            "rows in willLikeMovie.py have to be aligned on the training columns."
        )
    st.dataframe(pd.DataFrame([st.session_state["edit_result"]]), width="stretch")
    st.info("Press `Re-run pipeline` in the sidebar to retrain the models on the new values.")


def require_password() -> bool:
    """Block the whole app until the correct password is entered.

    The accepted password is DEFAULT_PASSWORD, or the APP_PASSWORD secret when the host
    sets one. Once the right password is given the session stays unlocked, so the user
    is not asked again on every interaction.
    """
    if st.session_state.get("unlocked"):
        return True

    expected = os.environ.get("APP_PASSWORD") or DEFAULT_PASSWORD
    st.markdown("### willLikeMovie")
    st.caption("This app is password protected. Enter the password to continue.")
    entered = st.text_input("password", type="password", key="app_password")
    if not entered:
        return False
    if not hmac.compare_digest(entered, expected):
        st.error("Wrong password.")
        return False

    st.session_state["unlocked"] = True
    return True


def main() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.title("willLikeMovie")
    st.caption("Predict a movie with the trained models, or store a new movie with your own "
               "rating in the database.")

    if not require_password():
        st.stop()
        return

    if not TARGET_SCRIPT.exists():
        st.error(f"Missing pipeline script: {TARGET_SCRIPT}")
        return

    with st.sidebar:
        st.header("Run control")
        st.write(f"Script: `{TARGET_SCRIPT.name}`")
        st.caption("Trains both models, clusters the data and writes `movieforme_cluster.csv`. "
                   "Press refresh to retrain.")
        refresh = st.button("Re-run pipeline", type="primary")
        if "run" in st.session_state:
            st.success(f"Last run: {st.session_state['run']['finished_at']:%Y-%m-%d %H:%M:%S}")

    if refresh or "run" not in st.session_state:
        with st.spinner("Training the models, this can take a while..."):
            st.session_state["run"] = run_pipeline()

    run = st.session_state["run"]

    if run["error"] is not None:
        st.error(
            f"The pipeline raised `{type(run['error']).__name__}: {run['error']}`. "
            "Check that MySQL is running and the `willlikemovie` database is reachable."
        )
        with st.expander("stderr", expanded=True):
            st.code(run["stderr"].rstrip(), language="text")
        return

    ns = run["module"].__dict__
    st.sidebar.metric("known genres", len(genre_options(run["features"])))

    show_predict_form(ns, run["features"])
    st.divider()
    show_add_movie(ns, run["features"])
    st.divider()
    show_search_and_edit(ns, run["features"])


if __name__ == "__main__":
    main()
