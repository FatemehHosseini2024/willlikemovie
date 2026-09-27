# Deploying to Streamlit Community Cloud

`app.py` runs `willLikeMovie.py` on every new session, and that script trains its models from the
`movieforme` table. The connection string comes from the environment variable
`WILLLIKEMOVIE_DB_URL`; when it is unset the pipeline uses the committed SQLite file
`data/movieforme.db`, so no credentials are needed and nothing sensitive is stored in the
repository.

To run against your own MySQL instead, set the variable before starting the app:

```powershell
$env:WILLLIKEMOVIE_DB_URL = "mysql+pymysql://USER:PASSWORD@HOST:3306/willlikemovie"
streamlit run app.py
```

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

1. Go to https://share.streamlit.io and connect the repository. A public repository needs no
   GitHub App authorization, so this is one click; a private one asks you to authorize the
   Streamlit app for that repository first.
2. In **Deploy > Settings > Secrets** add:

   ```
   WILLLIKEMOVIE_DB_URL = "sqlite:///data/movieforme.db"
   APP_PASSWORD        = "the password you chose"
   ```

   `APP_PASSWORD` is what keeps the database from being edited by anyone who finds the URL: when
   it is set, the app asks for the password before showing anything. `WILLLIKEMOVIE_DB_URL` is
   optional here, since the deployed default is already the SQLite file, but setting it makes the
   intent explicit.

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
- No database credentials are committed anywhere in this repository. `WILLLIKEMOVIE_DB_URL` is
  read from the environment, and `APP_PASSWORD` lives in the deployment secrets.
- `movieforme_cluster.csv` is written on every run into the app's temporary filesystem.
