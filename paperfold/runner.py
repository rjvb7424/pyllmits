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
from pathlib import Path

from config import ModelSpec
from models import build_model
from paperfold.cognitive_test import CognitiveTest
from run_control import RunControl, StopExperiment

LOG = logging.getLogger("crafter_experiment.paperfold.run")


class PaperfoldRunner:
    """Runs every model over every trial of the paper-folding test."""

    def __init__(
        self,
        run_name: str,
        num_trials: int,
        num_folds: int,
        model_specs: list[ModelSpec],
        runs_dir: Path,
        control: "RunControl | None" = None,
    ):
        self.run_name = run_name
        self.num_trials = int(num_trials)
        self.num_folds = int(num_folds)
        self.model_specs = model_specs
        self.run_dir = Path(runs_dir) / run_name
        self.control = control
        # May raise ValueError if this run name already holds results for a
        # different num_folds - trials from two different puzzle difficulties
        # would give a meaningless combined accuracy number.
        self.results = self._load_or_init_results()

    @property
    def results_path(self) -> Path:
        return self.run_dir / "results.json"

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

        try:
            for trial in range(done, total):
                if self.control is not None:
                    self.control.checkpoint()
                    self.control.update(
                        state="running", model=spec.name,
                        trial=trial + 1, num_trials=total,
                    )
                LOG.info("[%s] trial %d/%d ...", spec.name, trial + 1, total)
                result = self._run_trial(spec, model, trial)
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
                    )
        finally:
            model.unload()

    # =========================================================================
    #  One trial
    # =========================================================================
    def _run_trial(self, spec: ModelSpec, model, trial_index: int) -> dict:
        model.reset()  # clear any conversation memory so trials don't bleed together
        test = CognitiveTest()
        result = test.run(num_folds=self.num_folds, solver=self._solver_for(model))
        result["trial"] = trial_index + 1
        # Tag the result with the model we intended to test, even if the
        # solver call failed and couldn't report its own model_version. This
        # keeps per-model resume counting accurate (mirrors legacy run.py).
        result["model_version"] = spec.name
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
    def _load_or_init_results(self) -> dict:
        fingerprint = {"num_folds": self.num_folds}
        if self.results_path.exists():
            existing = json.loads(self.results_path.read_text())
            old_fp = existing.get("config_fingerprint")
            if old_fp is not None and old_fp != fingerprint:
                raise ValueError(
                    f"'{self.run_name}' already has results with a different "
                    f"num_folds ({old_fp.get('num_folds')} vs {self.num_folds}). "
                    f"Merging them would give a meaningless accuracy number. "
                    f"Pick a different run name, or delete {self.run_dir} to start over."
                )
            LOG.info("Found existing results - resuming (config matches).")
            existing.setdefault("config_fingerprint", fingerprint)
            # Keep current: on resume, num_trials may have grown - the stored
            # value would otherwise stay stale and mislead the plots.
            existing["num_trials"] = self.num_trials
            existing["num_folds"] = self.num_folds
            return existing
        return {
            "experiment": self.run_name,
            "config_fingerprint": fingerprint,
            "num_trials": self.num_trials,
            "num_folds": self.num_folds,
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
