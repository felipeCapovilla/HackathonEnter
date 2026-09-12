.PHONY: setup test api schema
setup:
	uv venv --python 3.12 && uv pip install -e ".[dev]"
test:
	pytest -q
api:
	uvicorn src.api.main:app --reload --port 8000
schema:   ## gera o JSON Schema que o front consome — evita divergência de chave
	python -c "import json;from contracts.schema import Recomendacao,CaseFeatures;\
print(json.dumps({'CaseFeatures':CaseFeatures.model_json_schema(),'Recomendacao':Recomendacao.model_json_schema()},indent=2,ensure_ascii=False))" > web/schema.json
