"""One full pipeline run: extract -> silver -> quality gate -> load, recorded in pipeline_runs.

Run with:  python -m pipeline.run        (needs DATABASE_URL)
Exit codes: 0 success, 1 pipeline failure, 2 cannot reach the database.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import psycopg

from pipeline import extract, load, quality_checks, validate

if TYPE_CHECKING:
    from psycopg import Connection

log = logging.getLogger(__name__)

MAX_ERROR_CHARS = 1000


def execute(conn: "Connection") -> int:
    """Run the pipeline on an open connection and record the outcome. Returns an exit code."""
    run_id = load.start_run(conn)
    rejected = 0
    try:
        extracts = extract.run_extraction()
        batch = validate.build_silver(extracts)
        rejected = batch.rows_rejected
        if batch.rows_ingested == 0:
            raise RuntimeError("no valid rows to load (every source failed or every row was rejected)")
        quality_checks.enforce(batch)  # raises QualityCheckError: a bad batch is never loaded
        load.load_batch(conn, batch)
    except Exception as exc:  # every failure must be recorded, whatever its type
        conn.rollback()
        log.exception("Pipeline run %d failed", run_id)
        message = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]
        load.finish_run(conn, run_id, "failed", 0, rejected, message)
        return 1

    load.finish_run(conn, run_id, "success", batch.rows_ingested, rejected)
    log.info(
        "Run %d succeeded: %d rows ingested, %d rejected",
        run_id, batch.rows_ingested, rejected,
    )
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        conn = load.connect()
    except (RuntimeError, psycopg.Error) as exc:
        log.error("Cannot connect to the database: %s", exc)
        return 2
    with conn:
        return execute(conn)


if __name__ == "__main__":
    raise SystemExit(main())
