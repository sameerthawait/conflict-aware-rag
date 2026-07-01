.PHONY: install ingest serve eval generate-dataset test lint

# Pinned Python requirements setup
install:
	pip install -r requirements.txt

# Seed vector store with documents from a specified path
path ?= ./data/raw
ingest:
	python scripts/ingest.py --path $(path) --recursive

# Run local FastAPI server with reload
serve:
	uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000

# Execute evaluation pipeline against golden verified pairs
eval:
	python scripts/run_evaluation.py --dataset ./data/golden_dataset/qa_pairs.json

# Build synthetic evaluation Q&A pairs from Chroma indexed data
max-chunks ?= 100
generate-dataset:
	python scripts/generate_golden_dataset.py --max-chunks $(max-chunks)

# Run full project pytest suites (excluding evaluation run itself)
test:
	pytest tests/unit/ tests/integration/ tests/eval/

# Format / Lint validation checks
lint:
	ruff check src/
	mypy src/ --ignore-missing-imports

# Local dependency vulnerability check
security-check:
	python scripts/security/audit_deps.py
