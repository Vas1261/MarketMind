"""
Unit tests for marketmind.core.domain.experiment

Tests state machine transitions, invariants, and the pre-registration
validation rules that enforce research discipline.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from marketmind.core.domain.experiment import (
    AcceptanceCriteria,
    Experiment,
    ExperimentStatus,
    KillCriteria,
    PreRegistration,
)
from marketmind.core.exceptions import ExperimentStateError


class TestExperimentStatus:
    """Tests for the ExperimentStatus state machine."""

    def test_registered_can_transition_to_in_progress(self) -> None:
        assert ExperimentStatus.REGISTERED.can_transition_to(ExperimentStatus.IN_PROGRESS)

    def test_in_progress_can_transition_to_completed(self) -> None:
        assert ExperimentStatus.IN_PROGRESS.can_transition_to(ExperimentStatus.COMPLETED)

    def test_completed_can_transition_to_accepted(self) -> None:
        assert ExperimentStatus.COMPLETED.can_transition_to(ExperimentStatus.ACCEPTED)

    def test_completed_can_transition_to_rejected(self) -> None:
        assert ExperimentStatus.COMPLETED.can_transition_to(ExperimentStatus.REJECTED)

    def test_accepted_cannot_transition_anywhere(self) -> None:
        for target in ExperimentStatus:
            assert not ExperimentStatus.ACCEPTED.can_transition_to(target)

    def test_rejected_cannot_transition_anywhere(self) -> None:
        for target in ExperimentStatus:
            assert not ExperimentStatus.REJECTED.can_transition_to(target)

    def test_registered_cannot_skip_to_completed(self) -> None:
        assert not ExperimentStatus.REGISTERED.can_transition_to(ExperimentStatus.COMPLETED)


class TestKillCriteria:
    """Tests for KillCriteria invariant."""

    def test_creates_with_single_criterion(self) -> None:
        kc = KillCriteria(criteria=("Sharpe CI <= 0.0",))
        assert len(kc.criteria) == 1

    def test_empty_criteria_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one criterion"):
            KillCriteria(criteria=())

    def test_immutable(self) -> None:
        kc = KillCriteria(criteria=("criterion",))
        with pytest.raises(FrozenInstanceError):
            kc.criteria = ("tampered",)  # type: ignore[misc]


class TestPreRegistration:
    """Tests for PreRegistration invariants."""

    def _make_pre_reg(self, **overrides) -> PreRegistration:  # type: ignore[no-untyped-def]
        defaults: dict = {
            "experiment_id": "EXP-001",
            "title": "Test",
            "research_question": "Does feature X contain signal?",
            "hypothesis": "H1: Feature X predicts direction.",
            "null_hypothesis": "H0: No directional accuracy above baseline.",
            "justification": "Literature says so.",
            "universe_id": "UNIVERSE-V1",
            "dataset_version_hash": "abc",
            "feature_list": ("rsi_14",),
            "model_type": "LogisticRegression",
            "model_params": {"C": 1.0},
            "validation_scheme": "walk_forward",
            "validation_params": {"train_window_years": 3},
            "acceptance_criteria": AcceptanceCriteria(
                primary_metric="deflated_sharpe_ratio",
                primary_threshold="> 0.0",
            ),
            "kill_criteria": KillCriteria(criteria=("DSR <= 0.0",)),
            "final_validation_set_hash": "sealed",
            "protocol_version": "1.0",
            "git_commit": "abc123",
            "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        }
        defaults.update(overrides)
        return PreRegistration(**defaults)

    def test_creates_valid_pre_registration(self) -> None:
        pr = self._make_pre_reg()
        assert pr.experiment_id == "EXP-001"

    def test_id_must_start_with_exp(self) -> None:
        with pytest.raises(ValueError, match="must start with 'EXP-'"):
            self._make_pre_reg(experiment_id="007-WRONG")

    def test_empty_hypothesis_raises(self) -> None:
        with pytest.raises(ValueError, match="hypothesis cannot be empty"):
            self._make_pre_reg(hypothesis="")

    def test_empty_null_hypothesis_raises(self) -> None:
        with pytest.raises(ValueError, match="null_hypothesis cannot be empty"):
            self._make_pre_reg(null_hypothesis="")

    def test_empty_feature_list_raises(self) -> None:
        with pytest.raises(ValueError, match="feature_list cannot be empty"):
            self._make_pre_reg(feature_list=())

    def test_immutable(self) -> None:
        pr = self._make_pre_reg()
        with pytest.raises(FrozenInstanceError):
            pr.experiment_id = "EXP-999"  # type: ignore[misc]


class TestExperiment:
    """Tests for the Experiment state machine."""

    def _make_experiment(self) -> Experiment:
        pr = PreRegistration(
            experiment_id="EXP-001",
            title="Test",
            research_question="Test question",
            hypothesis="H1: something",
            null_hypothesis="H0: nothing",
            justification="Because.",
            universe_id="UNIVERSE-V1",
            dataset_version_hash="abc",
            feature_list=("feature_a",),
            model_type="LogisticRegression",
            model_params={},
            validation_scheme="walk_forward",
            validation_params={},
            acceptance_criteria=AcceptanceCriteria(
                primary_metric="sharpe", primary_threshold="> 0"
            ),
            kill_criteria=KillCriteria(criteria=("sharpe <= 0",)),
            final_validation_set_hash="sealed",
            protocol_version="1.0",
            git_commit="abc",
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        return Experiment(pre_registration=pr)

    def test_initial_status_is_registered(self) -> None:
        exp = self._make_experiment()
        assert exp.status == ExperimentStatus.REGISTERED

    def test_start_transitions_to_in_progress(self) -> None:
        exp = self._make_experiment()
        exp.start()
        assert exp.status == ExperimentStatus.IN_PROGRESS
        assert exp.started_at is not None

    def test_complete_transitions_to_completed(self) -> None:
        exp = self._make_experiment()
        exp.start()
        exp.complete()
        assert exp.status == ExperimentStatus.COMPLETED

    def test_accept_transitions_to_accepted(self) -> None:
        exp = self._make_experiment()
        exp.start()
        exp.complete()
        exp.accept()
        assert exp.status == ExperimentStatus.ACCEPTED
        assert exp.decided_at is not None

    def test_reject_transitions_to_rejected(self) -> None:
        exp = self._make_experiment()
        exp.start()
        exp.complete()
        exp.reject()
        assert exp.status == ExperimentStatus.REJECTED

    def test_cannot_accept_without_completing_first(self) -> None:
        exp = self._make_experiment()
        exp.start()
        with pytest.raises(ExperimentStateError):
            exp.accept()

    def test_cannot_start_twice(self) -> None:
        exp = self._make_experiment()
        exp.start()
        with pytest.raises(ExperimentStateError):
            exp.start()

    def test_cannot_reject_accepted_experiment(self) -> None:
        exp = self._make_experiment()
        exp.start()
        exp.complete()
        exp.accept()
        with pytest.raises(ExperimentStateError):
            exp.reject()

    def test_experiment_id_delegates_to_pre_registration(self) -> None:
        exp = self._make_experiment()
        assert exp.experiment_id == "EXP-001"

    def test_str_representation(self) -> None:
        exp = self._make_experiment()
        assert "EXP-001" in str(exp)
        assert "REGISTERED" in str(exp)
