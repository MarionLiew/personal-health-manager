.PHONY: install init test lint doctor clean

install:
	uv sync --extra test --extra backup

init:
	uv run health init --json

test:
	uv run pytest

lint:
	uv run ruff check .

doctor:
	uv run health doctor --json

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov coverage.xml

