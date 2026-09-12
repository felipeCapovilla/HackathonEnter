"""SQLite-backed API aggregates for policy adherence and documentary coverage."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any


def _grouped_counts(connection: sqlite3.Connection, column: str, bank_id: str | None = None) -> dict[str, int]:
    """Return stable counts for a known ``analyses`` text column."""
    joins = " JOIN cases ON cases.id = analyses.case_id" if bank_id is not None else ""
    where = " WHERE cases.bank_id = ?" if bank_id is not None else ""
    rows = connection.execute(
        f"""
        SELECT
            COALESCE(NULLIF(TRIM({column}), ''), 'DESCONHECIDO') AS value,
            COUNT(*) AS count
        FROM analyses{joins}{where}
        GROUP BY COALESCE(NULLIF(TRIM({column}), ''), 'DESCONHECIDO')
        ORDER BY value
        """, (bank_id,) if bank_id is not None else ()
    ).fetchall()
    return {str(value): int(count) for value, count in rows}


def build_monitoring_summary(connection: sqlite3.Connection, bank_id: str | None = None) -> Mapping[str, Any]:
    """Build the monitoring payload consumed by the bank dashboard.

    Adherence is measured only for decisions that reference an analysis whose
    recommendation is ``ACORDO``, ``DEFESA`` or ``RECUPERAR``. Orphan decisions and analyses
    without a decision remain visible in their respective totals, but cannot
    be interpreted as either adherent or non-adherent.
    """
    if bank_id is None:
        total_analyses = int(connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0])
        total_lawyer_decisions = int(connection.execute("SELECT COUNT(*) FROM lawyer_decisions").fetchone()[0])
        scoped_where, scoped_args = "WHERE", ()
    else:
        total_analyses = int(connection.execute("SELECT COUNT(*) FROM analyses JOIN cases ON cases.id = analyses.case_id WHERE cases.bank_id = ?", (bank_id,)).fetchone()[0])
        total_lawyer_decisions = int(connection.execute("SELECT COUNT(*) FROM lawyer_decisions JOIN cases ON cases.id = lawyer_decisions.case_id WHERE cases.bank_id = ?", (bank_id,)).fetchone()[0])
        scoped_where, scoped_args = "INNER JOIN cases ON cases.id = analysis.case_id WHERE cases.bank_id = ? AND", (bank_id,)

    comparable_decisions, adherent_decisions = connection.execute(
        f"""
        SELECT
            COUNT(*) AS comparable_decisions,
            COALESCE(
                SUM(
                    CASE
                        WHEN UPPER(TRIM(decision.action)) = UPPER(TRIM(analysis.recommendation))
                        THEN 1
                        ELSE 0
                    END
                ),
                0
            ) AS adherent_decisions
        FROM lawyer_decisions AS decision
        INNER JOIN analyses AS analysis ON analysis.id = decision.analysis_id
            {scoped_where} UPPER(TRIM(decision.action)) IN ('ACORDO', 'DEFESA', 'RECUPERAR')
          AND UPPER(TRIM(analysis.recommendation)) IN ('ACORDO', 'DEFESA', 'RECUPERAR')
        """, scoped_args
    ).fetchone()

    comparable = int(comparable_decisions)
    adherence_rate = round(int(adherent_decisions) / comparable, 4) if comparable else None

    return {
        "total_analyses": total_analyses,
        "total_lawyer_decisions": total_lawyer_decisions,
        "adherence_rate": adherence_rate,
        "recommendations": _grouped_counts(connection, "recommendation", bank_id),
        "documentary_statuses": _grouped_counts(connection, "documentary_status", bank_id),
    }
