"""Private, local-only consumer state for public listing bundles."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import ListingError, identity_key


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LocalConsumer:
    """Import listings without storing resumes, rankings, or applications."""

    def __init__(self, database):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    identity TEXT PRIMARY KEY,
                    record TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    human_decision TEXT
                )
                """
            )

    def _connect(self):
        return sqlite3.connect(self.database)

    def import_bundle(self, bundle):
        if not isinstance(bundle, dict) or not isinstance(bundle.get("records"), list):
            raise ListingError("consumer requires a listing bundle")
        imported = 0
        updated = 0
        seen_at = bundle.get("manifest", {}).get("observed_at") or _now()
        with self._connect() as connection:
            for record in bundle["records"]:
                identity = identity_key(record)
                if identity is None:
                    raise ListingError("consumer requires source and job identity")
                encoded = json.dumps(record, sort_keys=True, ensure_ascii=False)
                existing = connection.execute(
                    "SELECT 1 FROM listings WHERE identity = ?", (identity,)
                ).fetchone()
                if existing:
                    connection.execute(
                        """
                        UPDATE listings
                        SET record = ?, last_seen_at = ?
                        WHERE identity = ?
                        """,
                        (encoded, seen_at, identity),
                    )
                    updated += 1
                else:
                    connection.execute(
                        """
                        INSERT INTO listings
                            (identity, record, first_seen_at, last_seen_at)
                        VALUES (?, ?, ?, ?)
                        """,
                        (identity, encoded, seen_at, seen_at),
                    )
                    imported += 1
        return {"imported": imported, "updated": updated}

    def get(self, identity):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT identity, record, first_seen_at, last_seen_at, human_decision
                FROM listings WHERE identity = ?
                """,
                (identity,),
            ).fetchone()
        if row is None:
            return None
        return {
            "identity": row[0],
            "record": json.loads(row[1]),
            "first_seen_at": row[2],
            "last_seen_at": row[3],
            "human_decision": row[4],
        }

    def set_human_decision(self, identity, decision):
        with self._connect() as connection:
            connection.execute(
                "UPDATE listings SET human_decision = ? WHERE identity = ?",
                (decision, identity),
            )
