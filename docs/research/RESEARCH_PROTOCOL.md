# MarketMind Research Protocol

**Version:** 1.0
**Status:** Active
**Effective From:** 2024-01-01

---

## Purpose

This document defines the mandatory research methodology for all experiments conducted on the MarketMind platform.

Every experiment must follow this protocol exactly. Deviations require a protocol amendment (new version) committed to version control before the experiment begins.

---

## Core Principle

> Every model is a hypothesis. Every feature is a hypothesis.
> Nothing is accepted because it looks good historically.
> Everything must survive objective validation.

---

## Research Workflow

```
Idea
  ↓
Research Question (written, clear, falsifiable)
  ↓
Hypothesis (H1 and H0 stated explicitly)
  ↓
Pre-Registration (committed to git before any code)
  ↓
Experiment Design (features, model, validation scheme, thresholds — all specified)
  ↓
Implementation
  ↓
Walk-Forward Validation (never plain k-fold)
  ↓
Statistical Testing (Deflated Sharpe, Block Bootstrap, White's Reality Check)
  ↓
Kill Criteria Evaluation (pre-defined; failure → immediate rejection)
  ↓
Backtesting (transaction-cost adjusted)
  ↓
Out-of-Sample Validation (sealed dataset; one-shot; irreversible)
  ↓
Decision: ACCEPTED or REJECTED
  ↓
Research Log Entry (including adversarial review)
  ↓
FDR Tracker Update
  ↓
[If ACCEPTED] Monitoring
```

---

## Pre-Registration Requirements

A pre-registration document must be committed to `docs/research/pre-registrations/` **before any modeling code is written**.

The pre-registration must specify:

1. **Experiment ID** — format: `EXP-{NNN}` (zero-padded three digits)
2. **Title** — short descriptive title
3. **Research question** — one clear, answerable question
4. **Hypothesis (H1)** — the testable claim, written as a falsifiable statement
5. **Null hypothesis (H0)** — the claim to reject
6. **Justification** — why this hypothesis should work; cite literature where available
7. **Universe ID** — which fixed universe is used
8. **Dataset version hash** — content hash of the training + validation dataset
9. **Feature list** — every feature, specified to full parameter level (not concept-level)
10. **Model type and all hyperparameters** — must be fully specified; no TBD values
11. **Validation scheme** — exact parameters (window sizes, step sizes)
12. **Acceptance criteria** — quantitative thresholds that must be met
13. **Kill criteria** — conditions that immediately force rejection
14. **Sealed validation set hash** — the dataset that may only be used once, at the end
15. **Protocol version** — this document's version
16. **Git commit** — commit hash at time of pre-registration

---

## Sealed Final Validation Set

**The sealed validation set is a one-way gate.**

- It is hashed and recorded before any development begins.
- It is never used during feature selection, model selection, or hyperparameter tuning.
- It is evaluated **once**, after all development is frozen.
- That evaluation is irreversible — if the model fails, it is rejected; the set is not re-used for debugging.

The seal hash is verified programmatically before any evaluation run against the sealed set.

---

## Acceptance and Rejection

**A model may be ACCEPTED only if:**
- It passes all kill criteria
- It meets all acceptance criteria
- It passes the one-shot final validation

**A model must be REJECTED if:**
- Any kill criterion is met (regardless of other results)
- It fails to beat baselines on the primary metric
- It fails the final validation

**REJECTED experiments are never deleted.** They remain in the research log. The history of rejected experiments is evidence of a functioning research platform.

---

## Multiple Testing Protection

Because many hypotheses are tested over time:

1. Every hypothesis is logged in the Research Log, whether accepted or rejected.
2. A running False Discovery Rate (FDR) calculation is maintained.
3. The FDR uses Benjamini–Hochberg correction across all tests logged to date.
4. If the acceptance rate exceeds 20%, a mandatory methodology review is triggered.
5. The final validation set is separate from all development data and is never used for more than one final evaluation.

---

## Research Log Requirements

Every completed experiment must have a research log entry in `docs/research/research-log/`.

Required fields:
- Experiment ID and reference to pre-registration
- Walk-forward results (per fold)
- Aggregate results with confidence intervals
- Baseline comparison
- Decision (ACCEPTED or REJECTED)
- Rejection reasons (if rejected)
- **Adversarial review** — a written section asking "why might this result be spurious?"
- Lessons learned
- FDR contribution count
- MLflow run ID (if tracking is enabled)

---

## Regime Analysis

Every accepted model's performance must be reported broken down by market regime.

Regime definitions are fixed in `marketmind/regime/definitions.py` before any experiments begin. They are never redefined after observing results.

Version 1 regime classifier: volatility terciles of the trailing 20-day realised volatility of the benchmark index (SPY), computed at each bar using only past data.

---

## Protocol Amendments

Amendments to this protocol require:
1. A new protocol version number
2. A git commit with message `"protocol: bump to vN.N — reason"`
3. All future pre-registrations reference the new version
4. Previously accepted experiments under old protocol versions remain valid under their original protocol

---

*This protocol is the authoritative methodology document for MarketMind.*
*All experiments must comply with the version in effect at time of pre-registration.*
