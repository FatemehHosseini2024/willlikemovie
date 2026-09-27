# Deploying to Streamlit Community Cloud

`app.py` runs `willLikeMovie.py` on every new session, and that script trains its models from the
`movieforme` table. The connection string comes from the environment variable
`WILLLIKEMOVIE_DB_URL`; when it is not set the pipeline falls back to your local
`mysql+pymysql://root:1234567@localhost/willlikemovie`, so local development is unaffected.

The hosted version uses the committed SQLite file `data/movieforme.db` (the same 117 rows), which
means no database account and no card is needed. See *Persistence* below before you rely on it.

## Files in the repository

```
app.py                    the Streamlit frontend (entry point)
willLikeMovie.py          the pipeline it runs
requirements.txt          pinned dependencies
.streamlit/config.toml    server + theme settings
data/movieforme.db        the SQLite database, 117 movies
seed/movieforme.csv       the same rows as CSV
seed/seed_data.py         creates the table and loads the CSV into any database
export_data.py            local helper, re-exports seed/movieforme.csv from the local MySQL
```

`omdbapi.py`, `movieforme_cluster*.csv` and `__pycache__` are not needed on the server.

## 1. Rebuild the SQLite database from scratch (optional)

Only needed if `data/movieforme.db` is ever lost or you want to refresh it from the CSV:

```powershell
$env:WILLLIKEMOVIE_DB_URL = "sqlite:///data/movieforme.db"
python seed\seed_data.py --force
```

To pull newer rows out of your local MySQL first, run `python export_data.py`, then the command
above.

## 2. Push the code to GitHub

Create a **new, empty repository** (do not reuse the `VS_code_projects` repository, it contains
all your coursework). In this folder:

```powershell
git init
git add app.py willLikeMovie.py requirements.txt .streamlit data seed DEPLOY.md export_data.py .gitignore
git commit -m "Deploy willLikeMovie to Streamlit Community Cloud"
git branch -M main
git remote add origin git@github.com:FatemehHosseini2024/willlikemovie.git
git push -u origin main
```

## 3. Deploy the app

1. Go to https://share.streamlit.io and connect the repository.
2. In **Deploy > Settings > Secrets** add:

   ```
   WILLLIKEMOVIE_DB_URL = "sqlite:///data/movieforme.db"
   APP_PASSWORD        = "the password you chose"
   ```

   `APP_PASSWORD` is what keeps the database from being edited by anyone who finds the URL: when
   it is set, the app asks for the password before showing anything. Leave
   `WILLLIKEMOVIE_DB_URL` out and the app would fall back to MySQL on localhost, which does not
   exist on the server, so set it explicitly.

3. Deploy. The first page load trains the models, which takes roughly a minute.

## Persistence, and how to get a real database later

The free Community Cloud filesystem is **ephemeral**: movies added or edited through the hosted
app live in the running container and are gone after the next redeploy, a branch switch or a
period of inactivity. The 117 committed rows always come back, because they are in the
repository.

When you want edits to stick, point `WILLLIKEMOVIE_DB_URL` at a real MySQL server and the same
code works unchanged, because every query goes through SQLAlchemy:

```
WILLLIKEMOVIE_DB_URL = "mysql+pymysql://USER:PASSWORD@HOST:PORT/DBNAME?charset=utf8mb4"
```

Then load the rows with `python seed\seed_data.py` against that server. Aiven (aiven.io) has a
free MySQL plan, or any VM you own will do.

## Other things to know

- The pipeline reruns on every new session, so the first request after an idle period pays the
  training cost again.
- The password in `willLikeMovie.py` is only the local fallback. It is committed to the
  repository, so rotate that local database password if the machine is reachable from anywhere.
- `movieforme_cluster.csv` is written on every run into the app's temporary filesystem.
