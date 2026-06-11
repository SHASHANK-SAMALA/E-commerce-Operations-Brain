"""Drop and recreate mem0 pgvector tables with correct dimensions."""
from ecommerce_brain.db.engine import get_session
from sqlalchemy import text

with get_session() as s:
    tables = s.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'mem0%'")
    ).fetchall()
    print("mem0 tables found:", [t[0] for t in tables])
    for (t,) in tables:
        s.execute(text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))
        print(f"Dropped {t}")
    print("Done — mem0 will recreate tables on next init with correct dims.")
