from pathlib import Path

from src.policy.engine import PolicyEngine


def test_trained_artifact_serves_the_intermediate_zone() -> None:
    engine = PolicyEngine(model_path=Path(__file__).parents[1] / "artefatos" / "modelo_xgboost.pkl")
    decision = engine.evaluate(
        {
            "case_id": "teste-modelo",
            "uf": "SP",
            "value_of_claim": 1000,
            "contrato": True,
            "extrato": True,
            "comprovante_credito": False,
        }
    )

    assert decision.source == "MODEL"
    assert decision.decision_code == "MODELO_CALIBRADO"
    assert decision.agreement_probability is not None
