"""Create the `movieforme` table on the target database and load seed/movieforme.csv.

Usage (locally, against the hosted database):

    set WILLLIKEMOVIE_DB_URL=mysql+pymysql://user:password@host:3306/dbname
    python seed/seed_data.py            # refuses to run if the table has rows
    python seed/seed_data.py --force    # drops the table first, then reloads
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import Column, Float, Integer, MetaData, String, Table, create_engine, inspect, text

SEED_FILE = Path(__file__).resolve().parent / "movieforme.csv"
TABLE_NAME = "movieforme"


def table_definition() -> Table:
    return Table(
        TABLE_NAME,
        MetaData(),
        Column("idmovieforme", Integer, primary_key=True, autoincrement=True),
        Column("genres", String(200), nullable=False),
        Column("year", Integer, nullable=False),
        Column("imdb", Float, nullable=False),
        Column("country", String(100), nullable=False),
        Column("agerating", Integer),
        Column("like", String(45)),
        Column("score", Float),
        Column("title", String(100), nullable=False),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="drop the table before loading")
    args = parser.parse_args()

    url = os.environ.get("WILLLIKEMOVIE_DB_URL")
    if not url:
        print("WILLLIKEMOVIE_DB_URL is not set. Example:")
        print("  set WILLLIKEMOVIE_DB_URL=mysql+pymysql://user:password@host:3306/dbname")
        return 1

    engine = create_engine(url)
    connection = engine.connect()
    try:
        existing = TABLE_NAME in inspect(connection).get_table_names()
        if existing:
            count = connection.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar()
            print(f"{TABLE_NAME} already exists with {count} row(s).")
            if count and not args.force:
                print("Nothing to do. Use --force to drop and reload it.")
                return 0
        if not existing or args.force:
            connection.commit()
            if args.force:
                table_definition().drop(connection, checkfirst=True)
                print("dropped the existing table")
            table_definition().create(connection, checkfirst=True)
            connection.commit()
            print(f"created {TABLE_NAME}")
    finally:
        connection.close()

    frame = pd.read_csv(SEED_FILE)
    frame["year"] = frame["year"].astype("Int64")
    frame["agerating"] = frame["agerating"].astype("Int64")
    frame["idmovieforme"] = frame["idmovieforme"].astype("Int64")
    frame = frame[[column.name for column in table_definition().columns]]
    frame.to_sql(TABLE_NAME, engine, if_exists="append", index=False)

    with engine.connect() as connection:
        total = connection.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar()
        sample = connection.execute(
            text(f"SELECT idmovieforme, title, genres FROM {TABLE_NAME} ORDER BY idmovieforme LIMIT 3")
        ).fetchall()
    print(f"loaded {len(frame)} rows, table now holds {total}")
    for row in sample:
        print("  ", row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
