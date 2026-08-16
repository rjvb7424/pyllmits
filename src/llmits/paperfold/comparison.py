"""
llmits.paperfold.comparison
===========================

Compares several paper-folding runs against each other.

``analysis.py`` answers "which model is best *inside* this run". This module
answers the other half of the experiment - "what did changing the prompt do" -
by putting whole runs side by side: real direction names against swapped ones,
against single-word placeholders, against twenty-word phrases, and so on.

Three things make that comparison honest rather than just convenient:

  * **Scope.** Two runs are only comparable over the models and fold counts
    they both actually have scored trials for. A run that stopped after five
    models, or one that swept 3-8 folds while the others sat at 3, would
    otherwise be compared through its own particular mixture. ``restrict=True``
    (the default) trims every run to the models and fold counts common to all
    of them and reports exactly what that dropped, so the trim is visible
    rather than silent.

  * **Breadth.** A run's average moving is not the same finding as every model
    moving. ``findings()`` separates the two: a shift the whole field shares is
    a fact about the prompt, and one carried by a single model is a fact about
    that model.

  * **Noise.** Forty trials per model is not many. Every accuracy difference is
    checked against a 95% confidence interval on the pooled trials before it is
    called a change at all, so "no measurable difference" is a result this page
    can actually report instead of reading small wobble as signal.

Plots are written to a comparison directory as ``<kind>.png``:

  * ``accuracy_by_experiment``      - the headline: one bar per run
  * ``tokens_by_experiment``        - what each run cost in tokens
  * ``time_by_experiment``          - and in wall-clock thinking time
  * ``accuracy_matrix``             - every model x every run, as a heatmap
  * ``accuracy_change_matrix``      - the same grid as change from the baseline
  * ``tokens_change_matrix``        - and the token cost of that change
  * ``model_slopes``                - one line per model across the runs
  * ``sensitivity_by_model``        - how much each model swung, ranked
  * ``accuracy_vs_tokens_by_experiment`` / ``..._vs_time_...``
                                    - did the extra spend buy anything
  * ``label_complexity``            - accuracy and tokens against how many words
                                      the direction names were given
  * ``accuracy_by_folds_by_experiment``
                                    - difficulty curves, one line per run
  * ``letter_bias_by_experiment``   - whether answers collapsed toward a letter

Styling deliberately matches ``llmits.paperfold.analysis`` (same muted gray
labels, same plain-language axis captions, same finishing pass) so a comparison
chart and a single-run chart read as one family.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from llmits.paperfold import analysis as ar

# The four orientations the puzzle actually folds in, and the wider vocabulary
# of spatial words a placeholder might smuggle back in. A twenty-word phrase
# that opens with "Southwest" is not a neutral label, and counting those hits
# is what tells that experiment apart from one built of nonsense nouns.
DIRECTIONS = ("north", "south", "east", "west")
SPATIAL_WORDS = frozenset(DIRECTIONS + (
    "northeast", "northwest", "southeast", "southwest",
    "up", "down", "left", "right", "top", "bottom",
    "upward", "downward", "upwards", "downwards",
    "above", "below", "vertical", "horizontal",
))

# One color per experiment, for every chart that draws runs side by side. The
# baseline keeps the neutral dark gray the single-run charts already use for
# "the number to compare against", so it reads as the reference wherever it
# appears rather than as one more colored condition.
BASELINE_COLOR = "#52514e"
EXPERIMENT_COLORS = ("#2a78d6", "#e8863c", "#3fb27f", "#a259c4",
                     "#d64550", "#00959c", "#9c7a2e", "#5c6bc0")

# Change colors: green where the measure moved the way you'd want it to, red
# where it moved the other way. Which way that is depends on the measure -
# more accuracy is good, more tokens is not - so both charts and findings go
# through Measure.higher_is_better rather than assuming "up is good".
BETTER_COLOR = "#2e8b57"
WORSE_COLOR = "#c0392b"
NEUTRAL_COLOR = "#9a9894"

LABEL_GRAY = ar.LABEL_GRAY
CHANCE = 20.0          # five candidates, so a coin-flipper lands here

PLOT_KINDS = (
    "accuracy_by_experiment", "tokens_by_experiment", "time_by_experiment",
    "accuracy_matrix", "accuracy_change_matrix", "tokens_change_matrix",
    "model_slopes", "sensitivity_by_model",
    "accuracy_vs_tokens_by_experiment", "accuracy_vs_time_by_experiment",
    "label_complexity", "accuracy_by_folds_by_experiment",
    "letter_bias_by_experiment",
)


# =============================================================================
#  Measures - the three things a run is compared on
# =============================================================================
@dataclass(frozen=True)
class Measure:
    """One comparable quantity, and everything needed to talk about it.

    ``higher_is_better`` is what keeps the rest of the module honest about
    direction: the same "+18%" is a result worth having on accuracy and a bill
    worth noticing on tokens, and every color, arrow and finding below decides
    which by asking here.
    """
    key: str
    label: str                      # "Accuracy"
    axis: str                       # full axis caption, plain language
    higher_is_better: bool
    of: Callable[[list[dict]], float]
    fmt: Callable[[float], str]
    delta_fmt: Callable[[float], str]
    unit: str                       # short suffix for the UI


MEASURES: dict[str, Measure] = {
    "accuracy": Measure(
        key="accuracy", label="Accuracy",
        axis="Accuracy (% of answers correct)",
        higher_is_better=True, of=ar.accuracy_of,
        fmt=lambda v: f"{v:.0f}%", delta_fmt=lambda d: f"{d:+.1f} pp", unit="%",
    ),
    "tokens": Measure(
        key="tokens", label="Token consumption",
        axis="Average token consumption (total tokens per trial)",
        higher_is_better=False, of=ar.field_average("total_tokens"),
        fmt=lambda v: f"{v:,.0f}", delta_fmt=lambda d: f"{d:+,.0f}", unit=" tok",
    ),
    "time": Measure(
        key="time", label="Response time",
        axis="Average response time (seconds per trial)",
        higher_is_better=False, of=ar.field_average("elapsed_seconds"),
        fmt=lambda v: f"{v:.1f}s", delta_fmt=lambda d: f"{d:+.1f}s", unit="s",
    ),
}
MEASURE_ORDER = ("accuracy", "tokens", "time")


# =============================================================================
#  Loading and scoping
# =============================================================================
def load_run(run_dir: Path) -> dict[str, Any]:
    """Read one run's results.json into {name, results, rows}, where rows is
    the flat per-trial view every aggregate below works from (scored trials
    only - an unanswered trial has no accuracy, no token count and no response
    time to contribute)."""
    results = json.loads((run_dir / "results.json").read_text())
    return {
        "name": run_dir.name,
        "results": results,
        "rows": ar.filter_scored(ar.flatten(results)),
    }


def models_of(rows) -> set[str]:
    """Models with at least one scored trial in these rows.

    Scored, not merely listed: a model that was added to a run and then errored
    out on every call still appears in results.json with an empty trial list,
    and treating it as present would shrink the common set to nothing.
    """
    return {r.get("model_version", "unknown") for r in rows}


def common_models(runs) -> list[str]:
    """Models every one of these runs has scored trials for, sorted."""
    if not runs:
        return []
    shared = set.intersection(*(models_of(r["rows"]) for r in runs))
    return sorted(shared)


def common_folds(runs) -> list[int]:
    """Fold counts every one of these runs has trials at, sorted.

    Comparing a 3-fold run against the 3-to-8 sweep on their raw averages
    compares "how hard is this wording" against "how hard is this wording plus
    five extra folds of difficulty". The overlap - here just 3 folds - is the
    only part of the two that answers the same question.
    """
    if not runs:
        return []
    shared = set.intersection(*(set(ar.fold_values(r["rows"])) for r in runs))
    return sorted(shared)


def scope_rows(rows, models: set[str] | None, folds: set[int] | None) -> list[dict]:
    """Trim rows to a set of models and fold counts.

    Trials recorded before fold counts were written into each result carry no
    ``num_folds``; they're kept rather than dropped, since there's nothing to
    place them at and dropping them would silently empty an old run.
    """
    out = []
    for r in rows:
        if models is not None and r.get("model_version", "unknown") not in models:
            continue
        if folds is not None and r.get("num_folds") is not None \
                and int(r["num_folds"]) not in folds:
            continue
        out.append(r)
    return out


# =============================================================================
#  What was actually changed between runs: the direction labels
# =============================================================================
def _label_texts(run) -> list[str]:
    """The words each direction was presented under in this run.

    Read from the trials themselves rather than from the config fingerprint, so
    "random placeholders" - which draws a fresh mapping every single trial and
    therefore has no single mapping to record - is measured the same way as
    every other mode. Only a sample is read: the interesting figure is how long
    and how spatial the labels are, and that doesn't drift across trials.
    """
    texts: list[str] = []
    for r in run["rows"][:200]:
        labels = r.get("direction_labels")
        if labels:
            texts.extend(str(v) for v in labels.values())
    if texts:
        return texts
    fingerprint = (run["results"].get("config_fingerprint") or {}).get("direction_labels")
    if fingerprint:
        return [str(v) for v in fingerprint.values()]
    return list(DIRECTIONS)      # "real" mode: the directions are their own labels


def label_profile(run) -> dict[str, Any]:
    """A description of *what this run changed* - the axis every finding about
    prompt wording is ultimately plotted against.

    Three numbers come out of it. ``words`` is how long the direction names
    were, which is the obvious dial. ``spatial_words`` is the subtler one: a
    placeholder phrase that itself contains "east" or "southwest" is not a
    neutral label but a contradicting one, and a run built from those is testing
    interference, not unfamiliarity. ``swapped`` catches the special case where
    the four real direction words were simply permuted among themselves.
    """
    mode = run["results"].get("direction_mode", "real")
    texts = _label_texts(run)
    tokens = [re.findall(r"[a-z]+", t.lower()) for t in texts]
    words = sum(len(t) for t in tokens) / len(tokens) if tokens else 1.0
    chars = sum(len(t) for t in texts) / len(texts) if texts else 0.0
    spatial = sum(1 for t in tokens for w in t if w in SPATIAL_WORDS) / (len(tokens) or 1)

    fingerprint = (run["results"].get("config_fingerprint") or {}).get("direction_labels") or {}
    swapped = bool(fingerprint) and all(
        str(v).strip().lower() in DIRECTIONS for v in fingerprint.values()
    ) and any(str(v).strip().lower() != k for k, v in fingerprint.items())

    if mode == "real":
        kind = "Real direction names"
    elif mode == "random":
        kind = "Random word per trial"
    elif swapped:
        kind = "Swapped real names"
    elif words < 1.5:
        kind = "Single-word placeholder"
    else:
        kind = f"{words:.0f}-word phrase"

    return {
        "mode": mode,
        "kind": kind,
        "words": round(words, 2),
        "chars": round(chars, 1),
        "spatial_words": round(spatial, 2),
        "swapped": swapped,
        "labels": fingerprint or None,
    }


# =============================================================================
#  Aggregation
# =============================================================================
def _per_model(rows, measure: Measure) -> dict[str, float]:
    return {m: v for m, v, _ in ar.model_values(rows, measure.of)}


def _trials_per_model(rows) -> dict[str, int]:
    counts: Counter = Counter()
    for r in rows:
        counts[r.get("model_version", "unknown")] += 1
    return dict(counts)


def _pooled_accuracy_ci(rows) -> float:
    """Half-width of a 95% confidence interval on this run's pooled accuracy.

    Deliberately the crudest defensible yardstick - a normal approximation on
    the pooled trials - because its job is only to keep small differences from
    being read as findings. Trials within a run aren't fully independent (the
    same models answer all of them), so this understates the real uncertainty
    if anything, which is the safe direction for a check that gates claims.
    """
    n = len(rows)
    if n < 2:
        return 100.0
    p = sum(1 for r in rows if r["is_correct"]) / n
    return 100 * 1.96 * math.sqrt(max(p * (1 - p), 1e-6) / n)


def _letter_profile(rows) -> dict[str, Any]:
    """How the answers were spread across the five letters, against how the
    correct answers were. A predicted distribution far more lopsided than the
    correct one is positional bias - picking a favourite letter - which is what
    a model that has stopped reasoning tends to fall back on."""
    predicted = Counter(r["predicted_choice"] for r in rows)
    correct = Counter(r["correct_choice"] for r in rows)
    n = len(rows) or 1
    pred_share = {l: predicted.get(l, 0) / n for l in ar.LETTERS}
    top = max(pred_share, key=lambda l: pred_share[l]) if rows else "-"
    return {
        "predicted": {l: round(100 * pred_share[l], 1) for l in ar.LETTERS},
        "correct": {l: round(100 * correct.get(l, 0) / n, 1) for l in ar.LETTERS},
        "top_letter": top,
        "top_share": round(100 * pred_share.get(top, 0), 1),
        # Total variation from a flat 20%-each spread: 0 means perfectly even,
        # 80 means every answer went to one letter.
        "skew": round(100 * sum(abs(pred_share[l] - 0.2) for l in ar.LETTERS) / 2, 1),
    }


def summarise_run(run, rows) -> dict[str, Any]:
    """Everything the comparison page shows about one run, over the rows left
    after scoping."""
    per_model = {key: _per_model(rows, MEASURES[key]) for key in MEASURE_ORDER}
    trials = _trials_per_model(rows)
    models = sorted(trials)

    metrics = {}
    for key in MEASURE_ORDER:
        values = list(per_model[key].values())
        metrics[key] = {
            # The average of the model bars, not of the pooled trials - one
            # model running twice as long as another shouldn't get twice the
            # vote in what the whole run scored (see analysis.macro_average).
            "value": ar.macro_average(values),
            "pooled": MEASURES[key].of(rows),
            "min": min(values) if values else 0.0,
            "max": max(values) if values else 0.0,
            "spread": (max(values) - min(values)) if values else 0.0,
        }

    return {
        "name": run["name"],
        "display": ar.display_name(run["name"]),
        "label": label_profile(run),
        "models": models,
        # Which provider each model came from, so the charts can color models
        # by provider family exactly as the single-run charts do (the backend
        # is recorded per model, not per trial - see analysis.flatten).
        "backends": {m: b for m, b in
                     ((r.get("model_version"), r.get("backend")) for r in rows)
                     if m in trials},
        "model_count": len(models),
        "trials": len(rows),
        "trials_per_model": trials,
        "fold_counts": ar.fold_values(rows),
        "metrics": metrics,
        "per_model": {m: {key: per_model[key].get(m) for key in MEASURE_ORDER}
                      | {"trials": trials.get(m, 0)}
                      for m in models},
        "accuracy_ci": _pooled_accuracy_ci(rows),
        "letters": _letter_profile(rows),
        "created": run["results"].get("created"),
        "updated": run["results"].get("updated"),
    }


def build_summary(runs, baseline: str | None = None, restrict: bool = True) -> dict[str, Any]:
    """The whole comparison, as one JSON-safe structure.

    ``runs`` arrives in the order the comparison should read; ``baseline`` names
    the run everything else is measured against (defaults to the first).
    """
    if not runs:
        return {"ok": False, "error": "pick at least one run to compare"}

    names = [r["name"] for r in runs]
    baseline = baseline if baseline in names else names[0]

    shared_models = common_models(runs)
    shared_folds = common_folds(runs)
    model_scope = set(shared_models) if restrict else None
    fold_scope = set(shared_folds) if restrict else None

    scoped = {r["name"]: scope_rows(r["rows"], model_scope, fold_scope) for r in runs}
    empty = [n for n, rows in scoped.items() if not rows]
    if empty:
        return {"ok": False, "error":
                "no comparable trials left for " + ", ".join(empty) +
                (" - these runs share no model (or no fold count) with the rest of "
                 "the selection. Turn off \"compare like for like\" to see each run "
                 "on its own terms instead." if restrict else
                 " - that run has no scored trials yet.")}

    summaries = [summarise_run(r, scoped[r["name"]]) for r in runs]
    by_name = {s["name"]: s for s in summaries}

    dropped_models = sorted(
        set.union(*(models_of(r["rows"]) for r in runs)) - set(shared_models))
    dropped_folds = {r["name"]: [f for f in ar.fold_values(r["rows"])
                                 if f not in shared_folds] for r in runs}

    # Model rows for the matrix: ranked by how they did on the baseline, best
    # first, so reading down the column is reading a leaderboard and any run
    # that reorders it is visibly doing so.
    base = by_name[baseline]
    model_union = sorted(set().union(*(set(s["models"]) for s in summaries)))
    model_order = sorted(
        model_union,
        key=lambda m: (-(base["per_model"].get(m, {}).get("accuracy") or -1), m))

    return {
        "ok": True,
        "baseline": baseline,
        "restricted": restrict,
        "runs": summaries,
        "models": model_order,
        "measures": [{"key": k, "label": MEASURES[k].label, "axis": MEASURES[k].axis,
                      "unit": MEASURES[k].unit,
                      "higher_is_better": MEASURES[k].higher_is_better}
                     for k in MEASURE_ORDER],
        "scope": {
            "models_used": shared_models if restrict else model_union,
            "models_dropped": dropped_models if restrict else [],
            "folds_used": shared_folds if restrict else
                          sorted(set().union(*(set(s["fold_counts"]) for s in summaries))),
            "folds_dropped": {n: f for n, f in dropped_folds.items() if f and restrict},
        },
        "findings": findings(summaries, baseline),
    }


# =============================================================================
#  Findings - the patterns, stated in words
# =============================================================================
def _delta(summary, base, key: str) -> float:
    return summary["metrics"][key]["value"] - base["metrics"][key]["value"]


def _pct_change(summary, base, key: str) -> float:
    before = base["metrics"][key]["value"]
    if not before:
        return 0.0
    return 100 * (summary["metrics"][key]["value"] - before) / before


def _distinguishable(summary, base) -> bool:
    """Whether an accuracy difference is bigger than the two runs' combined
    95% interval - i.e. whether it is worth calling a difference at all."""
    margin = math.hypot(summary["accuracy_ci"], base["accuracy_ci"])
    return abs(_delta(summary, base, "accuracy")) > margin


def _spearman(a: list[float], b: list[float]) -> float:
    """Rank correlation between two orderings of the same models. 1.0 means a
    run reordered nobody, 0 means the leaderboard was reshuffled at random."""
    if len(a) < 3:
        return float("nan")

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):          # average the ranks of tied values
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return out

    ra, rb = np.array(ranks(a)), np.array(ranks(b))
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) < 3:
        return float("nan")
    ax, ay = np.array(x, dtype=float), np.array(y, dtype=float)
    if ax.std() == 0 or ay.std() == 0:
        return float("nan")
    return float(np.corrcoef(ax, ay)[0, 1])


def _shared_models(summary, base) -> list[str]:
    return [m for m in summary["models"] if m in base["per_model"]]


def findings(summaries, baseline: str) -> list[dict[str, str]]:
    """Plain-language readings of the comparison, most load-bearing first.

    Each one is a claim the numbers support on their own terms, with the
    hedging kept in rather than rounded away: how many models moved, whether the
    move clears the noise floor, and whether it was the field or one model.
    ``kind`` is only a color for the UI - "good"/"bad" are about the direction
    the measure moved, never about whether the finding matters.
    """
    by_name = {s["name"]: s for s in summaries}
    base = by_name[baseline]
    others = [s for s in summaries if s["name"] != baseline]
    out: list[dict[str, str]] = []

    if not others:
        return [{"kind": "note", "title": "Only one run selected",
                 "text": "Add a second run to compare it against "
                         f"{base['display']}."}]

    # -- 1. the headline per run, with breadth and the noise check ------------
    for s in others:
        shared = _shared_models(s, base)
        moved = [(m, (s["per_model"][m]["accuracy"] or 0)
                  - (base["per_model"][m]["accuracy"] or 0)) for m in shared]
        worse = [m for m, d in moved if d < 0]
        better = [m for m, d in moved if d > 0]
        d_acc = _delta(s, base, "accuracy")
        real = _distinguishable(s, base)

        direction = "lower" if d_acc < 0 else "higher"
        if not real:
            kind, verdict = "note", (
                "within the margin of these trial counts, so this is best read "
                "as no measurable change in accuracy")
        else:
            kind = "bad" if d_acc < 0 else "good"
            verdict = f"{abs(d_acc):.1f} points {direction} than {base['display']}"

        tied = len(shared) - len(worse) - len(better)
        breadth = (f"{len(worse)} of {len(shared)} models scored lower, "
                   f"{len(better)} scored higher" +
                   (f", {tied} landed on exactly the same score" if tied else ""))
        cost = (f"tokens {_pct_change(s, base, 'tokens'):+.0f}%, "
                f"response time {_pct_change(s, base, 'time'):+.0f}%")
        out.append({
            "kind": kind, "run": s["name"],
            "title": f"{s['display']}: {MEASURES['accuracy'].fmt(s['metrics']['accuracy']['value'])}"
                     f" ({_delta_text(d_acc, 'accuracy')})",
            "text": f"{verdict}. {breadth}. Cost of the change: {cost}.",
        })

    # -- 2. was it the field, or one model? ----------------------------------
    for s in others:
        shared = _shared_models(s, base)
        if len(shared) < 3:
            continue
        deltas = {m: (s["per_model"][m]["accuracy"] or 0)
                     - (base["per_model"][m]["accuracy"] or 0) for m in shared}
        total = sum(deltas.values())
        if abs(total / len(shared)) < 1e-9:
            continue
        biggest = max(deltas, key=lambda m: abs(deltas[m]))
        without = (total - deltas[biggest]) / (len(shared) - 1)
        overall = total / len(shared)
        if abs(overall) > 1 and (abs(without) < 0.4 * abs(overall) or
                                 (without * overall) < 0):
            out.append({
                "kind": "warn", "run": s["name"],
                "title": f"{s['display']}'s shift is mostly one model",
                "text": f"Drop {biggest} and the average change goes from "
                        f"{overall:+.1f} to {without:+.1f} points. That is a fact "
                        f"about {biggest}, not about the wording.",
            })
        elif len(shared) >= 4 and all(d < 0 for d in deltas.values()):
            out.append({
                "kind": "bad", "run": s["name"],
                "title": f"Every model scored lower on {s['display']}",
                "text": f"All {len(shared)} models dropped, by "
                        f"{min(-d for d in deltas.values()):.0f} to "
                        f"{max(-d for d in deltas.values()):.0f} points. A shift "
                        f"the whole field shares is a fact about the wording.",
            })
        elif len(shared) >= 4 and all(d > 0 for d in deltas.values()):
            out.append({
                "kind": "good", "run": s["name"],
                "title": f"Every model scored higher on {s['display']}",
                "text": f"All {len(shared)} models improved, by "
                        f"{min(deltas.values()):.0f} to {max(deltas.values()):.0f} "
                        f"points.",
            })

    # -- 3. paid more, got nothing -------------------------------------------
    for s in others:
        if _distinguishable(s, base):
            continue
        tok, sec = _pct_change(s, base, "tokens"), _pct_change(s, base, "time")
        if max(tok, sec) >= 15:
            out.append({
                "kind": "warn", "run": s["name"],
                "title": f"{s['display']} cost more for the same score",
                "text": f"Accuracy is unchanged within the margin, but tokens are "
                        f"{tok:+.0f}% and response time {sec:+.0f}%. The models were "
                        f"not unbothered by this wording - they worked harder to "
                        f"land in the same place.",
            })

    # -- 4. which models care about the wording at all -----------------------
    everywhere = [m for m in base["per_model"]
                  if all(m in s["per_model"] for s in summaries)]
    if len(summaries) >= 2 and everywhere:
        spreads = {m: max(s["per_model"][m]["accuracy"] for s in summaries)
                      - min(s["per_model"][m]["accuracy"] for s in summaries)
                   for m in everywhere}
        loudest = max(spreads, key=lambda m: spreads[m])
        quietest = min(spreads, key=lambda m: spreads[m])
        out.append({
            "kind": "note",
            "title": "Most and least sensitive to the wording",
            "text": f"{loudest} swings {spreads[loudest]:.0f} points across these "
                    f"{len(summaries)} runs; {quietest} moves only "
                    f"{spreads[quietest]:.0f}. A model whose score barely moves when "
                    f"the direction names do is the one behaving as though it reads "
                    f"the geometry.",
        })

    # -- 5. did the leaderboard survive? -------------------------------------
    for s in others:
        shared = _shared_models(s, base)
        rho = _spearman([base["per_model"][m]["accuracy"] for m in shared],
                        [s["per_model"][m]["accuracy"] for m in shared])
        if math.isnan(rho):
            continue
        if rho < 0.5:
            out.append({
                "kind": "warn", "run": s["name"],
                "title": f"{s['display']} reorders which model is best",
                "text": f"Rank correlation with {base['display']} is only {rho:.2f}. "
                        f"The models that handle this wording are not the same ones "
                        f"that handled the baseline, so a single ranking does not "
                        f"carry across the two.",
            })

    # -- 6. does label length itself explain anything? -----------------------
    words = [s["label"]["words"] for s in summaries]
    if len({round(w, 1) for w in words}) >= 3:
        acc = [s["metrics"]["accuracy"]["value"] for s in summaries]
        tok = [s["metrics"]["tokens"]["value"] for s in summaries]
        r_acc, r_tok = _pearson(words, acc), _pearson(words, tok)
        parts = []
        if not math.isnan(r_acc):
            parts.append(f"accuracy r = {r_acc:+.2f}")
        if not math.isnan(r_tok):
            parts.append(f"tokens r = {r_tok:+.2f}")
        if parts:
            out.append({
                "kind": "note",
                "title": "Label length against the measures",
                "text": f"Across {len(summaries)} runs with direction names from "
                        f"{min(words):.0f} to {max(words):.0f} words: " +
                        ", ".join(parts) + ". With this few runs a correlation is a "
                        f"hint at a direction to test, not a result.",
            })

    # -- 7. answers collapsing onto one letter -------------------------------
    for s in summaries:
        skew, top = s["letters"]["skew"], s["letters"]["top_letter"]
        if skew >= 25:
            out.append({
                "kind": "warn", "run": s["name"],
                "title": f"{s['display']} leans on one answer letter",
                "text": f"{s['letters']['top_share']:.0f}% of answers went to "
                        f"{top} (an even spread would be 20%). Picking a favourite "
                        f"letter is what guessing looks like from the outside.",
            })

    # -- 8. how much trial data is behind all this ---------------------------
    trials = sorted(s["trials"] for s in summaries)
    out.append({
        "kind": "note",
        "title": "What these numbers rest on",
        "text": f"{trials[0]:,}-{trials[-1]:,} scored trials per run. The 95% margin "
                f"on a run's accuracy is about "
                f"±{max(s['accuracy_ci'] for s in summaries):.1f} points, so "
                f"differences smaller than that are noise, not findings."
                if trials[0] != trials[-1] else
                f"{trials[0]:,} scored trials per run, with a 95% margin of about "
                f"±{max(s['accuracy_ci'] for s in summaries):.1f} points on each "
                f"run's accuracy. Differences smaller than that are noise.",
    })
    return out


def _delta_text(delta: float, key: str) -> str:
    return "no change" if abs(delta) < 0.05 else MEASURES[key].delta_fmt(delta)


# =============================================================================
#  Plots
# =============================================================================
def experiment_colors(summaries, baseline: str) -> dict[str, Any]:
    """One color per run, with the baseline held out in neutral gray."""
    colors, i = {}, 0
    for s in summaries:
        if s["name"] == baseline:
            colors[s["name"]] = BASELINE_COLOR
        else:
            colors[s["name"]] = EXPERIMENT_COLORS[i % len(EXPERIMENT_COLORS)]
            i += 1
    return colors


def model_colors(summary) -> dict[str, Any]:
    """One color per model, in the same provider families the single-run charts
    use - so a model is the same shade of blue whichever page it appears on."""
    backends: dict[str, str | None] = {}
    for s in summary["runs"]:
        for model, backend in (s.get("backends") or {}).items():
            backends.setdefault(model, backend)
    return ar.model_color_map([{"model_version": m, "backend": b}
                               for m, b in backends.items()])


def _tick(name: str, width: int = 16) -> str:
    """A run name as an axis tick: spaces for underscores, wrapped so long
    experiment names stay readable instead of overlapping their neighbours."""
    return textwrap.fill(ar.display_name(name), width)


def _change_color(delta: float, measure: Measure) -> str:
    if abs(delta) < 1e-9:
        return NEUTRAL_COLOR
    good = (delta > 0) == measure.higher_is_better
    return BETTER_COLOR if good else WORSE_COLOR


def _stagger(points, xspan: float, yspan: float, steps=(10, -26, 36, -52, 62, -78)):
    """Vertical offsets (in points) for a set of labelled markers, so labels
    that would land on top of each other step out of each other's way instead.

    Runs cluster hard on these charts - five wordings of the same puzzle tend to
    score within a few points of each other - so the default "label just above
    the marker" writes five captions into the same inch of canvas. Each point
    takes the first offset no near neighbour has already claimed.
    """
    placed: list[tuple[float, float, int]] = []
    offsets = []
    for x, y in points:
        taken = {level for px, py, level in placed
                 if abs(x - px) < 0.30 * (xspan or 1) and abs(y - py) < 0.10 * (yspan or 1)}
        level = next(i for i in range(len(steps) + len(points)) if i not in taken)
        placed.append((x, y, level))
        offsets.append(steps[level % len(steps)])
    return offsets


def _subtitle(ax, text: str) -> None:
    ax.annotate(text, xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=9, color=LABEL_GRAY)


def _scope_note(summary) -> str:
    """One line saying what every chart in this comparison was computed over -
    repeated on each figure so a downloaded PNG carries its own caveat instead
    of depending on the page it was downloaded from."""
    scope = summary["scope"]
    models = len(scope["models_used"])
    folds = scope["folds_used"]
    fold_text = ("any fold count" if not folds else
                 f"{folds[0]} folds" if len(folds) == 1 else
                 f"{folds[0]}-{folds[-1]} folds")
    if summary["restricted"]:
        return (f"Like for like: the {models} models and {fold_text} all "
                f"{len(summary['runs'])} runs have in common")
    return f"Every run on its own models and fold counts ({models} models seen in total)"


def plot_metric_by_experiment(summary, out: Path, key: str) -> None:
    """The headline chart for one measure: one bar per run, with the spread it
    hides drawn through it and the change from the baseline printed underneath.

    This is the chart the whole page exists to produce - two wordings, two bars,
    and the gap between them is the finding. The range line matters as much as
    the bar: an average that fell because every model fell is a result about the
    prompt, and one that fell because a single model collapsed is not.
    """
    measure = MEASURES[key]
    runs, baseline = summary["runs"], summary["baseline"]
    base = next(s for s in runs if s["name"] == baseline)
    colors = experiment_colors(runs, baseline)

    values = [s["metrics"][key]["value"] for s in runs]
    lows = [s["metrics"][key]["min"] for s in runs]
    highs = [s["metrics"][key]["max"] for s in runs]
    xs = list(range(len(runs)))

    # One thinking model can spend three times what the rest of the field does,
    # and an axis stretched to reach its whisker leaves every bar the same
    # squashed height - which defeats a chart whose whole job is the difference
    # between the bars. Past twice the tallest bar the axis is cut to the bars
    # and the whiskers that run off the top are labelled with where they got to,
    # so nothing is hidden, only moved out of the way.
    tallest_bar, tallest_whisker = max(values), max(highs)
    clipped = key != "accuracy" and tallest_whisker > 2 * tallest_bar
    top = (118 if key == "accuracy" else
           1.45 * tallest_bar if clipped else 1.3 * (tallest_whisker or 1.0))
    headroom = 0.02 * top

    fig, ax = plt.subplots(figsize=(max(6.5, 1.9 * len(runs) + 2.5), 6.2))
    ax.bar(xs, values, width=0.62, color=[colors[s["name"]] for s in runs], zorder=2)
    ax.errorbar(xs, values,
                yerr=[[v - lo for v, lo in zip(values, lows)],
                      [hi - v for v, hi in zip(values, highs)]],
                fmt="none", ecolor="#52514e", elinewidth=1, capsize=5, zorder=4,
                label="Lowest to highest model")

    # Where the axis was cut, the labels sit over the whiskers running past them,
    # so they get a plain background to stay legible against the line.
    plate = dict(facecolor="white", edgecolor="none", pad=1.6) if clipped else None
    for x, s, value, high in zip(xs, runs, values, highs):
        anchor = min(high, top * 0.78) if clipped else high
        if clipped and high > top:
            ax.annotate(f"↑ {measure.fmt(high)}", (x, top * 0.985),
                        ha="center", va="top", fontsize=8.5, color="#7a7874",
                        zorder=5, bbox=plate)
        ax.text(x, anchor + headroom, measure.fmt(value), ha="center", va="bottom",
                fontsize=10.5, color="#52514e", zorder=5, bbox=plate,
                fontweight="bold" if s["name"] == baseline else "normal")
        if s["name"] != baseline:
            delta = value - base["metrics"][key]["value"]
            ax.text(x, anchor + headroom + 0.060 * top,
                    _delta_text(delta, key), ha="center", va="bottom", fontsize=9.5,
                    color=_change_color(delta, measure), fontweight="bold",
                    zorder=5, bbox=plate)

    ax.axhline(base["metrics"][key]["value"], linestyle=(0, (6, 3)), linewidth=1.2,
               color=BASELINE_COLOR, zorder=1,
               label=f"{base['display']} (baseline)")
    if key == "accuracy":
        ax.axhline(CHANCE, linestyle="--", linewidth=1, color="#898781",
                   label=f"Chance ({CHANCE:.0f}%)")

    ax.set_xticks(xs)
    ax.set_xticklabels([_tick(s["name"]) for s in runs], fontsize=9)
    ax.set_xlabel("Experiment (one paper-folding run each)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel(measure.axis, color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"{measure.label} across {len(runs)} experiments", fontsize=13, pad=30)
    _subtitle(ax, f"Each bar = mean of that run's model bars  |  {_scope_note(summary)}" +
                  ("  |  axis cut to the bars; arrows mark where the priciest model reached"
                   if clipped else ""))
    ax.set_ylim(0, top)
    ax.margins(x=0.08)
    ax.grid(True, axis="y", alpha=0.3)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=9, loc="upper center",
               bbox_to_anchor=(0.5, 0.0), ncol=3, frameon=False)
    ar._finish(fig, ax, out, rotate_xticks=False)


def _matrix(summary, key: str, relative_to: str | None = None):
    """The models x runs grid behind every heatmap: absolute values, or the
    change from a baseline run when ``relative_to`` names one."""
    runs = summary["runs"]
    models = [m for m in summary["models"]
              if any(m in s["per_model"] for s in runs)]
    grid = np.full((len(models), len(runs)), np.nan)
    base = next((x for x in runs if x["name"] == relative_to), None)
    for j, s in enumerate(runs):
        for i, m in enumerate(models):
            value = s["per_model"].get(m, {}).get(key)
            if value is None:
                continue
            if base is None:
                grid[i, j] = value
            else:
                before = base["per_model"].get(m, {}).get(key)
                if before is None:
                    continue
                if key == "accuracy":
                    grid[i, j] = value - before           # percentage points
                else:
                    grid[i, j] = 100 * (value - before) / before if before else np.nan
    return models, grid


def _draw_matrix(summary, out: Path, *, key: str, relative: bool, title: str,
                 subtitle: str, cbar_label: str, fmt) -> None:
    """One heatmap of models against runs.

    A grid, not a wall of grouped bars: seventeen models across five runs is
    eighty-five numbers, and at that size a reader is looking for the shape -
    which row went dark, which column did - long before any single value. The
    numbers are printed in the cells anyway so nothing is only readable as a
    color.
    """
    measure = MEASURES[key]
    runs = summary["runs"]
    baseline = summary["baseline"]
    models, grid = _matrix(summary, key, baseline if relative else None)
    if not models or not runs:
        return

    saturated = None
    if relative:
        # One model can spend four times what it did on the baseline while the
        # rest of the field moves by single digits, and a scale stretched to
        # reach that outlier washes every other cell to the same neutral shade -
        # so the color runs out at the 90th percentile of the changes and
        # anything past it saturates. The numbers are printed in the cells
        # regardless, so the outlier is still readable, just no longer setting
        # the contrast for everybody else. The baseline's own column is left out
        # of that calculation: it is zeros by construction.
        others = np.delete(grid, [j for j, s in enumerate(runs)
                                  if s["name"] == baseline], axis=1)
        magnitudes = np.abs(others[~np.isnan(others)])
        biggest = float(magnitudes.max()) if magnitudes.size else 1.0
        limit = float(np.percentile(magnitudes, 90)) if magnitudes.size else 1.0
        limit = limit or biggest or 1.0
        if biggest > 1.05 * limit:
            saturated = limit
        cmap = plt.get_cmap("RdYlGn" if measure.higher_is_better else "RdYlGn_r")
        norm = matplotlib.colors.TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)
    elif key == "accuracy":
        cmap, norm = plt.get_cmap("RdYlGn"), matplotlib.colors.Normalize(0, 100)
    else:
        cmap = plt.get_cmap("YlOrBr")
        norm = matplotlib.colors.Normalize(float(np.nanmin(grid)), float(np.nanmax(grid)))

    fig, ax = plt.subplots(figsize=(max(7.0, 1.9 * len(runs) + 4.2),
                                    max(4.5, 0.42 * len(models) + 2.6)))
    image = ax.imshow(grid, aspect="auto", cmap=cmap, norm=norm)
    ax.set_xticks(range(len(runs)))
    ax.set_xticklabels([_tick(s["name"], 14) for s in runs], fontsize=8.5)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models, fontsize=9)
    ax.set_xlabel("Experiment (one paper-folding run each)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Model (ranked by the baseline run)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(title, fontsize=13, pad=30)
    _subtitle(ax, subtitle + (f"  |  color runs out at {fmt(saturated)}; bigger changes "
                              f"share the end shade" if saturated else ""))

    for i in range(len(models)):
        for j in range(len(runs)):
            value = grid[i, j]
            if np.isnan(value):
                ax.text(j, i, "-", ha="center", va="center", fontsize=8, color="#9a9894")
                continue
            # White text on dark cells, near-black on light ones, decided from
            # the cell's own luminance rather than from a threshold on the value
            # (which breaks the moment the color scale changes).
            r, g, b, _ = cmap(norm(value))
            dark = (0.299 * r + 0.587 * g + 0.114 * b) < 0.55
            ax.text(j, i, fmt(value), ha="center", va="center", fontsize=8.5,
                    color="#ffffff" if dark else "#1a1a1a")
    ax.set_xticks(np.arange(-0.5, len(runs), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(models), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.4)
    ax.tick_params(which="minor", length=0)
    fig.colorbar(image, ax=ax, shrink=0.75, pad=0.02,
                 extend="both" if saturated else "neither").set_label(
        cbar_label, color=LABEL_GRAY, fontsize=9)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_accuracy_matrix(summary, out: Path) -> None:
    _draw_matrix(summary, out, key="accuracy", relative=False,
                 title="Accuracy of every model in every experiment",
                 subtitle=f"Percent of answers correct  |  {_scope_note(summary)}",
                 cbar_label="Accuracy (%)", fmt=lambda v: f"{v:.0f}")


def plot_accuracy_change_matrix(summary, out: Path) -> None:
    base = next(s for s in summary["runs"] if s["name"] == summary["baseline"])
    _draw_matrix(summary, out, key="accuracy", relative=True,
                 title=f"Accuracy change from {base['display']}, per model",
                 subtitle="Percentage points gained (green) or lost (red) against the "
                          f"baseline column  |  {_scope_note(summary)}",
                 cbar_label="Change (percentage points)",
                 fmt=lambda v: f"{v:+.0f}")


def plot_tokens_change_matrix(summary, out: Path) -> None:
    base = next(s for s in summary["runs"] if s["name"] == summary["baseline"])
    _draw_matrix(summary, out, key="tokens", relative=True,
                 title=f"Token consumption change from {base['display']}, per model",
                 subtitle="Percent more (red) or fewer (green) tokens per trial than the "
                          f"baseline column  |  {_scope_note(summary)}",
                 cbar_label="Change (%)", fmt=lambda v: f"{v:+.0f}%")


def plot_model_slopes(summary, out: Path) -> None:
    """One line per model, walking left to right across the experiments.

    The heatmap says how much each cell moved; this says whether the models
    moved *together*. A bundle of near-parallel lines means the wording did the
    same thing to everyone, which is a property of the prompt. Lines that cross
    mean the wording suits some models and not others, which is a property of
    the models - and the two call for completely different follow-ups.
    """
    runs = summary["runs"]
    models = summary["models"]
    colors = model_colors(summary)
    xs = list(range(len(runs)))

    fig, ax = plt.subplots(figsize=(max(8.0, 2.1 * len(runs) + 3.0), 7.0))
    for i, m in enumerate(models):
        ys = [s["per_model"].get(m, {}).get("accuracy") for s in runs]
        points = [(x, y) for x, y in zip(xs, ys) if y is not None]
        if len(points) < 2:
            continue
        ax.plot([p[0] for p in points], [p[1] for p in points],
                marker=ar.MARKERS[i % len(ar.MARKERS)], markersize=5, linewidth=1.6,
                color=colors[m], alpha=0.9, label=m, zorder=3)

    averages = [s["metrics"]["accuracy"]["value"] for s in runs]
    ax.plot(xs, averages, linewidth=3.0, color=BASELINE_COLOR, alpha=0.9,
            marker="o", markersize=7, zorder=4, label="Average of all models")
    ax.axhline(CHANCE, linestyle="--", linewidth=1, color="#898781",
               label=f"Chance ({CHANCE:.0f}%)")

    ax.set_xticks(xs)
    ax.set_xticklabels([_tick(s["name"]) for s in runs], fontsize=9)
    ax.set_xlabel("Experiment (one paper-folding run each)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel(MEASURES["accuracy"].axis, color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"How each model moved across {len(runs)} experiments", fontsize=13, pad=30)
    _subtitle(ax, "Parallel lines = the wording did the same thing to every model  |  "
                  f"crossing lines = it did not  |  {_scope_note(summary)}")
    ax.set_ylim(-5, 110)
    ax.margins(x=0.06)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    ar._finish(fig, ax, out, rotate_xticks=False)


def plot_sensitivity_by_model(summary, out: Path) -> None:
    """How far each model's accuracy swung across the whole selection, ranked.

    The single most useful ranking this page produces. A model at the top of it
    scored very differently depending only on what the four directions were
    called - the puzzle underneath never changed - which is the clearest sign
    available that its answer was leaning on the words. A model at the bottom
    held the same score throughout, which is what reading the geometry looks
    like.
    """
    runs = summary["runs"]
    rows = []
    for m in summary["models"]:
        values = [s["per_model"][m]["accuracy"] for s in runs if m in s["per_model"]]
        if len(values) < 2:
            continue
        rows.append((m, max(values) - min(values), min(values), max(values), len(values)))
    if not rows:
        return
    rows.sort(key=lambda r: r[1])
    colors = experiment_colors(runs, summary["baseline"])

    fig, ax = plt.subplots(figsize=(9.5, max(4.0, 0.55 * len(rows) + 2.2)))
    ys = list(range(len(rows)))
    for y, (m, spread, low, high, _) in zip(ys, rows):
        ax.plot([low, high], [y, y], color="#c9c6c0", linewidth=6,
                solid_capstyle="round", zorder=1)
    for s in runs:
        color = colors[s["name"]]
        xs = [s["per_model"][m]["accuracy"] for m, *_ in rows if m in s["per_model"]]
        ys_here = [y for y, (m, *_) in zip(ys, rows) if m in s["per_model"]]
        ax.scatter(xs, ys_here, s=46, color=color, zorder=3, edgecolors="white",
                   linewidths=0.8, label=ar.display_name(s["name"]))
    for y, (m, spread, low, high, _) in zip(ys, rows):
        ax.text(high + 4, y, f"{spread:.0f} pp", va="center", fontsize=9, color="#52514e")

    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=9)
    ax.axvline(CHANCE, linestyle="--", linewidth=1, color="#898781",
               label=f"Chance ({CHANCE:.0f}%)")
    ax.set_xlabel(MEASURES["accuracy"].axis, color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Model (least wording-sensitive at the bottom)", color=LABEL_GRAY, fontsize=10)
    ax.set_title("How much each model's score depends on the wording", fontsize=13, pad=30)
    _subtitle(ax, "Bar = that model's lowest to highest score across the selected runs; "
                  f"the number is the swing  |  {_scope_note(summary)}")
    ax.set_xlim(0, 124)
    ax.grid(True, axis="x", alpha=0.3)
    # Below the figure, not beside it: a run legend is as wide as the run names
    # are long, and beside a chart this tall it either crushes the plot or lands
    # on top of the dots it is labelling.
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=8.5, loc="upper center",
               bbox_to_anchor=(0.5, 0.0), ncol=2, frameon=False)
    ar._finish(fig, ax, out, rotate_xticks=False)


def plot_accuracy_vs_cost(summary, out: Path, key: str) -> None:
    """Accuracy against what a run cost, one marker per experiment, with an
    arrow drawn from the baseline to each of the others.

    The arrow is the point. Straight up is a wording that bought accuracy;
    straight right is one that only bought a bill; down and to the right - which
    is what heavier prompts usually produce - is the worst outcome available and
    the easiest one to miss when accuracy is read on its own.
    """
    measure = MEASURES[key]
    runs, baseline = summary["runs"], summary["baseline"]
    base = next(s for s in runs if s["name"] == baseline)
    colors = experiment_colors(runs, baseline)

    fig, ax = plt.subplots(figsize=(11.5, 7.5))
    bx = base["metrics"][key]["value"]
    by = base["metrics"]["accuracy"]["value"]
    points = [(s["metrics"][key]["value"], s["metrics"]["accuracy"]["value"]) for s in runs]
    xs = [p[0] for p in points]
    offsets = _stagger(points, max(xs) - min(xs), 30.0)
    for s, (x, y), dy in zip(runs, points, offsets):
        if s["name"] != baseline:
            ax.annotate("", xy=(x, y), xytext=(bx, by),
                        arrowprops=dict(arrowstyle="->", color=colors[s["name"]],
                                        alpha=0.45, linewidth=1.6,
                                        shrinkA=9, shrinkB=9), zorder=2)
        ax.scatter(x, y, s=340 if s["name"] == baseline else 260,
                   color=colors[s["name"]], alpha=0.9, edgecolors="white",
                   linewidths=1.5, zorder=3,
                   marker="D" if s["name"] == baseline else "o")
        ax.annotate(f"{_tick(s['name'], 26)}\n"
                    f"{MEASURES['accuracy'].fmt(y)}, {measure.fmt(x)}",
                    (x, y), textcoords="offset points", xytext=(12, dy),
                    fontsize=8.5, color="#52514e", zorder=5)

    ax.axhline(by, linestyle=(0, (6, 3)), linewidth=1, color=BASELINE_COLOR,
               alpha=0.7, label=f"{base['display']} accuracy (baseline)")
    ax.axvline(bx, linestyle=(0, (6, 3)), linewidth=1, color=BASELINE_COLOR, alpha=0.7)
    ax.axhline(CHANCE, linestyle="--", linewidth=1, color="#898781",
               label=f"Chance ({CHANCE:.0f}%)")
    ax.set_xlabel(measure.axis, color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel(MEASURES["accuracy"].axis, color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"Accuracy against {measure.label.lower()}, by experiment",
                 fontsize=13, pad=30)
    _subtitle(ax, "Arrow = what changing the wording did to the baseline; up is worth "
                  f"having, right is what it cost  |  {_scope_note(summary)}")
    ax.set_ylim(-5, 112)
    ax.margins(x=0.22)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9, loc="lower right")
    ar._finish(fig, ax, out, rotate_xticks=False)


def plot_label_complexity(summary, out: Path) -> None:
    """The two measures against how many words each run gave a direction.

    Only drawn when the selection actually spans different label lengths - it's
    the chart for "does making the label longer do anything on its own", and
    with every run at one word there is no axis to plot along. Marker size
    carries a second variable: how many spatial words the labels themselves
    contained, which separates a long nonsense phrase from a long phrase that
    keeps saying "southwest" while meaning north.
    """
    runs = summary["runs"]
    colors = experiment_colors(runs, summary["baseline"])
    words = [s["label"]["words"] for s in runs]

    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.0))
    for ax, key in zip(axes, ("accuracy", "tokens")):
        measure = MEASURES[key]
        ys = [s["metrics"][key]["value"] for s in runs]
        offsets = _stagger(list(zip(words, ys)),
                           max(words) - min(words), max(ys) - min(ys))
        for s, x, y, dy in zip(runs, words, ys, offsets):
            hits = s["label"]["spatial_words"]
            ax.scatter(x, y, s=110 + 90 * hits, color=colors[s["name"]],
                       alpha=0.9, edgecolors="white", linewidths=1.2, zorder=3)
            ax.annotate(_tick(s["name"], 20), (x, y), textcoords="offset points",
                        xytext=(9, dy), fontsize=8, color="#52514e", zorder=5)
        if len({round(w, 1) for w in words}) >= 2:
            slope, intercept = np.polyfit(words, ys, 1)
            span = np.linspace(min(words), max(words), 2)
            ax.plot(span, slope * span + intercept, linestyle=(0, (5, 4)),
                    linewidth=1.2, color="#898781", zorder=1,
                    label=f"Trend ({slope:+.1f} per word)")
            ax.legend(fontsize=8.5, loc="best")
        ax.set_xlabel("Words per direction name (how long each label was)",
                      color=LABEL_GRAY, fontsize=10)
        ax.set_ylabel(measure.axis, color=LABEL_GRAY, fontsize=10)
        ax.set_title(measure.label, fontsize=11.5)
        ax.grid(True, alpha=0.3)
        ax.margins(x=0.25, y=0.25)
        ax.spines[["top", "right"]].set_visible(False)
        if key == "accuracy":
            ax.set_ylim(-5, 112)
            ax.axhline(CHANCE, linestyle="--", linewidth=1, color="#898781")

    fig.tight_layout()
    fig.suptitle("What label length did to accuracy and to cost", fontsize=13, y=1.09)
    fig.text(0.5, 1.03, "Bigger marker = more real direction words hidden inside the "
                        f"labels themselves  |  {_scope_note(summary)}",
             ha="center", fontsize=9, color=LABEL_GRAY)
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_accuracy_by_folds_by_experiment(summary, out: Path, fold_rows) -> None:
    """Difficulty curves with one line per experiment, models averaged.

    ``analysis.plot_accuracy_by_folds`` draws a line per model inside one run;
    this draws a line per run, so the question becomes whether a wording made
    the puzzle harder everywhere or only once the folds piled up. Only drawn
    when at least one selected run swept more than one fold count.

    The one chart that reads ``fold_rows`` rather than the scoped summary: the
    fold count is this chart's x axis, and trimming every run to the folds they
    all share would flatten it to a single column and delete the very thing it
    was drawn to show. Models are still trimmed to the common set, so the lines
    remain comparable at the fold counts where they overlap.
    """
    runs = summary["runs"]
    colors = experiment_colors(runs, summary["baseline"])

    fig, ax = plt.subplots(figsize=(10.0, 6.5))
    drawn = False
    for s in runs:
        rows = fold_rows[s["name"]]
        folds = ar.fold_values(rows)
        if not folds:
            continue
        ys, counts = [], []
        for f in folds:
            at_fold = [r for r in rows if r.get("num_folds") is not None
                       and int(r["num_folds"]) == f]
            per_model = ar.model_values(at_fold)
            ys.append(ar.macro_average(v for _, v, _ in per_model))
            counts.append(len(per_model))
        if len(folds) == 1:
            ax.scatter(folds, ys, s=90, color=colors[s["name"]], zorder=3,
                       edgecolors="white", linewidths=1,
                       label=ar.display_name(s["name"]))
        else:
            ax.plot(folds, ys, marker="o", markersize=6, linewidth=2.0,
                    color=colors[s["name"]], label=ar.display_name(s["name"]), zorder=3)
        # A run stopped partway leaves the deeper fold counts to whichever models
        # got that far, and a point averaging two models next to one averaging
        # twelve is not the trend it looks like. Say so where it happens - and
        # only there, since on a complete sweep the counts are all the same and
        # would be noise on the chart.
        if len(set(counts)) > 1:
            for f, y, n in zip(folds, ys, counts):
                ax.annotate(f"{n}", (f, y), textcoords="offset points", xytext=(0, -14),
                            ha="center", fontsize=7.5, color=colors[s["name"]])
        drawn = True
    if not drawn:
        plt.close(fig)
        return

    ax.axhline(CHANCE, linestyle="--", linewidth=1, color="#898781",
               label=f"Chance ({CHANCE:.0f}%)")
    ax.set_xlabel("Number of folds (how many times the paper was folded)",
                  color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel(MEASURES["accuracy"].axis, color=LABEL_GRAY, fontsize=10)
    ax.set_title("Difficulty curve, one line per experiment", fontsize=13, pad=30)
    _subtitle(ax, "Every model averaged into one line per run - where a line reaches the "
                  "chance level is how much folding that wording could carry  |  "
                  "the only chart here that keeps each run's full fold range  |  "
                  "a small number under a point = how few models reached that far")
    ax.set_ylim(-5, 110)
    ax.margins(x=0.08)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8.5, loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    ar._finish(fig, ax, out, rotate_xticks=False)


def plot_letter_bias_by_experiment(summary, out: Path) -> None:
    """Which of the five letters the answers landed on, per experiment.

    Accuracy says how often a run was right; this says what it did when it
    wasn't. Answers spread evenly across A-E are answers to the puzzle. Answers
    piling onto one letter are a fallback, and a wording that produces that
    pile has pushed the models out of reasoning and into guessing - which is a
    different failure from simply finding the puzzle harder.
    """
    runs = summary["runs"]
    colors = experiment_colors(runs, summary["baseline"])
    letters = ar.LETTERS
    width = 0.8 / len(runs)
    xs = np.arange(len(letters))

    fig, ax = plt.subplots(figsize=(max(8.0, 1.3 * len(runs) + 6.0), 5.8))
    for j, s in enumerate(runs):
        shares = [s["letters"]["predicted"][l] for l in letters]
        ax.bar(xs + (j - (len(runs) - 1) / 2) * width, shares, width * 0.92,
               color=colors[s["name"]], label=ar.display_name(s["name"]), zorder=2)
    ax.axhline(100 / len(letters), linestyle="--", linewidth=1.2, color="#898781",
               label="Even spread (20% each)", zorder=3)
    ax.set_xticks(xs)
    ax.set_xticklabels(letters)
    ax.set_xlabel("Answer letter (the five candidate options)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Share of answers (% of that run's trials)", color=LABEL_GRAY, fontsize=10)
    ax.set_title("Which letter the answers went to, by experiment", fontsize=13, pad=30)
    _subtitle(ax, "A run leaning hard on one letter has stopped answering the puzzle  |  "
                  + ",  ".join(f"{ar.display_name(s['name'])}: {s['letters']['skew']:.0f}% skew"
                               for s in runs[:3]))
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(fontsize=8.5, loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False)
    ar._finish(fig, ax, out, rotate_xticks=False)


def build_all_plots(summary, fold_rows, plots_dir: Path) -> list[str]:
    """Write every comparison plot that this selection can support.

    Some kinds only mean something for certain selections - a difficulty curve
    needs a run that swept folds, a label-length chart needs runs whose labels
    differ in length - so those are skipped rather than drawn empty, and any
    stale copy from an earlier comparison in the same folder is removed so the
    page never shows a chart that no longer applies.

    ``fold_rows`` is {run name: rows trimmed to the common models but keeping
    every fold count}; only the difficulty-curve chart reads it (see there).
    """
    plots_dir.mkdir(parents=True, exist_ok=True)
    runs = summary["runs"]

    def has_fold_sweep() -> bool:
        return any(len(ar.fold_values(fold_rows.get(s["name"], []))) > 1 for s in runs)

    def label_lengths_differ() -> bool:
        return len({round(s["label"]["words"], 1) for s in runs}) > 1

    builders: dict[str, tuple[Callable[[Path], None], bool]] = {
        "accuracy_by_experiment":
            (lambda p: plot_metric_by_experiment(summary, p, "accuracy"), True),
        "tokens_by_experiment":
            (lambda p: plot_metric_by_experiment(summary, p, "tokens"), True),
        "time_by_experiment":
            (lambda p: plot_metric_by_experiment(summary, p, "time"), True),
        "accuracy_matrix":
            (lambda p: plot_accuracy_matrix(summary, p), True),
        "accuracy_change_matrix":
            (lambda p: plot_accuracy_change_matrix(summary, p), len(runs) > 1),
        "tokens_change_matrix":
            (lambda p: plot_tokens_change_matrix(summary, p), len(runs) > 1),
        "model_slopes":
            (lambda p: plot_model_slopes(summary, p), len(runs) > 1),
        "sensitivity_by_model":
            (lambda p: plot_sensitivity_by_model(summary, p), len(runs) > 1),
        "accuracy_vs_tokens_by_experiment":
            (lambda p: plot_accuracy_vs_cost(summary, p, "tokens"), True),
        "accuracy_vs_time_by_experiment":
            (lambda p: plot_accuracy_vs_cost(summary, p, "time"), True),
        "label_complexity":
            (lambda p: plot_label_complexity(summary, p), label_lengths_differ()),
        "accuracy_by_folds_by_experiment":
            (lambda p: plot_accuracy_by_folds_by_experiment(summary, p, fold_rows),
             has_fold_sweep()),
        "letter_bias_by_experiment":
            (lambda p: plot_letter_bias_by_experiment(summary, p), True),
    }

    written: list[str] = []
    for kind in PLOT_KINDS:
        build, applicable = builders[kind]
        out = plots_dir / f"{kind}.png"
        if not applicable:
            out.unlink(missing_ok=True)
            continue
        build(out)
        if out.exists():
            written.append(out.name)
    return written


def compare(run_dirs, baseline: str | None, restrict: bool,
            plots_dir: Path | None) -> dict[str, Any]:
    """The whole comparison in one call: read the runs, scope them, summarise
    them, and (when ``plots_dir`` is given) draw the charts.

    The single entry point the Studio server uses, so the server never has to
    know how scoping works or which charts exist - adding a plot kind here is
    all it takes for one to appear on the page.
    """
    runs = [load_run(d) for d in run_dirs]
    summary = build_summary(runs, baseline, restrict)
    if not summary.get("ok"):
        return summary
    if plots_dir is not None:
        model_scope = set(summary["scope"]["models_used"])
        fold_rows = {r["name"]: scope_rows(r["rows"], model_scope, None) for r in runs}
        summary["plots"] = build_all_plots(summary, fold_rows, plots_dir)
    return summary


# =============================================================================
#  Where a comparison lives on disk
# =============================================================================
def comparison_slug(names) -> str:
    """A stable folder name for one selection of runs.

    Derived from the run names, so re-opening the same comparison lands on the
    same folder and overwrites its own plots instead of leaving a new pile
    behind every time the page is refreshed. Sorted first: comparing A against
    B and B against A is the same set of charts up to which one is the baseline,
    and the baseline is a redraw rather than a different folder.
    """
    digest = hashlib.sha1("\n".join(sorted(names)).encode()).hexdigest()[:10]
    return f"cmp_{digest}"


def prune_comparisons(root: Path, keep: int = 12) -> None:
    """Keep only the most recently written comparison folders.

    These are pure derived output - every one of them can be rebuilt from the
    runs in a second - so an unbounded pile of them is just clutter. Only
    folders this module named are ever touched.
    """
    if not root.exists():
        return
    folders = [d for d in root.iterdir() if d.is_dir() and d.name.startswith("cmp_")]
    for old in sorted(folders, key=lambda d: d.stat().st_mtime, reverse=True)[keep:]:
        for f in old.glob("*"):
            if f.is_file():
                f.unlink()
        try:
            old.rmdir()
        except OSError:
            pass          # something unexpected in there - leave it alone
