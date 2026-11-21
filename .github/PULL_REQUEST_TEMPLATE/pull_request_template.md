## Summary

State the purpose of this change in one or two declarative sentences.

## Changes

- `src/rtfs/...`: Describe the modification.

## Verification

```bash
.venv/bin/ruff check .
.venv/bin/pytest -v
```

## Checklist

- [ ] Commit messages follow Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
- [ ] All unit tests pass offline without live network requests.
- [ ] `ruff check .` reports zero errors.
