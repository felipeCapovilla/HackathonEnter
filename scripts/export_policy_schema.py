"""Export the segment policy contracts used by the preserved visual prototype."""

import json
from pathlib import Path

from contracts.schema import CaseFeatures, Recomendacao


def export_schema() -> Path:
    destination = Path(__file__).resolve().parents[1] / "src/interface/prototype/schema.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "CaseFeatures": CaseFeatures.model_json_schema(),
                "Recomendacao": Recomendacao.model_json_schema(),
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )
    return destination


if __name__ == "__main__":
    print(export_schema())
