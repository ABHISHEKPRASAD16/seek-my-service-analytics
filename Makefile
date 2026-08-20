# ============================================================================
# Seek My Service - GNU make targets
#
# The project is built and demoed on Windows, where make.bat is the script that
# actually gets used. This Makefile is the POSIX equivalent, for CI runners and
# for anyone on macOS or Linux.
#
# Both files expose the same six targets, so instructions in the README work
# either way.
# ============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Windows puts the interpreter in Scripts/, everyone else in bin/.
ifeq ($(OS),Windows_NT)
    VENV_BIN := .venv/Scripts
    PY_BOOT  := py -3.12
else
    VENV_BIN := .venv/bin
    PY_BOOT  := python3.12
endif

VPY := $(VENV_BIN)/python

.PHONY: help setup generate validate train serve dashboard test measures all clean

help: ## Show this help
	@echo ""
	@echo "Seek My Service - build targets"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Typical first run:  make all"
	@echo ""

setup: ## Create .venv on Python 3.12 and install pinned dependencies
	@command -v $(firstword $(PY_BOOT)) >/dev/null 2>&1 || \
		{ echo "ERROR: Python 3.12 not found. LightGBM wheels still lag on 3.13+."; exit 1; }
	@test -d .venv || $(PY_BOOT) -m venv .venv
	@$(VPY) -m pip install --upgrade pip --quiet
	@$(VPY) -m pip install -r requirements.txt --quiet
	@echo "[setup] done: $$($(VPY) --version)"

generate: check-venv ## Build the CSVs in data/
	@$(VPY) generator/generate.py

validate: check-venv ## Run the 16 data integrity checks
	@$(VPY) validate.py

train: check-venv ## Train and persist all three models
	@$(VPY) ml/train_all.py

test: check-venv ## Run the pytest suite
	@$(VPY) -m pytest tests -q

measures: check-venv ## Regenerate measures.dax and the Tabular Editor script
	@$(VPY) powerbi/build_measures.py

dashboard: check-venv ## Open the Streamlit dashboard in your browser
	@$(VPY) -m streamlit run streamlit_app.py --server.port 8501

serve: check-venv ## Start the three FastAPI services (Ctrl+C stops all three)
	@echo "forecast  http://127.0.0.1:8001/docs"
	@echo "match     http://127.0.0.1:8002/docs"
	@echo "pricing   http://127.0.0.1:8003/docs"
	@trap 'kill 0' EXIT INT TERM; \
	$(VPY) -m uvicorn ml.forecast_service:app --port 8001 & \
	$(VPY) -m uvicorn ml.match_service:app    --port 8002 & \
	$(VPY) -m uvicorn ml.pricing_service:app  --port 8003 & \
	wait

all: setup generate validate train test ## Everything, in order
	@echo ""
	@echo "[all] complete. Next: open Power BI Desktop and follow powerbi/BUILD_GUIDE.md"

clean: ## Delete generated data and model artefacts (keeps .venv)
	@rm -f data/*.csv
	@rm -f ml/models/*.joblib ml/models/*.json
	@find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .pytest_cache
	@echo "[clean] done. Run 'make setup' if you also removed .venv."

check-venv:
	@test -x $(VPY) || { echo "ERROR: no virtualenv. Run: make setup"; exit 1; }
