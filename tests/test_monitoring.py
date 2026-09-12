"""Tests for SQLite monitoring aggregates."""

from __future__ import annotations

import sqlite3

from backend.app.monitoring import build_monitoring_summary


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE analyses (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            recommendation TEXT,
            documentary_status TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE lawyer_decisions (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            analysis_id TEXT,
            action TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    return connection


def test_summary_aggregates_decisions_recommendations_and_documentary_statuses() -> None:
    connection = _connection()
    connection.executemany(
        "INSERT INTO analyses VALUES (?, ?, ?, ?, ?)",
        [
            ("analysis-1", "case-1", "ACORDO", "SUSTENTADA_DOCUMENTALMENTE", "2026-09-12"),
            ("analysis-2", "case-2", "DEFESA", "INFORMACAO_INSUFICIENTE", "2026-09-12"),
            ("analysis-3", "case-3", "ACORDO", "INFORMACAO_INSUFICIENTE", "2026-09-12"),
        ],
    )
    connection.executemany(
        "INSERT INTO lawyer_decisions VALUES (?, ?, ?, ?, ?)",
        [
            ("decision-1", "case-1", "analysis-1", "acordo", "2026-09-12"),
            ("decision-2", "case-2", "analysis-2", "ACORDO", "2026-09-12"),
            ("decision-3", "case-3", "analysis-3", "DEFESA", "2026-09-12"),
        ],
    )

    summary = build_monitoring_summary(connection)

    assert summary == {
        "total_analyses": 3,
        "total_lawyer_decisions": 3,
        "adherence_rate": 0.3333,
        "recommendations": {"ACORDO": 2, "DEFESA": 1},
        "documentary_statuses": {
            "INFORMACAO_INSUFICIENTE": 2,
            "SUSTENTADA_DOCUMENTALMENTE": 1,
        },
    }


def test_summary_returns_none_adherence_without_comparable_decisions() -> None:
    connection = _connection()
    connection.execute(
        "INSERT INTO analyses VALUES (?, ?, ?, ?, ?)",
        ("analysis-1", "case-1", "ACORDO", None, "2026-09-12"),
    )
    connection.execute(
        "INSERT INTO lawyer_decisions VALUES (?, ?, ?, ?, ?)",
        ("decision-1", "case-2", "missing-analysis", "DEFESA", "2026-09-12"),
    )

    summary = build_monitoring_summary(connection)

    assert summary["total_analyses"] == 1
    assert summary["total_lawyer_decisions"] == 1
    assert summary["adherence_rate"] is None
    assert summary["recommendations"] == {"ACORDO": 1}
    assert summary["documentary_statuses"] == {"DESCONHECIDO": 1}
