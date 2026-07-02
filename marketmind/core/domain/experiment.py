"""
Experiment & Hypothesis Domain Objects
=======================================

Value objects representing the research workflow: from hypothesis formation
through pre-registration, execution, and final decision.

These objects enforce the scientific discipline of the platform. An Experiment
cannot transition to COMPLETED without a recorded decision. A decision cannot
be ACCEPTED without passing AcceptanceCriteria. These are not conventions —
they are enforced by the domain model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ExperimentStatus(StrEnum):
    """
    Lifecycle states of a research experiment.

    State transitions are strictly enforced:
        REGISTERED → IN_PROGRESS → COMPLETED → ACCEPTED | REJECTED

    No other transitions are permitted. In particular, REJECTED experiments
    cannot be moved back to IN_PROGRESS — start a new experiment instead.
    """

    REGISTERED = "REGISTERED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"

    def can_transition_to(self, target: ExperimentStatus) -> bool:
        """Return True if transitioning from this status to `target` is permitted."""
        transitions: dict[ExperimentStatus, list[ExperimentStatus]] = {
            ExperimentStatus.REGISTERED: [ExperimentStatus.IN_PROGRESS],
            ExperimentStatus.IN_PROGRESS: [ExperimentStatus.COMPLETED],
            ExperimentStatus.COMPLETED: [
                ExperimentStatus.ACCEPTED,
                ExperimentStatus.REJECTED,
            ],
            ExperimentStatus.ACCEPTED: [],
            ExperimentStatus.REJECTED: [],
        }
        return target in transitions.get(self, [])


@dataclass(frozen=True)
class AcceptanceCriteria:
    """
    Quantitative thresholds that a hypothesis must meet to be accepted.

    All criteria are specified in the pre-registration document
    before any experiment runs. They may not be modified after
    the experiment begins.

    Attributes
    ----------
    primary_metric:
        The single metric that determines accept/reject.
        Example: "deflated_sharpe_ratio"
    primary_threshold:
        The minimum value (or description) the primary metric must achieve.
        Example: "> 0.0 at 95% block-bootstrap CI lower bound"
    secondary_criteria:
        Additional constraints that must all be met alongside the primary.
        These do not override the primary — they are additional gates.
    """

    primary_metric: str
    primary_threshold: str
    secondary_criteria: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KillCriteria:
    """
    Conditions that immediately terminate an experiment and force rejection.

    Kill criteria are evaluated before acceptance criteria. If any kill
    criterion is met, the experiment is rejected regardless of primary metric.

    Kill criteria force researchers to think about failure modes *before*
    seeing results — this reduces the temptation to rationalise poor outcomes.
    """

    criteria: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.criteria:
            raise ValueError(
                "KillCriteria must contain at least one criterion. "
                "An experiment with no kill criteria has no falsifiability."
            )


@dataclass(frozen=True)
class PreRegistration:
    """
    The pre-experiment declaration of hypothesis, methodology, and criteria.

    A PreRegistration is committed to version control before any code that
    implements the experiment is written. This creates a permanent, dated
    record of what was expected before the results were seen.

    The pre-registration is immutable once created. If methodology must
    change after registration, create a new experiment with a new ID and
    document why the change was necessary.

    Attributes
    ----------
    experiment_id:
        Unique identifier. Convention: "EXP-{NNN}" e.g. "EXP-007"
    title:
        Short descriptive title.
    research_question:
        The question this experiment is designed to answer.
    hypothesis:
        H1: the testable claim. Written as a falsifiable statement.
    null_hypothesis:
        H0: the claim to be rejected if H1 is supported.
    justification:
        Why this hypothesis should work. Cite literature if available.
    universe_id:
        ID of the fixed research universe used.
    dataset_version_hash:
        Hash of the dataset version used for training and validation.
    feature_list:
        Exact features used. Specified to full parameter level, not concept.
    model_type:
        The model class name.
    model_params:
        Complete hyperparameter dict. Must be fully specified — no "TBD".
    validation_scheme:
        How the model is validated. e.g. "walk_forward"
    validation_params:
        Exact parameters of the validation scheme.
    acceptance_criteria:
        What the model must achieve to be accepted.
    kill_criteria:
        What immediately triggers rejection.
    final_validation_set_hash:
        Hash of the sealed final validation dataset.
        This set is never touched during development.
    protocol_version:
        Version of the research protocol in effect when this was registered.
    git_commit:
        Git commit hash at time of pre-registration.
    created_at:
        UTC timestamp of pre-registration creation.
    """

    experiment_id: str
    title: str
    research_question: str
    hypothesis: str
    null_hypothesis: str
    justification: str
    universe_id: str
    dataset_version_hash: str
    feature_list: tuple[str, ...]
    model_type: str
    model_params: dict[str, Any]
    validation_scheme: str
    validation_params: dict[str, Any]
    acceptance_criteria: AcceptanceCriteria
    kill_criteria: KillCriteria
    final_validation_set_hash: str
    protocol_version: str
    git_commit: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.experiment_id.startswith("EXP-"):
            raise ValueError(f"experiment_id must start with 'EXP-', got {self.experiment_id!r}")
        if not self.hypothesis:
            raise ValueError("hypothesis cannot be empty.")
        if not self.null_hypothesis:
            raise ValueError("null_hypothesis cannot be empty.")
        if not self.feature_list:
            raise ValueError(
                "feature_list cannot be empty. At least one feature must be specified."
            )


@dataclass
class Experiment:
    """
    A research experiment tracking its full lifecycle.

    An Experiment wraps a PreRegistration and tracks its progress through
    the research workflow. Status transitions are enforced.

    Unlike domain value objects (frozen), Experiment is mutable because
    its status changes over time. All mutations must go through the
    explicit transition methods, never by directly setting status.
    """

    pre_registration: PreRegistration
    status: ExperimentStatus = ExperimentStatus.REGISTERED
    mlflow_run_id: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    decided_at: datetime | None = None

    @property
    def experiment_id(self) -> str:
        return self.pre_registration.experiment_id

    def start(self, at: datetime | None = None) -> None:
        """Transition from REGISTERED to IN_PROGRESS."""
        self._require_transition(ExperimentStatus.IN_PROGRESS)
        self.status = ExperimentStatus.IN_PROGRESS
        self.started_at = at or datetime.now(UTC)

    def complete(self, at: datetime | None = None) -> None:
        """Transition from IN_PROGRESS to COMPLETED."""
        self._require_transition(ExperimentStatus.COMPLETED)
        self.status = ExperimentStatus.COMPLETED
        self.completed_at = at or datetime.now(UTC)

    def accept(self, at: datetime | None = None) -> None:
        """Transition from COMPLETED to ACCEPTED."""
        self._require_transition(ExperimentStatus.ACCEPTED)
        self.status = ExperimentStatus.ACCEPTED
        self.decided_at = at or datetime.now(UTC)

    def reject(self, at: datetime | None = None) -> None:
        """Transition from COMPLETED to REJECTED."""
        self._require_transition(ExperimentStatus.REJECTED)
        self.status = ExperimentStatus.REJECTED
        self.decided_at = at or datetime.now(UTC)

    def _require_transition(self, target: ExperimentStatus) -> None:
        from marketmind.core.exceptions import ExperimentStateError

        if not self.status.can_transition_to(target):
            raise ExperimentStateError(
                f"Cannot transition experiment {self.experiment_id} "
                f"from {self.status.value} to {target.value}."
            )

    def __str__(self) -> str:
        return f"Experiment({self.experiment_id}, status={self.status.value})"
