"""SQLite-backed API aggregates for policy adherence and documentary coverage."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any


def _grouped_counts(connection: sqlite3.Connection, column: str) -> dict[str, int]:
    """Return stable counts for a known ``analyses`` text column."""
    rows = connection.execute(
        f"""
        SELECT
            COALESCE(NULLIF(TRIM({column}), ''), 'DESCONHECIDO') AS value,
            COUNT(*) AS count
        FROM analyses
        GROUP BY COALESCE(NULLIF(TRIM({column}), ''), 'DESCONHECIDO')
        ORDER BY value
        """
    ).fetchall()
    return {str(value): int(count) for value, count in rows}


def build_monitoring_summary(connection: sqlite3.Connection) -> Mapping[str, Any]:
    """Build the monitoring payload consumed by the bank dashboard.

    Adherence is measured only for decisions that reference an analysis whose
    recommendation is ``ACORDO`` or ``DEFESA``. Orphan decisions and analyses
    without a decision remain visible in their respective totals, but cannot
    be interpreted as either adherent or non-adherent.
    """
    total_analyses = int(connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0])
    total_lawyer_decisions = int(
        connection.execute("SELECT COUNT(*) FROM lawyer_decisions").fetchone()[0]
    )

    comparable_decisions, adherent_decisions = connection.execute(
        """
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
        WHERE UPPER(TRIM(decision.action)) IN ('ACORDO', 'DEFESA')
          AND UPPER(TRIM(analysis.recommendation)) IN ('ACORDO', 'DEFESA')
        """
    ).fetchone()

    comparable = int(comparable_decisions)
    adherence_rate = round(int(adherent_decisions) / comparable, 4) if comparable else None

    return {
        "total_analyses": total_analyses,
        "total_lawyer_decisions": total_lawyer_decisions,
        "adherence_rate": adherence_rate,
        "recommendations": _grouped_counts(connection, "recommendation"),
        "documentary_statuses": _grouped_counts(connection, "documentary_status"),
    }
