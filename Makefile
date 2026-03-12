PYTHON ?= python
FRONTEND_DIR ?= frontend

.PHONY: dev starter api backend-test typecheck frontend-install frontend-typecheck frontend-test frontend-build test demo-data trace-demo functional-test load-baseline observability-up observability-down distributed-up

dev: starter

starter:
	$(PYTHON) onTroFinanceStarter.py

api:
	$(PYTHON) main.py

backend-test:
	$(PYTHON) -m pytest tests -q

typecheck:
	$(PYTHON) -m basedpyright main.py src tests

frontend-install:
	npm --prefix $(FRONTEND_DIR) ci

frontend-typecheck:
	npm --prefix $(FRONTEND_DIR) run typecheck

frontend-test:
	npm --prefix $(FRONTEND_DIR) test

frontend-build:
	npm --prefix $(FRONTEND_DIR) run build

test: backend-test typecheck frontend-typecheck frontend-test

demo-data:
	$(PYTHON) scripts/demo_scenario.py --sample-limit 4

trace-demo:
	$(PYTHON) local_trace_demo.py --limit 4

functional-test:
	$(PYTHON) functional_test_runner.py

load-baseline:
	$(PYTHON) scripts/load_baseline.py --base-url http://127.0.0.1:8000

observability-up:
	docker compose --profile observability up -d

observability-down:
	docker compose --profile observability down

distributed-up:
	docker compose --profile distributed up -d
