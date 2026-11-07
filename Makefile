.PHONY: install lint wire wire-check format test dead check run e2e frontend frontend-check

install:
	uv sync --all-extras

lint:
	uv run ruff check .
	uv run ruff format --check src tests scripts
	uv run pyright
	uv run lint-imports
	$(MAKE) wire-check

wire:
	uv run python scripts/generate_wire.py

wire-check:
	uv run python scripts/generate_wire.py --check

format:
	uv run ruff check --fix .
	uv run ruff format src tests scripts

test:
	uv run pytest -m "not e2e"

e2e: frontend
	uv run pytest -m e2e --no-cov --output test-results

dead:
	uv run vulture src/skat

frontend:
	cd frontend && pnpm install --frozen-lockfile && pnpm build

frontend-check:
	cd frontend && pnpm check && pnpm lint && pnpm test

check: lint test dead frontend-check

run: frontend
	uv run skat serve
