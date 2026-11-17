import sqlite3

from app.database import Base, engine

Base.metadata.create_all(bind=engine)


def test_database_tables_are_created() -> None:
    with sqlite3.connect("censo.db") as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

    table_names = {name for (name,) in tables}

    assert {"users", "pessoas", "status_historico", "documentos", "auditoria"}.issubset(table_names)
