"""
paperfold/runner.py
====================

Drives a paper-folding batch:

    for each model:
        for each trial:
            build a fresh folded/punched puzzle, ask the model to solve it,
            grade the answer
        record accuracy + full per-trial transcript
        SAVE results.json          (crash-safe, after every trial)

Mirrors experiment.ExperimentRunner's design choices, on purpose, so the two
experiment types behave the same way operationally even though they share no
domain logic:
  * results.json is rewritten atomically after every trial, so a crash mid-run
    never loses completed trials.
  * per-model resume: on restart, trials already in results.json are skipped.
  * a model that fails to load is recorded and skipped; the run continues.
  * every trial calls model.reset() first, so no conversation memory a
    backend might keep can leak one puzzle's answer into the next trial.

The only thing borrowed from models/ is the LanguageModel interface
(models.build_model / model.generate(system_prompt, user_prompt)) - there is
no paper-folding-specific AI-calling code anywhere in this file.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import tempfile
import time
from pathlib import Path

from config import ModelSpec
from models import build_model
from paperfold.cognitive_test import CognitiveTest, random_direction_labels
from run_control import RunControl, StopExperiment

LOG = logging.getLogger("crafter_experiment.paperfold.run")

DIRECTION_MODES = ("real", "fixed", "random")


class PaperfoldRunner:
    """Runs every model over every trial of the paper-folding test."""

    def __init__(
        self,
        run_name: str,
        num_trials: int,
        num_folds: int,
        model_specs: list[ModelSpec],
        runs_dir: Path,
        direction_mode: str = "real",
        direction_labels: dict | None = None,
        control: "RunControl | None" = None,
    ):
        self.run_name = run_name
        self.num_trials = int(num_trials)
        self.num_folds = int(num_folds)
        self.model_specs = model_specs
        self.run_dir = Path(runs_dir) / run_name
        # "real": use north/south/east/west as-is (default, matches the
        #   original prototype exactly).
        # "fixed": direction_labels is used for every trial in this run.
        # "random": a fresh random mapping is drawn for every trial (still
        #   explained at the top of that trial's own prompt) - the more
        #   rigorous variant for testing whether a model's accuracy comes
        #   from real spatial reasoning or from pattern-matching on the
        #   literal words "north"/"south"/"east"/"west".
        self.direction_mode = direction_mode if direction_mode in DIRECTION_MODES else "real"
        self.direction_labels = direction_labels
        self.control = control
        # May raise ValueError if this run name already holds results for a
        # different num_folds/direction scheme - trials answered under
        # different puzzle difficulty or wording would give a meaningless
        # combined accuracy number.
        self.results = self._load_or_init_results()
        # Every configured model gets a record immediately, not lazily as
        # _run_model reaches it - otherwise a crash partway through a batch
        # (or just constructing a runner to save a setup without running it)
        # would leave the not-yet-started models completely absent from
        # results.json, which is exactly what silently dropped them from the
        # "resume this run" picker.
        self._ensure_model_records()

    @property
    def results_path(self) -> Path:
        return self.run_dir / "results.json"

    def _ensure_model_records(self) -> None:
        for spec in self.model_specs:
            self.results["models"].setdefault(
                spec.name, {"backend": spec.backend, "slug": spec.slug, "error": None, "trials": []}
            )

    def save(self) -> None:
        """Persist the current setup/results to disk. Safe to call without
        ever running anything - used to save a setup for later."""
        self._save()

    # =========================================================================
    #  Top-level loop
    # =========================================================================
    def run(self) -> dict:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if self.control:
            self.control.update(state="running")
        try:
            for spec in self.model_specs:
                self._run_model(spec)
        except StopExperiment:
            LOG.info("Paper-folding run stopped by user. Progress saved.")
            self._save()
            if self.control:
                self.control.update(state="stopped")
            return self.results
        if self.control:
            self.control.update(state="finished")
        LOG.info("Done. Results at %s", self.results_path)
        return self.results

    def _run_model(self, spec: ModelSpec) -> None:
        record = self.results["models"].setdefault(
            spec.name, {"backend": spec.backend, "slug": spec.slug, "error": None, "trials": []}
        )
        done = len(record["trials"])
        total = self.num_trials
        if done >= total:
            LOG.info("[%s] already complete (%d/%d) - skipping.", spec.name, done, total)
            return

        LOG.info("[%s] loading (resuming at trial %d/%d)...", spec.name, done, total)
        model = build_model(spec)
        try:
            model.load()
        except Exception as exc:  # e.g. missing/invalid API key
            LOG.error("[%s] failed to load: %s", spec.name, exc)
            record["error"] = f"load failed: {exc}"
            self._save()
            return
        # A previous attempt's error (load failure or a mid-trial crash) no
        # longer applies once loading succeeds again - don't leave a stale
        # message sitting next to trials that are now succeeding.
        record["error"] = None

        try:
            for trial in range(done, total):
                labels = self._trial_direction_labels()
                if self.control is not None:
                    self.control.checkpoint()
                    self.control.update(
                        state="running", model=spec.name,
                        trial=trial + 1, num_trials=total,
                        direction_labels=labels, trial_started_at=time.time(),
                    )
                LOG.info("[%s] trial %d/%d ...", spec.name, trial + 1, total)
                try:
                    result = self._run_trial(spec, model, trial, labels)
                except Exception as exc:
                    # Isolate the failure to this one model - e.g. a transient
                    # provider error - rather than aborting every other model
                    # in the run. Trials already completed for this model (and
                    # every other model's progress) stay intact; this model
                    # simply resumes from here on the next Start.
                    LOG.error("[%s] trial %d failed: %s", spec.name, trial + 1, exc)
                    record["error"] = f"trial {trial + 1} failed: {exc}"
                    self._save()
                    break
                record["trials"].append(result)
                self._save()  # crash-safe: persist after every trial
                LOG.info(
                    "[%s] trial %d -> %s (predicted %s, correct %s)",
                    spec.name, trial + 1,
                    "CORRECT" if result["is_correct"] else "wrong",
                    result["predicted_choice"], result["correct_choice"],
                )
                if self.control is not None:
                    self.control.update(
                        state="running", model=spec.name, trial=trial + 1, num_trials=total,
                        last_predicted=result["predicted_choice"],
                        last_correct_choice=result["correct_choice"],
                        last_is_correct=result["is_correct"],
                        direction_labels=labels,
                        trial_started_at=None,
                        last_elapsed_seconds=result["elapsed_seconds"],
                        last_raw_response=result["raw_response"],
                        last_prompt=result["prompt"],
                    )
        finally:
            model.unload()

    def _trial_direction_labels(self) -> dict | None:
        """The {direction: placeholder} mapping for the next trial, or None
        to use the real direction names. Computed once per trial (not inside
        _run_trial) so the exact same mapping used for the puzzle is also
        what gets reported to the polled status - never two independently
        rolled "random" mappings for one trial."""
        if self.direction_mode == "fixed":
            return dict(self.direction_labels) if self.direction_labels else None
        if self.direction_mode == "random":
            return random_direction_labels()
        return None

    # =========================================================================
    #  One trial
    # =========================================================================
    def _run_trial(self, spec: ModelSpec, model, trial_index: int, direction_labels: dict | None) -> dict:
        model.reset()  # clear any conversation memory so trials don't bleed together
        test = CognitiveTest(direction_labels=direction_labels)
        result = test.run(num_folds=self.num_folds, solver=self._solver_for(model))
        result["trial"] = trial_index + 1
        # Tag the result with the model we intended to test, even if the
        # solver call failed and couldn't report its own model_version. This
        # keeps per-model resume counting accurate (mirrors legacy run.py).
        result["model_version"] = spec.name
        # Ground truth (fold_history) is always the real direction names -
        # this records what was actually shown to the model that trial.
        result["direction_labels"] = direction_labels
        return result

    @staticmethod
    def _solver_for(model):
        """Adapt a models.LanguageModel to the solver(prompt) -> dict contract
        CognitiveTest.run() expects. The full puzzle text is sent as the user
        prompt (no system prompt) so the AI-facing content matches the
        original prototype exactly - only the transport changes."""
        def solve(prompt: str) -> dict:
            text, elapsed = model.generate("", prompt)
            return {
                "text": text,
                "elapsed_seconds": elapsed,
                "total_tokens": getattr(model, "last_usage", None),
                "model_version": model.name,
            }
        return solve

    # =========================================================================
    #  Persistence
    # =========================================================================
    def _fingerprint(self) -> dict:
        fp = {"num_folds": self.num_folds, "direction_mode": self.direction_mode}
        if self.direction_mode == "fixed":
            fp["direction_labels"] = self.direction_labels
        return fp

    def _load_or_init_results(self) -> dict:
        fingerprint = self._fingerprint()
        if self.results_path.exists():
            existing = json.loads(self.results_path.read_text())
            old_fp = existing.get("config_fingerprint")
            if old_fp is not None and old_fp != fingerprint:
                raise ValueError(
                    f"'{self.run_name}' already has results with a different "
                    f"setup ({old_fp} vs {fingerprint}). Merging them would "
                    f"give a meaningless accuracy number. Pick a different "
                    f"run name, or delete {self.run_dir} to start over."
                )
            LOG.info("Found existing results - resuming (config matches).")
            existing.setdefault("config_fingerprint", fingerprint)
            # Keep current: on resume, num_trials may have grown - the stored
            # value would otherwise stay stale and mislead the plots.
            existing["num_trials"] = self.num_trials
            existing["num_folds"] = self.num_folds
            existing["direction_mode"] = self.direction_mode
            return existing
        return {
            "experiment": self.run_name,
            "config_fingerprint": fingerprint,
            "num_trials": self.num_trials,
            "num_folds": self.num_folds,
            "direction_mode": self.direction_mode,
            "created": _now(),
            "updated": _now(),
            "models": {},
        }

    def _save(self) -> None:
        """Atomically rewrite results.json so a crash can't corrupt it."""
        self.results["updated"] = _now()
        path = self.results_path
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(self.results, fh, indent=2)
        os.replace(tmp, path)


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")
