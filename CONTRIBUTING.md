# Contributing to rtfs

## Environment Setup

1. Clone the repository and create a Python 3.11+ virtual environment:

```bash
git clone https://github.com/AtaCanYmc/rtfs.git
cd rtfs
uv venv --python 3.11
uv pip install -e ".[dev]" --python .venv/bin/python
```

2. Run the verification suite before making changes:

```bash
.venv/bin/ruff check .
.venv/bin/pytest -v
```

## Branch Naming & Commit Messages

Use descriptive branch names prefixed by change category:

- `feat/<scope>` for new providers, parsers, or CLI flags
- `fix/<scope>` for bug fixes in parsing or scraping
- `test/<scope>` for test fixtures and coverage additions
- `docs/<scope>` for documentation updates

Follow the Conventional Commits specification for all commit messages:

```text
<type>(<scope>): <concise summary in imperative mood>
```

Allowed types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `chore`.

## Adding a Provider

1. Subclass `BaseProvider` in `src/rtfs/providers/`.
2. Implement `async def search(self, query: str) -> list[SearchResult]` and `async def fetch_raw(self, result: SearchResult) -> RawScript`.
3. Route all network calls through `self.http` (`HttpClient`) so per-host rate limiting and exponential backoff apply.
4. Register the provider in `ScriptAggregator` and add priority weighting in `SOURCE_PRIORITY_BONUS`.
5. Add offline unit tests in `tests/test_aggregator.py`.

## Pull Request Checklist

- [ ] `.venv/bin/ruff check .` exits with code 0.
- [ ] `.venv/bin/pytest -v` passes all unit tests.
- [ ] No live network calls occur during unit test execution.
- [ ] Public models in `src/rtfs/core/models.py` retain `ConfigDict(strict=True)`.
