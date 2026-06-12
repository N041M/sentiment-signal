.PHONY: help lint fix format test check

help:
	@echo "make lint    - ruff lint (no changes)"
	@echo "make fix     - ruff auto-fix lint issues"
	@echo "make format  - ruff format (code layout)"
	@echo "make test    - run the test suite (DB tests skip if Postgres is down)"
	@echo "make check   - lint + tests; run before committing"

lint:
	ruff check sentiment_signal/ scripts/ tests/

fix:
	ruff check --fix sentiment_signal/ scripts/ tests/

format:
	ruff format sentiment_signal/ scripts/ tests/

test:
	pytest -q

# Run before committing. Fast pure-function tests always run; DB-backed tests
# skip automatically if PostgreSQL is unavailable.
check: lint test
