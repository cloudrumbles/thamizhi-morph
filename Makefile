.PHONY: install test lint check build serve

install:
	python -m pip install -e '.[dev,api]'

test:
	pytest

lint:
	ruff check .

check: lint test build

build:
	python -m build

serve:
	thamizhimorph serve --host 0.0.0.0 --port 8000
