# Contributing to MarketMind

## Development Philosophy

Before contributing, read and internalise the **Project Charter** (`docs/research/RESEARCH_PROTOCOL.md`).

The single most important rule:

> **Scientific integrity takes priority over all other concerns.**
> Code quality, performance, and convenience are secondary to correctness and reproducibility.

---

## Getting Started

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify everything works
make test
make quality
```

---

## Branching Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-stable. Protected. Requires review + all CI green. |
| `develop` | Integration branch. All feature work targets here. |
| `feature/{name}` | Implementation work. |
| `research/EXP-{NNN}` | Experiment branches. Must reference a pre-registration. |
| `fix/{name}` | Bug fixes. |

---

## Before Opening a Pull Request

**For feature branches:**
- [ ] All existing tests pass (`make test`)
- [ ] New code has tests (`make coverage` shows ≥ 80%)
- [ ] No type errors (`make typecheck`)
- [ ] No lint errors (`make lint`)
- [ ] Import boundaries respected (`make import-check`)
- [ ] Docstrings on all public functions and classes

**For research branches (`research/EXP-NNN`):**
- [ ] Pre-registration YAML committed **before** any modeling code
- [ ] Pre-registration committed on a separate commit with message `"pre-reg: EXP-NNN"`
- [ ] PR description includes the experiment ID and pre-registration commit hash
- [ ] No modifications to pre-registration after modeling began

---

## Module Dependency Rules

These rules are **machine-enforced** by `import-linter` in CI. A PR violating them fails CI.

```
core         → nothing outside core
data         → core only
features     → core, data
research     → core only
models       → core, features
evaluation   → core, models, features
regime       → core, data
explainability → core, models, features
recommendation → core, evaluation, models
monitoring   → core, models, evaluation
api          → all application modules
dashboard    → api (via HTTP client), or direct module imports
```

If you believe a dependency rule should change, open an ADR first (`docs/adr/`).

---

## Writing Tests

**Test location:**

| Test type | Location | Runs in CI |
|-----------|----------|------------|
| Unit | `tests/unit/` | Always |
| Integration | `tests/integration/` | Always |
| Property-based | `tests/property/` | Always |
| Regression | `tests/regression/` | On research merges |

**Unit test rules:**
- Zero I/O. No files, no network, no database.
- Test one behaviour per test function.
- Name tests as `test_{what}_{condition}_{expected}`.

**Property test rules:**
- Use the `hypothesis` library.
- Test invariants, not specific values.
- Set `@settings(max_examples=200)` for important invariants.

**Leakage tests (critical):**
- Any transformer or splitter that touches time-series data must have a test that verifies it does not use future information.
- This is the highest-priority test category.

---

## Adding a New Module

1. Create the directory under `marketmind/`.
2. Add `__init__.py` with a docstring explaining what the module does and which Phase implements it.
3. Add the module to the import-linter contract in `pyproject.toml`.
4. Write unit tests before implementation.
5. Open an ADR if the module introduces a new architectural pattern.

---

## Code Style

- **Python 3.11+** features are permitted.
- **Type annotations required** on all public functions and class attributes.
- **Docstrings required** on all public modules, classes, and functions.
- **Immutable value objects** — domain objects use `@dataclass(frozen=True)`.
- **No bare `except:`** — always catch specific exception types.
- **No `print()`** in library code — use `get_logger(__name__)`.

Formatting is enforced by `ruff format`. Linting by `ruff check`. Both run on pre-commit.

---

## Commit Messages

Follow Conventional Commits:

```
<type>(<scope>): <description>

Types: feat, fix, refactor, test, docs, chore, research
Scope: core, data, features, models, evaluation, dashboard, config, ci

Examples:
  feat(data): add YahooFinance provider implementation
  test(core): add property tests for OHLCVBar price invariants
  research(EXP-007): pre-registration for RSI direction experiment
  docs(adr): ADR-003 walk-forward validation parameters
```

---

## Architecture Decision Records

Any significant structural decision requires an ADR in `docs/adr/`.

Use the template at `docs/adr/ADR-NNN-template.md`.

ADRs are **permanent records**. Do not delete them. If a decision is reversed, mark it `SUPERSEDED by ADR-NNN` and create a new ADR explaining the reversal.

---

## Research Workflow

See `docs/research/RESEARCH_PROTOCOL.md` for the complete research workflow.

Summary:
1. Write pre-registration YAML → commit → open branch
2. Implement features and model
3. Run experiment via pipeline (never manually edit result files)
4. Write adversarial review honestly
5. Record in research log
6. FDR tracker updates automatically
7. If acceptance rate > 20% → stop, mandatory review

---

## Questions

Open an issue or start a discussion. Research methodology questions are welcome — good science requires peer review.
