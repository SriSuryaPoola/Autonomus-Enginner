# Contributing to AI Autonomous Engineer

Thank you for your interest in contributing! This project is an open-source multi-agent platform that writes, tests, and self-heals code using LLMs.

---

## Quick Start (Dev Setup)

```bash
git clone https://github.com/SriSuryaPoola/autonomous-engineer.git
cd autonomous-engineer

# Install all dependencies including dev tools
pip install -e ".[dev]"

# Set up pre-commit hooks
pre-commit install

# Run the test suite
pytest tests/ -v --cov=core
```

---

## Before You Contribute

1. **Search existing issues** — your bug or idea may already be tracked
2. **Open an issue first** for significant changes — discuss approach before building
3. **Fork** the repo and create a feature branch: `git checkout -b feat/my-feature`
4. Keep PRs **focused** — one logical change per PR

---

## Code Standards

All code must pass the automated checks before merging:

```bash
ruff check .          # Lint
bandit -r core/       # Security scan
mypy core/ --ignore-missing-imports  # Type check
pytest tests/ --cov  # Tests + coverage
```

The CI pipeline runs all of these automatically on every PR.

### Style Guidelines
- Python 3.10+ syntax and type hints on all public functions
- Google-style docstrings on all modules and public classes
- Max line length: 100 characters (enforced by ruff)
- No bare `except:` clauses — always catch specific exceptions

---

## Submitting a Pull Request (PR)

1. Ensure all CI checks pass
2. Add or update tests for any changed behaviour
3. Update `docs/evolution.md` if you add a significant new feature
4. Fill out the PR template completely

---

## Project Structure

| Path | Purpose |
|---|---|
| `core/` | Engine: HiClaw, Claude Flow, Sandbox, Patch Engine, Memory |
| `agents/` | Worker agents (QA Engineer, Developer, DevOps) |
| `server/` | FastAPI backend + REST API |
| `ui/` | Vanilla JS frontend dashboard |
| `config/` | Settings, LLM providers, quality thresholds |
| `scripts/` | Dispatch scripts and utilities |
| `docs/` | Architecture, usage guides, evolution history |
| `benchmarks/` | Platform performance benchmarks |
| `tests/` | Unit tests |

---

## Reporting Bugs

Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md).

Always include:
- Platform version / commit hash
- Python version
- LLM provider in use
- Minimal reproduction steps
- Full error traceback

---

## Suggesting Features

Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md).

Reference the improvement backlog items (from `AUTONOMOUS_ENGINEER_IMPROVEMENT_BACKLOG.md`) where relevant.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
