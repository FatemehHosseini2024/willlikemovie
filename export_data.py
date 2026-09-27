"""Export the movieforme table to seed/movieforme.csv for a fresh deployment.

The source database comes from the WILLLIKEMOVIE_DB_URL environment variable, so no
credentials live in the repository:

    set WILLLIKEMOVIE_DB_URL=mysql+pymysql://user:password@host:3306/willlikemovie
    python export_data.py
"""
import csv
import os
import sys
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine

APP_DIR = Path(__file__).resolve().parent
url = os.environ.get("WILLLIKEMOVIE_DB_URL")
if not url:
    sys.exit("WILLLIKEMOVIE_DB_URL is not set. See the docstring for an example.")

engine = create_engine(url)
metadata = MetaData()
table = Table("movieforme", metadata, autoload_with=engine)

with engine.connect() as connection:
    rows = connection.execute(table.select().order_by(table.c.idmovieforme)).fetchall()

target = APP_DIR / "seed" / "movieforme.csv"
target.parent.mkdir(exist_ok=True)
columns = [column.name for column in table.columns]
with target.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(columns)
    for row in rows:
        values = row._mapping
        writer.writerow(["" if values[name] is None else values[name] for name in columns])

print(f"exported {len(rows)} rows to {target}")
print("columns:", columns)
