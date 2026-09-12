from __future__ import annotations

from pathlib import Path

import pytest

from src.interface.backend.database import connection_for, initialize_database


def test_connection_rolls_back_when_an_operation_fails(tmp_path: Path) -> None:
    database_path = tmp_path / "enteragree.db"
    initialize_database(database_path)

    with pytest.raises(RuntimeError, match="abort"):
        with connection_for(database_path) as connection:
            connection.execute(
                """INSERT INTO cases (
                    id, case_number, uf, value_of_claim, sub_subject, dossie_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("case-1", "0000001-00.2026.8.26.0001", "SP", 1000, None, "AUSENTE", "2026-09-12"),
            )
            raise RuntimeError("abort")

    with connection_for(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    assert count == 0
