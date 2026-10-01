"""Minimal stand-ins for a psycopg connection so DB code can be tested offline."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def norm(sql: str) -> str:
    """Collapse whitespace so tests can match SQL by prefix."""
    return " ".join(sql.split())


class FakeCursor:
    def __init__(self, conn: "FakeConn") -> None:
        self.conn = conn
        self._rows: list[Any] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        self.conn.statements.append((norm(sql), params))
        if norm(sql).startswith("SELECT name, id FROM locations"):
            self._rows = list(self.conn.existing_locations.items())
        elif "RETURNING id" in sql:
            self._rows = [(self.conn.next_id(),)]
        else:
            self._rows = []

    def executemany(self, sql: str, params_seq: Any) -> None:
        self.conn.statements.append((norm(sql), list(params_seq)))

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)


class FakeConn:
    """Records every statement; counts commits and rollbacks."""

    def __init__(self, existing_locations: dict[str, int] | None = None) -> None:
        self.statements: list[tuple[str, Any]] = []
        self.existing_locations = dict(existing_locations or {})
        self.commits = 0
        self.rollbacks = 0
        self._id = 0

    def next_id(self) -> int:
        self._id += 1
        return self._id

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        cur = FakeCursor(self)
        cur.execute(sql, params)
        return cur

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def starting(self, prefix: str) -> list[tuple[str, Any]]:
        """Recorded statements whose SQL starts with prefix."""
        return [s for s in self.statements if s[0].startswith(prefix)]


class FakeRecord:
    """Duck-types a pydantic silver record: load.py only calls model_dump()."""

    def __init__(self, **fields: Any) -> None:
        self.fields = fields

    def model_dump(self) -> dict[str, Any]:
        return dict(self.fields)


def make_batch(obs: list[FakeRecord], marine: list[FakeRecord] | None = None, rejected: int = 0) -> SimpleNamespace:
    """A stand-in SilverBatch."""
    marine = marine or []
    return SimpleNamespace(
        observations=SimpleNamespace(records=obs),
        marine=SimpleNamespace(records=marine),
        rows_ingested=len(obs) + len(marine),
        rows_rejected=rejected,
    )
