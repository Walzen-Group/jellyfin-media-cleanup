"""
Wizard state synchronization for multi-tab/multi-client consistency.

Stores the 4-step wizard state on the backend and broadcasts changes
via WebSocket so all connected clients stay in sync.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from media_cleanup.models.base import _Base
from media_cleanup.models.run_plan import FullSeriesDeletion, MovieDeletion, SeasonCleanup

logger = logging.getLogger(__name__)


class AnalysisParams(_Base):
    mode: str = "all"
    month_threshold: int = 24
    added_threshold: int = 12
    precise_matching: bool = True
    apply_auto_keep: bool = True


class FilterSettings(_Base):
    categories: list[str] = []
    greedy: bool = False
    media_type: str = "all"
    min_size_bytes: int = 0
    max_size_bytes: int | None = None


class PrepareSelections(_Base):
    movie_deletions: list[MovieDeletion] = []
    full_series_deletions: list[FullSeriesDeletion] = []
    season_cleanups: list[SeasonCleanup] = []


class WizardState(_Base):
    step: int = 1
    analysis_params: AnalysisParams | None = None
    filter_settings: FilterSettings | None = None
    prepare_selections: PrepareSelections | None = None
    job_id: str | None = None
    version: int = 0


class WizardStateUpdate(_Base):
    step: int | None = None
    analysis_params: AnalysisParams | None = None
    filter_settings: FilterSettings | None = None
    prepare_selections: PrepareSelections | None = None
    job_id: str | None = None


class WizardStateManager:
    """Thread-safe wizard state store with WebSocket broadcast."""

    def __init__(self) -> None:
        self._state = WizardState()
        self._lock = threading.Lock()
        self._broadcast_fn: Callable[[dict], None] | None = None

    def set_broadcast(self, fn: Callable[[dict], None]) -> None:
        self._broadcast_fn = fn

    def get_state(self) -> WizardState:
        with self._lock:
            return self._state

    def update(
        self,
        step: int | None = None,
        analysis_params: AnalysisParams | None = None,
        filter_settings: FilterSettings | None = None,
        prepare_selections: PrepareSelections | None = None,
        job_id: str | None = None,
    ) -> WizardState:
        with self._lock:
            if step is not None:
                self._state.step = step
            if analysis_params is not None:
                self._state.analysis_params = analysis_params
            if filter_settings is not None:
                self._state.filter_settings = filter_settings
            if prepare_selections is not None:
                self._state.prepare_selections = prepare_selections
            if job_id is not None:
                self._state.job_id = job_id
            self._state.version += 1
            state = self._state

        self._broadcast({"type": "wizard_state_changed", "state": state.model_dump(by_alias=True)})
        return state

    def reset(self) -> WizardState:
        with self._lock:
            self._state = WizardState()
            state = self._state

        self._broadcast({"type": "wizard_state_changed", "state": state.model_dump(by_alias=True)})
        return state

    def get_sync_message(self) -> dict:
        return {"type": "wizard_state_sync", "state": self._state.model_dump(by_alias=True)}

    def _broadcast(self, message: dict) -> None:
        if self._broadcast_fn:
            try:
                self._broadcast_fn(message)
            except Exception:
                logger.exception("Wizard state broadcast failed")
