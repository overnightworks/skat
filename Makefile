.PHONY: install lint wire wire-check words words-sync words-check voice format test dead check run e2e frontend frontend-check

install:
	uv sync --all-extras

lint:
	uv run ruff check .
	uv run ruff format --check src tests scripts
	uv run pyright
	PYTHONPATH=src uv run lint-imports
	$(MAKE) wire-check
	$(MAKE) words-check

wire:
	uv run python scripts/generate_wire.py

wire-check:
	uv run python scripts/generate_wire.py --check

words:
	uv run design-catalogs

words-sync:
	uv run design-catalogs --sync

words-check:
	uv run design-catalogs --check

voice:
	uv run python scripts/record_voice.py

format:
	uv run ruff check --fix .
	uv run ruff format src tests scripts

test:
	scripts/test_postgres.sh uv run pytest -m "not e2e"

e2e: frontend
	scripts/test_postgres.sh probe-run uv run pytest -m e2e --no-cov --output test-results

dead:
	uv run vulture src/skat

frontend:
	cd frontend && pnpm install --frozen-lockfile && pnpm build

frontend-check:
	cd frontend && pnpm check && pnpm lint && pnpm test

check: lint test dead frontend-check

run: frontend
	uv run skat serve
