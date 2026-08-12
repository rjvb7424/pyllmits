"""
llmits.paperfold.runner
=======================

Drives a paper-folding batch:

    for each model:
        for each fold count in the run's range (3, then 4, then 5, ...):
            for each trial:
                build a fresh folded/punched puzzle at that many folds, ask
                the model to solve it, grade the answer
        record accuracy + full per-trial transcript
        SAVE results.json          (crash-safe, after every trial)

A run tests one fold count (fold_counts=[3], the original behaviour) or a
whole increasing range (fold_counts=[3, 4, 5, 6]) - the latter is what the
"accuracy vs number of folds" difficulty curve in paperfold/analysis.py is
plotted from. num_trials is per fold count, so 10 trials over 3..6 folds is
40 puzzles per model. Each fold count gets its own paper size, big enough to
survive that many folds (see cognitive_test.paper_size_for_folds).

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
from collections import Counter
from pathlib import Path

from llmits.config import ModelSpec
from llmits.models import build_model
from llmits.paperfold.cognitive_test import (
    CognitiveTest, paper_size_for_folds, random_direction_labels,
)
from llmits.run_control import RunControl, StopExperiment

LOG = logging.getLogger("crafter_experiment.paperfold.run")

DIRECTION_MODES = ("real", "fixed", "random")


def normalize_fold_counts(num_folds) -> list[int]:
    """Accept either a single fold count or a collection of them, and return
    the sorted, de-duplicated list of counts a run should sweep.

    One entry means the classic "every puzzle has N folds" run; several mean
    the difficulty sweep (N trials at 3 folds, then N at 4, ...). Sorted so
    the run always works from easiest to hardest, whatever order the counts
    arrived in.
    """
    if isinstance(num_folds, (list, tuple, set, frozenset, range)):
        counts = sorted({int(v) for v in num_folds})
    else:
        counts = [int(num_folds)]
    if not counts:
        raise ValueError("A run needs at least one fold count.")
    if counts[0] < 0:
        raise ValueError(f"Fold counts can't be negative (got {counts[0]}).")
    return counts


class PaperfoldRunner:
    """Runs every model over every trial of the paper-folding test."""

    def __init__(
        self,
        run_name: str,
        num_trials: int,
        num_folds: int | list[int],
        model_specs: list[ModelSpec],
        runs_dir: Path,
        direction_mode: str = "real",
        direction_labels: dict | None = None,
        control: "RunControl | None" = None,
    ):
        self.run_name = run_name
        # Trials *per fold count*, not per model: a 10-trial run sweeping
        # 3..6 folds asks each model 40 puzzles. For a single-fold-count run
        # (the original shape) the two are the same thing.
        self.num_trials = int(num_trials)
        # num_folds accepts an int (one fold count) or a collection of ints
        # (the increasing-difficulty sweep) - see normalize_fold_counts.
        self.fold_counts = normalize_fold_counts(num_folds)
        self.num_folds = self.fold_counts[0]
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

    @property
    def total_trials(self) -> int:
        """Puzzles per model across the whole run - num_trials at each of the
        run's fold counts."""
        return self.num_trials * len(self.fold_counts)

    def _pending_folds(self, trials: list[dict]) -> list[int]:
        """The fold counts still owed for a model, easiest first, given the
        trials it already has on disk.

        Counted per fold count (from each trial's own recorded "num_folds")
        rather than from the plain length of the trial list, so resuming
        stays correct when the setup changed between runs: raising trials per
        fold count tops each fold count up individually, and widening the
        range (3..5 -> 3..7) runs only the newly added counts. Nothing is ever
        owed for a fold count outside the current range - trials recorded at
        one stay on disk and in the graphs, they're just not added to. (That
        only arises for a run whose range shrank, which _load_or_init_results
        refuses once there are trials to protect.)
        """
        done = Counter(t.get("num_folds") for t in trials)
        return [folds
                for folds in self.fold_counts
                for _ in range(max(0, self.num_trials - done.get(folds, 0)))]

    def _ensure_model_records(self) -> None:
        """Rebuild the models dict to exactly match model_specs - same order
        and same membership - every time a runner is constructed (Save setup
        or Start both go through here).

        Order: a dict only remembers *first-insertion* order, so previously
        this only ever recorded the order models were first added in, and a
        later drag-reorder in Setup never stuck - reloading the run always
        showed the original order again. Rebuilding fresh each time instead
        of setdefault-ing into the old dict makes the saved order match
        whatever's in model_specs right now.

        Membership: a model no longer in model_specs (removed in Setup) is
        simply left out of the rebuilt dict, so its recorded trials are
        dropped along with it instead of lingering as orphaned data for a
        model that's no longer part of the run.

        Existing trials/error for a model still present carry over untouched;
        only backend/slug/options are refreshed to the latest configured
        values (so editing max_tokens/temperature and re-saving updates what's
        on disk instead of the first-ever save winning forever).
        """
        existing = self.results.get("models", {})
        self.results["models"] = {
            spec.name: {
                "backend": spec.backend,
                "slug": spec.slug,
                "options": spec.options,
                "error": existing.get(spec.name, {}).get("error"),
                "trials": existing.get(spec.name, {}).get("trials", []),
            }
            for spec in self.model_specs
        }

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
        pending = self._pending_folds(record["trials"])
        total = self.total_trials
        done = total - len(pending)
        if not pending:
            LOG.info("[%s] already complete (%d/%d) - skipping.", spec.name, done, total)
            return

        LOG.info("[%s] loading (resuming at trial %d/%d)...", spec.name, done, total)
        model = build_model(spec, control=self.control)
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
            for offset, folds in enumerate(pending):
                trial = done + offset
                labels = self._trial_direction_labels()
                paper_w, paper_h = paper_size_for_folds(folds)
                if self.control is not None:
                    self.control.checkpoint()
                    self.control.update(
                        state="running", model=spec.name,
                        trial=trial + 1, num_trials=total,
                        num_folds=folds, fold_counts=list(self.fold_counts),
                        paper_size=f"{paper_w}x{paper_h}",
                        direction_labels=labels, trial_started_at=time.time(),
                    )
                LOG.info("[%s] trial %d/%d (%d folds, %dx%d paper) ...",
                         spec.name, trial + 1, total, folds, paper_w, paper_h)
                try:
                    result = self._run_trial(spec, model, trial, labels, folds)
                except StopExperiment:
                    # A model call can be stuck in retry backoff when Stop is
                    # pressed - that raises StopExperiment here too (not just
                    # at the checkpoint() above), and it must propagate up to
                    # run()'s handler, not get recorded as a trial failure.
                    raise
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
                    "[%s] trial %d -> %s (predicted %s, correct %s, %d folds)",
                    spec.name, trial + 1,
                    "CORRECT" if result["is_correct"] else "wrong",
                    result["predicted_choice"], result["correct_choice"], folds,
                )
                if self.control is not None:
                    self.control.update(
                        state="running", model=spec.name, trial=trial + 1, num_trials=total,
                        num_folds=folds, fold_counts=list(self.fold_counts),
                        paper_size=f"{paper_w}x{paper_h}",
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
    def _run_trial(self, spec: ModelSpec, model, trial_index: int,
                   direction_labels: dict | None, num_folds: int) -> dict:
        model.reset()  # clear any conversation memory so trials don't bleed together
        # The puzzle sizes its own paper from num_folds - a 6-fold puzzle gets
        # a bigger sheet than a 3-fold one, or the last folds would have
        # nothing left to halve.
        test = CognitiveTest(num_folds=num_folds, direction_labels=direction_labels)
        result = test.run(solver=self._solver_for(model))
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
        # A plain int for a single-fold-count run, a list for a sweep. Kept
        # that way on purpose: it's what runs recorded before fold sweeps
        # existed still carry, so those runs keep matching their own
        # fingerprint and stay resumable instead of being refused as "a
        # different setup". _is_fold_extension() below then lets one of those
        # 3-fold runs be widened into a 3..6 sweep without losing its trials.
        counts = self.fold_counts
        fp = {"num_folds": counts[0] if len(counts) == 1 else list(counts),
              "direction_mode": self.direction_mode}
        if self.direction_mode == "fixed":
            fp["direction_labels"] = self.direction_labels
        return fp

    @staticmethod
    def _is_fold_extension(old_fp: dict, new_fp: dict) -> bool:
        """True when the only difference between two fingerprints is that the
        new one sweeps *more* fold counts than the old one.

        Adding fold counts to a run is safe in a way other setup changes
        aren't: every trial records the fold count it was answered at, and the
        accuracy-vs-folds graph reports each one separately, so the trials
        already on disk stay exactly as valid as they were. It's also the
        natural next step from an existing run - take a 3-fold run and extend
        it into a 3..6 difficulty curve, keeping the 3-fold trials it already
        paid for. Dropping or changing fold counts is still a different setup
        and still refused.
        """
        def without_folds(fp):
            return {k: v for k, v in fp.items() if k != "num_folds"}

        if without_folds(old_fp) != without_folds(new_fp):
            return False
        try:
            old = set(normalize_fold_counts(old_fp["num_folds"]))
            new = set(normalize_fold_counts(new_fp["num_folds"]))
        except (KeyError, TypeError, ValueError):
            return False
        return bool(old) and old < new   # strict subset: only additions

    def _load_or_init_results(self) -> dict:
        fingerprint = self._fingerprint()
        if self.results_path.exists():
            existing = json.loads(self.results_path.read_text())
            old_fp = existing.get("config_fingerprint")
            has_trials = any(m.get("trials")
                             for m in existing.get("models", {}).values())
            if old_fp is not None and old_fp != fingerprint:
                # Only refuse when there are real trials to protect - mixing
                # results from two setups would give a meaningless accuracy
                # number. A trial-less results.json is just a saved setup
                # (created by Save setup, or a Start that never got a trial
                # in), so a setup change simply replaces it.
                if has_trials and not self._is_fold_extension(old_fp, fingerprint):
                    raise ValueError(
                        f"'{self.run_name}' already has results with a different "
                        f"setup ({old_fp} vs {fingerprint}). Merging them would "
                        f"give a meaningless accuracy number. You can widen the "
                        f"fold range of a run (its recorded trials keep their own "
                        f"fold counts), but not narrow or shift it. Otherwise pick "
                        f"a different run name, or delete {self.run_dir} to start over."
                    )
                if has_trials:
                    LOG.info("Fold range widened to %s - keeping the trials already "
                             "recorded, only the added fold counts will run.",
                             self.fold_counts)
                    existing["config_fingerprint"] = fingerprint
                else:
                    LOG.info("Existing results have no trials - adopting the new setup.")
                    existing["config_fingerprint"] = fingerprint
                    existing["models"] = {}
            else:
                LOG.info("Found existing results - resuming (config matches).")
                existing.setdefault("config_fingerprint", fingerprint)
            # Keep current: on resume, num_trials may have grown - the stored
            # value would otherwise stay stale and mislead the plots.
            existing["num_trials"] = self.num_trials
            existing["num_folds"] = self.num_folds
            existing["fold_counts"] = list(self.fold_counts)
            existing["direction_mode"] = self.direction_mode
            return existing
        return {
            "experiment": self.run_name,
            "config_fingerprint": fingerprint,
            # num_trials is per fold count; fold_counts says which counts are
            # swept. num_folds is the lowest of them, kept as a plain int so
            # anything reading the old field still gets a sensible number.
            "num_trials": self.num_trials,
            "num_folds": self.num_folds,
            "fold_counts": list(self.fold_counts),
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
