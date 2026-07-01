DIR ?= .
RUN := uv run material-agent
WORK_DIR := $(DIR)/.material-agent
RUNTIME_DB := $(WORK_DIR)/state.db
RUNTIME_LOG := $(WORK_DIR)/run.log

install:
	uv sync --all-groups
	@command -v exiftool >/dev/null 2>&1 || echo "WARNING: exiftool not found, run: brew install exiftool"
	@echo "Default local backend does not require Ollama or OMLX."

deps-refresh:
	uv lock --upgrade
	uv sync --all-groups --reinstall
	$(MAKE) test

deps-refresh-commit:
	$(MAKE) deps-refresh
	@if git diff --quiet -- uv.lock; then \
		echo "uv.lock unchanged; nothing to commit."; \
	else \
		git add uv.lock; \
		git commit -m "chore(deps): refresh uv lock"; \
	fi

launcher:
	uv run python scripts/write_macos_launcher.py

run:
	$(RUN) run $(DIR)

dry-run:
	$(RUN) run $(DIR) --dry-run

rerun:
	rm -f $(RUNTIME_DB) $(RUNTIME_DB)-wal $(RUNTIME_DB)-shm $(RUNTIME_DB)-journal $(RUNTIME_LOG)
	rm -f $(DIR)/material-agent.db $(DIR)/material-agent.db-wal $(DIR)/material-agent.db-shm $(DIR)/material-agent.db-journal $(DIR)/material-agent.log
	$(RUN) run $(DIR) --reprocess

persist:
	until $(RUN) run $(DIR); do echo "crashed, restarting..."; done

scan-scenes:
	$(RUN) scan-scenes --dir $(DIR)

suggest-scenes:
	$(RUN) suggest-scenes --dir $(DIR)

remap-scenes:
	$(RUN) remap-scenes --dir $(DIR) --from "$(FROM)" --to $(TO)

rescore:
	$(RUN) rescore --dir $(DIR) $(if $(SCENE),--scene $(SCENE),)

reset-ai:
	$(RUN) reset-ai --dir $(DIR) $(if $(KEEP_XMP),--keep-xmp,)

reset-ai-dry-run:
	$(RUN) reset-ai --dir $(DIR) --dry-run $(if $(KEEP_XMP),--keep-xmp,)

fix-db:
	$(RUN) fix-db --dir $(DIR)

rewrite-xmp:
	$(RUN) rewrite-xmp --dir $(DIR)

format:
	uv run ruff format .

check:
	uv run ruff check .

fix:
	uv run ruff check --fix .

test:
	uv run python -m pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete 2>/dev/null; \
	rm -rf .material-agent; \
	rm -f material-agent.db; \
	rm -rf dist/ *.egg-info/

.PHONY: install deps-refresh deps-refresh-commit launcher run dry-run rerun persist scan-scenes suggest-scenes remap-scenes rescore reset-ai reset-ai-dry-run fix-db rewrite-xmp format check fix test clean
