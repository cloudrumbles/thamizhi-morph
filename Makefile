.PHONY: test lint format typecheck check

test:
	pytest --cov=thamizhi_morph --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy

check: lint typecheck test
