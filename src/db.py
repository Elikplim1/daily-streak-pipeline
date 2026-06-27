"""Supabase connection management via psycopg2.

Uses the session pooler URL from DATABASE_URL (pooler.supabase.com:5432).
Do NOT use the direct db.*.supabase.co format — it requires IPv6 and fails
on most networks.

Usage:
    from src.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM fixtures")
            print(cur.fetchone())
"""
import urllib.parse
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extensions

from src.config import DATABASE_URL


def _parse_url(url: str) -> dict:
    """Parse a postgresql:// URI into psycopg2 keyword arguments."""
    parsed = urllib.parse.urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password,
        "sslmode": "require",
        "connect_timeout": 30,
    }


@contextmanager
def get_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Context manager that yields an open psycopg2 connection.

    Commits on clean exit, rolls back on exception, always closes.
    """
    conn = psycopg2.connect(**_parse_url(DATABASE_URL))
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor() -> Generator[psycopg2.extensions.cursor, None, None]:
    """Context manager that yields a psycopg2 cursor.

    Opens a connection, yields a cursor, commits on clean exit,
    rolls back on exception, always closes both.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()


def test_connection() -> None:
    """Verify the Supabase connection and print a summary row count.

    Run with: python -c "from src.db import test_connection; test_connection()"
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM fixtures;")
        fixture_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM flagged_opportunities;")
        opp_count = cur.fetchone()[0]

        print("Supabase connection: OK")
        print(f"PostgreSQL: {version[:60]}")
        print(f"Fixtures:   {fixture_count:,}")
        print(f"Flagged:    {opp_count:,}")
