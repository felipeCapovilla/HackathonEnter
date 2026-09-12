.PHONY: setup test api frontend build schema
setup:
	python -m pip install -e ".[dev]"
test:
	python -m pytest -q
api:
	python -m uvicorn src.interface.backend.main:app --reload --port 8000
frontend:
	npm --prefix src/interface/frontend run dev
build:
	npm --prefix src/interface/frontend run build
schema:
	python -m scripts.export_policy_schema
