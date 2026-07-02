# MarketMind

**AI-Powered Financial Intelligence & Quantitative Research Platform**

---

## What is MarketMind?

MarketMind is **not** a stock prediction application.
MarketMind is **not** a trading bot.
MarketMind is **not** an AI that promises to beat the market.

MarketMind is a **quantitative research platform** whose purpose is to:

- Discover hypotheses about financial market signals
- Validate them rigorously against historical data
- **Reject weak hypotheses** — this is considered a successful outcome
- Quantify uncertainty and estimate risk honestly
- Explain model behaviour with appropriate explainability tools
- Monitor whether an observed edge survives over time

> **Finding no statistically meaningful edge is considered a successful research outcome.**
> The platform is optimised for discovering truth, not confirming assumptions.

---

## Architecture Overview

MarketMind follows a **hexagonal (ports & adapters) architecture** organised into five layers:

```
Presentation   →  Streamlit dashboard + CLI
Application    →  Research orchestration, pipeline coordination
Domain         →  Core business rules, value objects, protocols
Infrastructure →  Data providers, database, experiment tracking
```

Module dependency rules are machine-enforced in CI — no module may import across architectural boundaries.

---

## Project Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project Foundation | ✅ Complete |
| 2 | Data Layer (ingestion, validation, storage) | 🔜 Next |
| 3 | Feature Engineering Pipeline | 📋 Planned |
| 4 | ML Pipeline (training, calibration) | 📋 Planned |
| 5 | Evaluation & Backtesting Framework | 📋 Planned |
| 6 | Dashboard | 📋 Planned |

---

## Quick Start

### Prerequisites

- Python 3.11 or 3.12
- `pip` (or `uv` — recommended for speed)
- `git`

### Setup

```bash
# Clone the repository
git clone https://github.com/your-username/marketmind.git
cd marketmind

# Install with development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks (runs lint/format/typecheck before each commit)
pre-commit install

# Verify the installation
make info
```

### Run Tests

```bash
# Unit tests (fast, no network)
make test-unit

# All tests
make test

# With coverage report
make coverage
```

### Docker

```bash
# Build
make docker-build

# Interactive shell
make docker-run

# Tests in container
make docker-test
```

---

## Development Commands

```bash
make help          # Show all available commands
make lint          # Run Ruff linter
make format        # Format code
make typecheck     # Run MyPy
make test          # Run tests
make coverage      # Run tests with coverage
make clean         # Remove caches and artifacts
```

---

## Configuration

Configuration is layered (later overrides earlier):

1. Built-in defaults
2. `marketmind/config/environments/{MM_ENVIRONMENT}.yaml`
3. Environment variables (`MM_` prefix)

Set `MM_ENVIRONMENT` to `local`, `research`, or `test`.

```bash
# Show active configuration
make config-show

# Validate configuration
make config-validate
```

Copy `.env.example` to `.env` for local development:

```bash
cp .env.example .env
```

---

## Research Methodology

Every model, feature, and strategy is treated as a **hypothesis that must earn its place** through rigorous testing. Before any experiment begins, a **pre-registration document** is committed to version control, specifying:

- The research question
- The hypothesis and null hypothesis
- Exact features and model parameters
- Acceptance and kill criteria
- The sealed final validation dataset

Experiments are tracked in the **Research Log** (`docs/research/research-log/`).

A running **False Discovery Rate tracker** monitors the hypothesis acceptance rate. If the acceptance rate exceeds 20%, a mandatory methodology review is triggered.

See `docs/research/RESEARCH_PROTOCOL.md` for the full methodology.

---

## Project Philosophy

1. No data leakage
2. No look-ahead bias
3. Minimise survivorship bias
4. Every experiment is reproducible
5. Every experiment is documented
6. Every prediction is explainable
7. Trust is more important than accuracy
8. Simplicity is preferred over unnecessary complexity
9. Models that do not beat baselines are rejected
10. Every conclusion is statistically defensible
11. **Most hypotheses are expected to fail. Rejecting them is success.**

---

## Known Limitations

These are documented limitations, not apologies:

- **Point-in-time correctness:** Historical data may reflect post-publication revisions unless using the snapshot provider. Documented in every model card.
- **Survivorship bias:** The research universe is selected from currently-listed securities. Companies that delisted during the study period are underrepresented.
- **Signal density:** Daily-bar technical signals represent the most heavily arbitraged information set in equity markets. The prior probability of finding exploitable edge is low. This is a feature, not a bug — it is the platform's job to measure that honestly.
- **Solo researcher bias:** Even with pre-registration, a single researcher designing and evaluating experiments has implicit knowledge that creates subtle conditioning. This is acknowledged and partially mitigated by the adversarial review step in the research log.

---

## Repository Structure

```
marketmind/
├── docs/                   # Architecture, ADRs, research log, pre-registrations
├── marketmind/             # Main Python package
│   ├── core/               # Domain layer (no infrastructure imports)
│   ├── config/             # Configuration management
│   ├── data/               # Data ingestion and validation (Phase 2)
│   ├── features/           # Feature engineering (Phase 3)
│   ├── models/             # ML models (Phase 4)
│   ├── evaluation/         # Backtesting and validation (Phase 5)
│   ├── research/           # Research framework
│   ├── recommendation/     # Rule-based recommendation engine
│   ├── explainability/     # SHAP and feature importance
│   ├── monitoring/         # Model governance and drift detection
│   ├── api/                # REST API
│   └── dashboard/          # Streamlit dashboard
├── tests/                  # Unit, integration, property, regression tests
├── scripts/                # Operational scripts
└── notebooks/              # Research notebooks (outputs stripped on commit)
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

---

## License

MIT License — see [LICENSE](LICENSE).

---

## Disclaimer

MarketMind is a research platform. Nothing produced by this platform constitutes investment advice. All research conclusions are experimental and may be wrong. Past research findings do not guarantee future results. Trade at your own risk.
