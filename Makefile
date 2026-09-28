.PHONY: setup dev test demo backend frontend

PY := .venv/bin/python

setup:
	python -m venv .venv || uv venv .venv
	$(PY) -m pip install -r backend/requirements.txt
	cd frontend && npm install

backend:
	$(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend

frontend:
	cd frontend && npm run dev

dev:
	$(MAKE) backend & $(MAKE) frontend

test:
	$(PY) -m pytest backend/tests -q --ignore=backend/tests/e2e_smoke.py --ignore=backend/tests/e2e_approval.py

demo:
	$(PY) backend/tests/e2e_smoke.py
