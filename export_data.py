"""Export the movieforme table to seed/movieforme.csv for a fresh deployment."""
import csv
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine

APP_DIR = Path(__file__).resolve().parent
engine = create_engine("mysql+pymysql://root:1234567@localhost/willlikemovie")
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
