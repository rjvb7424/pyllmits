"""
llmits.paperfold.analysis
=========================

Reads a paper-folding run's results.json and writes plots visualising how
well each model solved the puzzle. Ported from the original prototype's
analyze_results.py, with these changes:
  * results.json is now nested by model (matching the rest of this project's
    convention) instead of one flat list, so flatten() reconstructs the flat
    per-trial view every plot function still expects.
  * model_color_map()/_detect_provider() prefer the real backend field
    (populated by paperfold/runner.py) over guessing a provider from the
    model name - more reliable, and it generalises to any backend models/
    supports without needing a new regex every time.
  * styled to match the Crafter graphs (llmits.analysis.plots): titles read
    "<metric> of <name> experiment" with underscores shown as spaces, axis
    labels are the same muted gray with a plain-language explanation in
    parentheses, subtitles sit just above the axes, and top/right spines
    are hidden.

Plots are written to <run_dir>/plots/ as <kind>_of_<name>.png, matching the
naming convention llmits.analysis.plots (Crafter's) already uses:
  * letter_distribution_of_<name>.png   - predicted vs correct answer letter
  * accuracy_by_folds_of_<name>.png     - accuracy vs number of folds
                                          (only for runs that swept more than
                                          one fold count)
  * accuracy_by_model_of_<name>.png     - accuracy ranked best-to-worst, with
                                          the run's average as an extra bar
  * average_accuracy_of_<name>.png      - that average on its own, the number
                                          to carry between runs when comparing
                                          two environments
  * average_tokens_of_<name>.png        - the same one-bar summary for token
                                          spend: what the environment cost
  * average_time_of_<name>.png          - and for response time
  * accuracy_vs_tokens_of_<name>.png    - accuracy vs average token spend
  * accuracy_vs_time_of_<name>.png      - accuracy vs average response time
  * elapsed_time_by_model_of_<name>.png - average response time per model
  * tokens_by_model_of_<name>.png       - average token consumption per model

The three average_* charts share one shape (_plot_average) and the three
"by model" rankings share another (_draw_ranked_with_average), so a summary
bar means the same thing wherever it appears.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from llmits.paperfold.cognitive_test import paper_size_for_folds

# The letters used for the candidates in the spatial visualisation test.
LETTERS = ["A", "B", "C", "D", "E"]

# Same muted gray llmits.analysis.plots uses for axis labels and subtitles,
# so Crafter and paper-folding graphs read as one family.
LABEL_GRAY = "#8a8a8a"

# Each AI provider gets their own color family (a matplotlib colormap).
# Models from the same provider are shaded from light to dark within that family.
PROVIDER_COLORMAPS = {
    "gemini": plt.get_cmap("Blues"),
    "gpt": plt.get_cmap("Reds"),
}
# Fallback colormaps for providers not in PROVIDER_COLORMAPS.
FALLBACK_COLORMAPS = [plt.get_cmap("Greens"), plt.get_cmap("Purples"), plt.get_cmap("Oranges"), plt.get_cmap("Greys")]
# The range of shades to use for models within a provider's colormap
SHADE_RANGE = (0.35, 0.85)

PLOT_KINDS = ("letter_distribution", "accuracy_by_folds", "accuracy_by_model",
              "average_accuracy", "average_tokens", "average_time",
              "accuracy_vs_tokens", "accuracy_vs_time",
              "elapsed_time_by_model", "tokens_by_model")

# The average is a summary of the models, not one of them, so it's drawn in a
# neutral gray that can't be mistaken for a provider's color family, and set
# off from the ranked bars by a blank slot.
AVERAGE_COLOR = "#6f6d69"
AVERAGE_BREAKDOWN_COLOR = "#b6b4af"   # the per-fold-count bars it breaks into
AVERAGE_GAP = 0.6                     # blank space between the models and it

# Lines that land on the same accuracy (several models all at 100%, say) would
# be drawn exactly on top of each other and only the last one painted would be
# visible. Each hidden line gets a constant vertical nudge instead: small
# enough that the curve still reads as its true accuracy, big enough to see.
OVERLAP_NUDGE = 2.5      # percentage points between two lines nudged apart
OVERLAP_EPSILON = 2.0    # closer than this at a shared fold count = overlapping
# Cycled per model so tied lines are told apart by marker shape too, not just
# by the nudge - useful for anyone reading the graph in black and white.
MARKERS = ("o", "s", "^", "D", "v", "P", "X", "*")


def plot_filename(kind: str, name_slug: str) -> str:
    """Filename for a plot, e.g. accuracy_by_model_of_my_run.png."""
    return f"{kind}_of_{name_slug}.png"


def display_name(name: str) -> str:
    """Run name as shown in plot titles - underscores read as spaces (same
    convention as llmits.analysis.plots.get_experiment_name)."""
    return str(name).replace("_", " ").strip()


def flatten(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the nested (by model) results.json into one list of trial
    rows, the shape every plot function below expects. Each trial already
    carries its own "model_version"; this adds "backend" from the owning
    model's record alongside it."""
    rows: list[dict[str, Any]] = []
    for record in results.get("models", {}).values():
        backend = record.get("backend")
        for trial in record.get("trials", []):
            row = dict(trial)
            row.setdefault("backend", backend)
            rows.append(row)
    return rows


def filter_scored(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only keep trials that actually got a solver response."""
    return [r for r in rows if r.get("predicted_choice") is not None]


def accuracy_of(rows) -> float:
    """Percent of a set of trials answered correctly."""
    return 100 * sum(1 for r in rows if r["is_correct"]) / len(rows) if rows else 0.0


def field_average(field: str):
    """A measure reading one numeric field off each trial and averaging it -
    how "average tokens" and "average response time" are both expressed."""
    def measure(rows) -> float:
        return (sum(float(r.get(field) or 0) for r in rows) / len(rows)) if rows else 0.0
    return measure


def model_values(rows, measure=accuracy_of) -> list[tuple[str, float, int]]:
    """(model, value, trials) for every model, ranked lowest-to-highest.

    The one place a per-model figure is worked out, whatever the measure, so
    the ranked bars and the averages drawn on top of them can never disagree.
    """
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        by_model.setdefault(r.get("model_version", "unknown"), []).append(r)
    ranked = sorted(by_model.items(), key=lambda kv: measure(kv[1]))
    return [(m, measure(rs), len(rs)) for m, rs in ranked]


def model_accuracies(rows) -> list[tuple[str, float, int]]:
    """(model, accuracy %, trials) for every model, ranked worst-to-best."""
    return model_values(rows, accuracy_of)


def macro_average(values) -> float:
    """The average of the per-model bars: each model counts once, however many
    trials it happened to run.

    Deliberately not the same thing as pooling every trial together. A run
    stopped partway can leave one model with a single trial and another with
    sixty, and pooling would let whichever model ran longest speak for the
    whole experiment - so a half-finished run would read as the accuracy (or
    the token bill) of its fastest model. Averaging the bars keeps every
    model's voice the same size; where the two figures disagree the subtitle
    prints both rather than quietly picking one.
    """
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _count_summary(counts) -> str:
    """One number when every model ran the same amount ("40"), a range when
    they differ ("1-60" - a run stopped partway, or a model added late)."""
    counts = set(counts)
    if not counts:
        return "0"
    if len(counts) == 1:
        return str(counts.pop())
    return f"{min(counts)}-{max(counts)}"


def _average_note(rows, per_model, measure=accuracy_of, fmt=lambda v: f"{v:.0f}%") -> str:
    """Subtitle saying what the average bar is an average of - and, when
    unequal trial counts pull the two apart, what pooling every trial would
    have said instead.

    The gap is judged relative to the average itself (a couple of percent)
    rather than in fixed units, so the same rule works for a figure that runs
    0-100 and one measured in thousands of tokens.
    """
    macro, pooled = macro_average(v for _, v, _ in per_model), measure(rows)
    trials = _count_summary(n for _, _, n in per_model)
    note = (f"Average = mean of the {len(per_model)} model "
            f"bar{'' if len(per_model) == 1 else 's'}  |  "
            f"{trials} trial{'' if trials == '1' else 's'} per model")
    if abs(macro - pooled) >= max(0.02 * abs(macro), 1e-9):
        note += f"  |  pooling every trial instead: {fmt(pooled)}"
    return note


def _detect_provider(model_name: str, backend: str | None = None) -> str:
    """Which provider family a model belongs to, for color grouping. Prefers
    the real backend string (exact) over guessing from the model name (only
    used as a fallback for rows that predate the backend field)."""
    if backend:
        b = backend.lower()
        if b in ("gemini", "google"):
            return "gemini"
        if b in ("openai", "chatgpt", "gpt"):
            return "gpt"
        return "other"
    name = model_name.lower()
    if name.startswith("gemini"):
        return "gemini"
    if name.startswith("gpt") or re.match(r"^o\d", name):
        return "gpt"
    return "other"


def model_color_map(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Maps each model name to a color, grouped by provider color family."""
    model_backend: dict[str, str | None] = {}
    for r in rows:
        name = r.get("model_version", "unknown")
        if name not in model_backend:
            model_backend[name] = r.get("backend")
    models = sorted(model_backend.keys())

    # Group models by provider, so we can shade them within their provider's colormap.
    by_provider: dict[str, list[str]] = {}
    for m in models:
        by_provider.setdefault(_detect_provider(m, model_backend[m]), []).append(m)

    color_map = {}
    fallback_idx = 0
    # Sort provider keys so fallback-family assignment is stable across runs.
    for provider in sorted(by_provider.keys()):
        provider_models = sorted(by_provider[provider])
        n = len(provider_models)

        if provider in PROVIDER_COLORMAPS:
            cmap = PROVIDER_COLORMAPS[provider]
        else:
            cmap = FALLBACK_COLORMAPS[fallback_idx % len(FALLBACK_COLORMAPS)]
            fallback_idx += 1

        shades = [SHADE_RANGE[1]] if n == 1 else np.linspace(SHADE_RANGE[0], SHADE_RANGE[1], n)
        for model, shade in zip(provider_models, shades):
            color_map[model] = cmap(shade)

    return color_map


def _finish(fig, ax, out, rotate_xticks: bool = True) -> None:
    """Same finishing pass as the Crafter plots: no top/right spines, slanted
    x tick labels (skippable where they're single letters or numbers)."""
    ax.spines[["top", "right"]].set_visible(False)
    if rotate_xticks:
        plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_letter_distribution(rows, out: Path, experiment_name: str) -> None:
    """Predicted letter vs correct letter counts. A skew toward one
    letter in 'predicted' that doesn't match 'correct' is a sign of
    positional bias rather than real reasoning."""
    predicted_counts = Counter(r["predicted_choice"] for r in rows)
    correct_counts = Counter(r["correct_choice"] for r in rows)

    x = range(len(LETTERS))
    width = 0.35
    predicted_vals = [predicted_counts.get(l, 0) for l in LETTERS]
    correct_vals = [correct_counts.get(l, 0) for l in LETTERS]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar([i - width / 2 for i in x], predicted_vals, width, label="Predicted", color="#2a78d6")
    ax.bar([i + width / 2 for i in x], correct_vals, width, label="Correct", color="#eda100")
    ax.set_xticks(list(x))
    ax.set_xticklabels(LETTERS)
    ax.set_xlabel("Answer letter (the five candidate options)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Count (number of trials)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"Answer letter distribution of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    ax.legend(fontsize=9)
    _finish(fig, ax, out, rotate_xticks=False)


def fold_values(rows) -> list[int]:
    """Every fold count the run recorded trials at, sorted."""
    return sorted({int(r["num_folds"]) for r in rows if r.get("num_folds") is not None})


def sweeps_fold_counts(rows) -> bool:
    """Whether the run actually varied how many times the paper was folded.

    The accuracy-by-folds curve is a difficulty curve - it only says anything
    when the difficulty moved. At a single fold count every "line" is one dot
    and accuracy_by_model shows the same numbers more clearly, so
    build_all_plots skips the plot entirely in that case.
    """
    return len(fold_values(rows)) > 1


def _curve_overlaps(a: dict[int, float], b: dict[int, float]) -> bool:
    """True when two accuracy curves sit close enough at some shared fold
    count that drawing both would hide one under the other."""
    return any(abs(a[f] - b[f]) < OVERLAP_EPSILON for f in a.keys() & b.keys())


def _nudge_offset(level: int) -> float:
    """Vertical shift for a nudge level, alternating above/below the true
    value (0, +1, -1, +2, -2, ...) so a stack of tied models stays centred
    on the accuracy they share."""
    step = (level + 1) // 2
    return step * OVERLAP_NUDGE * (1 if level % 2 else -1)


def _nudge_offsets(curves: list[tuple[str, dict[int, float]]]) -> dict[str, float]:
    """How far to shift each model's line so none of them disappears beneath
    another. Assigned greedily in draw order: a curve keeps its true accuracy
    (no shift) unless it would collide with a line already placed, in which
    case it steps to the nearest free slot above or below. Collisions are
    checked against the placed lines' *shifted* positions, so nudging a line
    clear of one neighbour never drops it onto another.
    """
    offsets: dict[str, float] = {}
    placed: list[dict[int, float]] = []
    for model, curve in curves:
        level = 0
        while True:
            offset = _nudge_offset(level)
            shifted = {f: y + offset for f, y in curve.items()}
            if not any(_curve_overlaps(shifted, other) for other in placed):
                break
            level += 1
        offsets[model] = offset
        placed.append(shifted)
    return offsets


def plot_accuracy_by_folds(rows, out: Path, experiment_name: str) -> None:
    """Accuracy against how many times the paper was folded - the difficulty
    curve, one line per model.

    This is the plot a fold-range run exists for: each extra fold doubles the
    layers a solver has to unfold mentally, so a model that's really reasoning
    about the geometry should slide downward as folds increase, while one that
    was pattern-matching (or guessing) sits flat near the 20% five-choice
    chance line from the start.

    Trials are grouped by their own recorded "num_folds", so this works
    whatever the run swept. Models that tie on accuracy (a whole field sitting
    at 100%, say) would otherwise draw one line on top of another and leave
    only the last-painted model visible, so tied lines are nudged a couple of
    percentage points apart and the subtitle says so.
    """
    by_model: dict[str, dict[int, list[int]]] = {}
    for r in rows:
        folds = r.get("num_folds")
        if folds is None:
            continue          # pre-fold-count trial data; nothing to place it at
        m = r.get("model_version", "unknown")
        by_model.setdefault(m, {}).setdefault(int(folds), []).append(1 if r["is_correct"] else 0)

    folds_seen = fold_values(rows)
    colors = model_color_map(rows)

    fig, ax = plt.subplots(figsize=(10, 6.5))
    if not folds_seen:
        ax.text(0.5, 0.5, "No trials with a recorded fold count yet",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=11, color=LABEL_GRAY)
        ax.set_axis_off()
        fig.savefig(out, dpi=130, bbox_inches="tight")
        plt.close(fig)
        return

    # Best model last, so the legend reads worst-to-best top-down the same way
    # the accuracy-by-model bars are ranked.
    def overall(model: str) -> float:
        flags = [f for per_folds in by_model[model].values() for f in per_folds]
        return sum(flags) / len(flags)

    curves = [(model, {f: 100 * sum(flags) / len(flags)
                       for f, flags in by_model[model].items()})
              for model in sorted(by_model, key=overall)]
    offsets = _nudge_offsets(curves)

    drawn: list[float] = []
    for i, (model, curve) in enumerate(curves):
        xs = [f for f in folds_seen if f in curve]
        ys = [curve[f] + offsets[model] for f in xs]
        drawn.extend(ys)
        ax.plot(xs, ys, marker=MARKERS[i % len(MARKERS)], markersize=5, linewidth=1.8,
                color=colors[model], label=model, alpha=0.9, zorder=3)

    ax.axhline(20, linestyle="--", linewidth=1, color="#898781", label="Chance (20%)")
    ax.set_xticks(folds_seen)
    ax.set_xticklabels([str(f) for f in folds_seen])
    ax.set_xlabel("Number of folds (how many times the paper was folded)",
                  color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Accuracy (% of answers correct)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"Accuracy by number of folds of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    # Paper size is derived from the fold count, so say what the sheet grew
    # to across the x axis - it's the other thing that changed along it, and
    # it's why the prompts get longer toward the right. The nudge note only
    # appears when a line actually moved, so a graph with no ties doesn't
    # invite doubt about numbers that are exactly where they look.
    nudged = ("  |  tied lines nudged apart to stay visible, centred on the accuracy they share"
              if any(offsets.values()) else "")
    ax.annotate(f"Trials per point: {_trials_per_point(by_model, folds_seen)}  |  "
                f"{_paper_size_summary(rows, folds_seen)}{nudged}",
                xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=9, color=LABEL_GRAY)
    # Keep the usual 0-100 framing, widened only if a nudge pushed a line past it.
    ax.set_ylim(min(-5, min(drawn) - 3), max(110, max(drawn) + 3))
    ax.margins(x=0.06)
    ax.grid(True, alpha=0.3)
    # Outside the axes on the right: a run can hold a dozen-plus models, and an
    # in-axes legend that size covers the lines it's labelling.
    ax.legend(fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5),
              frameon=False)
    _finish(fig, ax, out, rotate_xticks=False)


def _trials_per_point(by_model: dict, folds_seen: list[int]) -> str:
    """How many trials each point averages over - one number when every model
    ran the same amount at every fold count, a range when they differ."""
    return _count_summary(len(per_folds[f]) for per_folds in by_model.values()
                          for f in folds_seen if f in per_folds)


def _paper_size_label(rows, folds: int) -> str:
    """The sheet size used at a given fold count, e.g. "16x16".

    Read from the trials themselves where possible. Trials recorded before
    paper size was written into each result fall back to deriving it from the
    fold count - the same rule the run itself used, and for the 3-fold runs
    that predate the field it gives exactly the 16x16 they were answered on.
    """
    for r in rows:
        if r.get("num_folds") == folds and r.get("paper_width"):
            return f"{r['paper_width']}x{r['paper_height']}"
    width, height = paper_size_for_folds(folds)
    return f"{width}x{height}"


def _paper_size_summary(rows, folds_seen: list[int]) -> str:
    """How the paper grew across the x axis, in one short phrase - listing
    every fold count separately gets unreadable past a few of them."""
    first, last = _paper_size_label(rows, folds_seen[0]), _paper_size_label(rows, folds_seen[-1])
    if len(folds_seen) == 1 or first == last:
        return f"paper {first}"
    return f"paper {first} at {folds_seen[0]} folds, up to {last} at {folds_seen[-1]}"


def plot_accuracy_by_model(rows, out: Path, experiment_name: str) -> None:
    """Accuracy broken down by model, ranked best-to-worst, with the run's
    average as one more bar above them.

    The per-model ranking answers "who is best here". The average bar answers
    the other question this experiment keeps being asked - "did changing the
    environment change anything" - because flipping between two runs (real
    direction names, then made-up ones) with a dozen-plus bars reshuffling
    tells you far less than one summary number moving. It's kept visually
    separate (gray, hatched, a blank slot below it) so it never reads as one
    more model, and repeated as a dashed line down the ranked bars so you can
    still see who sits above the average and who below.
    """
    per_model = model_accuracies(rows)
    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.6 * (len(per_model) + 2) + 1)))
    average = _draw_ranked_with_average(ax, per_model, model_color_map(rows),
                                        fmt=lambda v: f"{v:.0f}%", label_pad=1.5)
    ax.axvline(20, linestyle="--", linewidth=1, color="#898781", label="Chance (20%)")
    ax.set_xlabel("Accuracy (% of answers correct)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Model (LLM model used)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"Accuracy by model of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    ax.annotate(_average_note(rows, per_model),
                xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=9, color=LABEL_GRAY)
    ax.set_xlim(0, 110)
    ax.legend(fontsize=9, loc="lower right")
    _finish(fig, ax, out, rotate_xticks=False)


def _draw_ranked_with_average(ax, per_model, colors_map, *, fmt, label_pad) -> float:
    """Draw ranked horizontal bars with the run's average as one more bar
    above them, and return that average.

    Shared by every "by model" chart here (accuracy, tokens, response time),
    so the summary row looks and means the same thing on all of them. The
    average is kept visually separate - gray, hatched, a blank slot below it -
    so it never reads as one more model, and repeated as a dashed line down
    the ranked bars so you can still see who sits above it and who below.
    """
    models = [m for m, _, _ in per_model]
    values = [v for _, v, _ in per_model]
    average = macro_average(values)

    # Numeric y positions rather than the model names themselves: the average
    # needs a slot of its own with a gap under it, which categorical bars
    # (evenly spaced, one per label) can't leave room for.
    ys = list(range(len(models)))
    average_y = len(models) + AVERAGE_GAP

    bars = ax.barh(ys, values, color=[colors_map[m] for m in models])
    average_bar = ax.barh([average_y], [average], color=AVERAGE_COLOR,
                          hatch="//", edgecolor="white", linewidth=0)
    for bar, value in zip(bars, values):
        ax.text(bar.get_width() + label_pad, bar.get_y() + bar.get_height() / 2,
                fmt(value), va="center", fontsize=9, color="#52514e")
    ax.text(average_bar[0].get_width() + label_pad,
            average_bar[0].get_y() + average_bar[0].get_height() / 2,
            fmt(average), va="center", fontsize=9, color="#52514e",
            fontweight="bold")
    ax.set_yticks(ys + [average_y])
    ax.set_yticklabels(models + [f"Average (all {len(models)} models)"])
    ax.get_yticklabels()[-1].set_fontweight("bold")
    # A longer dash than the chance line's: the two sit in the same gray family
    # (the average line matches the average bar on purpose) and would otherwise
    # be hard to tell apart where they fall close together.
    ax.axvline(average, linestyle=(0, (6, 3)), linewidth=1.2, color=AVERAGE_COLOR,
               label=f"Average ({fmt(average)})")
    return average


def _plot_average(rows, out: Path, experiment_name: str, *, measure, metric: str,
                  ylabel: str, fmt, chance: float | None = None,
                  ylim: tuple[float, float] | None = None) -> None:
    """Shared shape for the whole-run average charts: one bar for the entire
    experiment, plus a bar per fold count when the run swept them.

    Every other plot here compares models inside a single run. These exist to
    compare runs *to each other*: run the same models on real direction names,
    then on made-up ones, and the gap between the two bars is the whole
    finding, with nothing else on the graph to read past. The thin line
    through each bar is the spread the average hides (lowest model to
    highest), because a shift means something very different when every model
    moved together than when one model moved and the rest held.

    On a fold sweep the per-fold bars turn the difficulty trend into one
    averaged shape instead of the dozen-plus crossing lines in
    accuracy_by_folds - and for the cost measures they show the thing that
    drives the bill, since every extra fold means a bigger sheet and a longer
    prompt to reason over.
    """
    per_model = model_values(rows, measure)
    values_by_model = [v for _, v, _ in per_model]
    folds_seen = fold_values(rows)

    fig, ax = plt.subplots(figsize=(max(5.0, 1.5 * (len(folds_seen) + 1) + 3.0), 5.5))
    if not per_model:
        ax.text(0.5, 0.5, "No scored trials yet", ha="center", va="center",
                transform=ax.transAxes, fontsize=11, color=LABEL_GRAY)
        ax.set_axis_off()
        fig.savefig(out, dpi=130, bbox_inches="tight")
        plt.close(fig)
        return

    # (tick label, average, lowest model, highest model, models averaged). The
    # whole-run bar is always last; the fold-count bars before it only appear
    # when the run actually varied difficulty (at one fold count they'd be the
    # same bar twice over).
    columns: list[tuple[str, float, float, float, int]] = []
    if len(folds_seen) > 1:
        for f in folds_seen:
            at_fold = [v for _, v, _ in model_values(
                [r for r in rows if r.get("num_folds") is not None
                 and int(r["num_folds"]) == f], measure)]
            columns.append((str(f), macro_average(at_fold),
                            min(at_fold), max(at_fold), len(at_fold)))
    columns.append(("All folds" if len(folds_seen) > 1 else f"All {len(per_model)} models",
                    macro_average(values_by_model),
                    min(values_by_model), max(values_by_model), len(per_model)))

    xs = list(range(len(columns)))
    if len(columns) > 1:
        xs[-1] += AVERAGE_GAP     # set the whole-run bar apart from its breakdown
    values = [c[1] for c in columns]
    colors = [AVERAGE_BREAKDOWN_COLOR] * (len(columns) - 1) + [AVERAGE_COLOR]

    # Accuracy is framed 0-100 whatever the run did, so two runs' bars are
    # directly comparable by eye. Tokens and seconds have no such ceiling, so
    # they scale to the tallest range line - the printed figure carries the
    # comparison there, not the bar height.
    top = ylim[1] if ylim else (1.25 * max(c[3] for c in columns) or 1.0)
    headroom = 0.025 * top   # gap between a range line's cap and its label

    ax.bar(xs, values, width=0.6 if len(columns) == 1 else 0.72,
           color=colors, zorder=2)
    ax.errorbar(xs, values,
                yerr=[[v - c[2] for v, c in zip(values, columns)],
                      [c[3] - v for v, c in zip(values, columns)]],
                fmt="none", ecolor="#52514e", elinewidth=1, capsize=5, zorder=4,
                label="Lowest to highest model")
    # Above the range line rather than the bar, so the number never lands on
    # top of the spread it's summarising. The whole-run one is bold: on a fold
    # sweep it's the headline and the rest are its breakdown.
    for i, (x, value, column) in enumerate(zip(xs, values, columns)):
        ax.text(x, column[3] + headroom, fmt(value), ha="center", va="bottom",
                fontsize=10, color="#52514e",
                fontweight="bold" if i == len(columns) - 1 else "normal")
    if chance is not None:
        ax.axhline(chance, linestyle="--", linewidth=1, color="#898781",
                   label=f"Chance ({chance:.0f}%)")
    ax.set_xticks(xs)
    # A run stopped partway can leave a fold count with fewer models behind it
    # than the run as a whole - and a bar averaging three models next to one
    # averaging five is not the comparison it looks like, so each bar says how
    # many it speaks for. Only when they actually differ: on a complete run
    # every bar covers every model and the counts would just be noise.
    varies = len({c[4] for c in columns}) > 1
    ax.set_xticklabels([f"{c[0]}\n({c[4]} model{'' if c[4] == 1 else 's'})" if varies
                        else c[0] for c in columns])
    ax.set_xlabel("Number of folds (how many times the paper was folded), then the "
                  "whole run" if len(folds_seen) > 1 else
                  "Whole run (every model, every trial)",
                  color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel(ylabel, color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"{metric} of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    ax.annotate(_average_note(rows, per_model, measure, fmt),
                xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=9, color=LABEL_GRAY)
    ax.set_ylim(ylim or (0, top))
    if len(columns) == 1:
        ax.set_xlim(-1.0, 1.0)    # one bar, centred - not a wall across the panel
    else:
        ax.margins(x=0.08)
    ax.grid(True, axis="y", alpha=0.3)
    # Under the whole figure: the bars fill the panel from y=0 up, so any
    # in-axes corner the legend could sit in already has a bar in it. Anchored
    # to the figure rather than the axes so it clears the x labels whatever
    # height they came out at (they grow a second line on a partial run), with
    # savefig's tight bounding box growing to take it in.
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=9, loc="upper center",
               bbox_to_anchor=(0.5, 0.0), ncol=2, frameon=False)
    _finish(fig, ax, out, rotate_xticks=False)


def plot_average_accuracy(rows, out: Path, experiment_name: str) -> None:
    """The run's accuracy as one number - what changing the environment did."""
    _plot_average(
        rows, out, experiment_name,
        measure=accuracy_of,
        metric="Average accuracy",
        ylabel="Accuracy (% of answers correct)",
        fmt=lambda v: f"{v:.0f}%",
        chance=20,
        ylim=(0, 118),
    )


def plot_average_tokens(rows, out: Path, experiment_name: str) -> None:
    """The run's token spend as one number - what changing the environment
    cost.

    The companion to average accuracy, and the one that says whether a change
    was free. Made-up direction words that hold accuracy steady but double the
    tokens didn't leave the models unbothered: they made them work harder for
    the same answer, and this is the bar that shows it.
    """
    _plot_average(
        rows, out, experiment_name,
        measure=field_average("total_tokens"),
        metric="Average token consumption",
        ylabel="Average token consumption (total tokens per trial)",
        fmt=lambda v: f"{v:,.0f}",
    )


def plot_average_time(rows, out: Path, experiment_name: str) -> None:
    """The run's thinking time as one number - the wall-clock counterpart to
    the token bill, and the one that moves when a model reasons longer without
    that showing up as more output."""
    _plot_average(
        rows, out, experiment_name,
        measure=field_average("elapsed_seconds"),
        metric="Average response time",
        ylabel="Average response time (seconds per trial)",
        fmt=lambda v: f"{v:.2f}s",
    )


def _plot_accuracy_vs(rows, out: Path, experiment_name: str, *,
                      field: str, metric: str, xlabel: str) -> None:
    """Shared shape for the efficiency scatters: one bubble per model
    (bubble size = number of trials), cost on x, accuracy on y. Top-left =
    accurate AND cheap (good). Bottom-right = expensive AND wrong (bad).
    A full-size single panel so the bubbles have room to breathe, with
    headroom above 100% so bubbles there aren't cropped."""
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        m = r.get("model_version", "unknown")
        by_model.setdefault(m, []).append(r)

    models = sorted(by_model.keys())
    colors = model_color_map(rows)

    points = []
    for m in models:
        rs = by_model[m]
        acc = 100 * sum(1 for r in rs if r["is_correct"]) / len(rs)
        avg_cost = sum((r.get(field) or 0) for r in rs) / len(rs)
        points.append((m, avg_cost, acc, len(rs)))
    xspan = (max(p[1] for p in points) - min(p[1] for p in points)) or 1.0

    fig, ax = plt.subplots(figsize=(11, 7.5))
    labelled: list[tuple[float, float, int]] = []  # (cost, acc, offset level)
    for m, avg_cost, acc, n in points:
        ax.scatter(avg_cost, acc, s=max(80, 25 * n), color=colors[m],
                   alpha=0.8, edgecolors="white", linewidths=1, zorder=3)
        # Stagger labels: when another label already sits at nearly the same
        # spot, step this one further away (below, then higher above, ...) so
        # clustered models stay readable.
        near = [lvl for cx, cy, lvl in labelled
                if abs(avg_cost - cx) < 0.18 * xspan and abs(acc - cy) < 5]
        level = next(lvl for lvl in range(len(points) + 1) if lvl not in near)
        dy = (6, -14, 20, -28, 34)[level % 5]
        labelled.append((avg_cost, acc, level))
        ax.annotate(m, (avg_cost, acc), textcoords="offset points",
                    xytext=(6, dy), fontsize=8, color="#52514e")
    ax.axhline(20, linestyle="--", linewidth=1, color="#898781", label="Chance (20%)")
    ax.set_xlabel(xlabel, color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Accuracy (% of answers correct)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"{metric} of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    ax.set_ylim(-5, 110)
    ax.margins(x=0.08)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9, loc="lower right")
    _finish(fig, ax, out, rotate_xticks=False)


def plot_accuracy_vs_tokens(rows, out: Path, experiment_name: str) -> None:
    """Accuracy against average token spend per trial."""
    _plot_accuracy_vs(
        rows, out, experiment_name,
        field="total_tokens",
        metric="Accuracy vs token consumption",
        xlabel="Average token consumption (total tokens per trial)",
    )


def plot_accuracy_vs_time(rows, out: Path, experiment_name: str) -> None:
    """Accuracy against average response time per trial."""
    _plot_accuracy_vs(
        rows, out, experiment_name,
        field="elapsed_seconds",
        metric="Accuracy vs response time",
        xlabel="Average response time (seconds per trial)",
    )


def _plot_avg_by_model(rows, out: Path, experiment_name: str, *,
                       field: str, metric: str, xlabel: str, fmt) -> None:
    """Shared shape for the per-model cost charts (response time, token
    consumption): average ``field`` over each model's trials, drawn as
    horizontal bars so the figure stays a sane size however many models a
    run has. Ranked so the value increases up the chart, with the run's
    average as an extra bar on top - the same summary row the accuracy
    ranking carries, so "is this model dear or cheap for this run" is
    answerable without doing the arithmetic by eye."""
    measure = field_average(field)
    per_model = model_values(rows, measure)
    xmax = max((v for _, v, _ in per_model), default=0) or 1.0

    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.6 * (len(per_model) + 2) + 1)))
    _draw_ranked_with_average(ax, per_model, model_color_map(rows),
                              fmt=fmt, label_pad=0.01 * xmax)
    ax.set_xlabel(xlabel, color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Model (LLM model used)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"{metric} of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    ax.annotate(_average_note(rows, per_model, measure, fmt),
                xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=9, color=LABEL_GRAY)
    ax.set_xlim(0, 1.15 * xmax)
    ax.legend(fontsize=9, loc="lower right")
    _finish(fig, ax, out, rotate_xticks=False)


def plot_elapsed_time_by_model(rows, out: Path, experiment_name: str) -> None:
    """Average response time per model, since slower/thinking models
    and fast/lite models are worth comparing directly."""
    _plot_avg_by_model(
        rows, out, experiment_name,
        field="elapsed_seconds",
        metric="Average response time by model",
        xlabel="Average response time (seconds per trial)",
        fmt=lambda v: f"{v:.2f}s" if v > 0 else "-",
    )


def plot_tokens_by_model(rows, out: Path, experiment_name: str) -> None:
    """Average token consumption per model - the token-cost counterpart to
    the response-time chart."""
    _plot_avg_by_model(
        rows, out, experiment_name,
        field="total_tokens",
        metric="Average token consumption by model",
        xlabel="Average token consumption (total tokens per trial)",
        fmt=lambda v: f"{v:,.0f}" if v > 0 else "-",
    )


def build_all_plots(rows, plots_dir: Path, slug: str) -> None:
    """Write every plot in ``PLOT_KINDS`` for one run into ``plots_dir``.

    The single authority on what "all plots" means for the paper-folding
    side (same pattern as llmits.analysis.plots.build_all_plots), so adding
    a plot never requires touching the Studio server.
    """
    plotters = {
        "letter_distribution": plot_letter_distribution,
        "accuracy_by_folds": plot_accuracy_by_folds,
        "accuracy_by_model": plot_accuracy_by_model,
        "average_accuracy": plot_average_accuracy,
        "average_tokens": plot_average_tokens,
        "average_time": plot_average_time,
        "accuracy_vs_tokens": plot_accuracy_vs_tokens,
        "accuracy_vs_time": plot_accuracy_vs_time,
        "elapsed_time_by_model": plot_elapsed_time_by_model,
        "tokens_by_model": plot_tokens_by_model,
    }
    plots_dir.mkdir(parents=True, exist_ok=True)
    for kind in PLOT_KINDS:
        out = plots_dir / plot_filename(kind, slug)
        # The difficulty curve needs a difficulty that moved: with a single
        # fold count it's one dot per model, which accuracy_by_model already
        # says better. Drop any copy left from an earlier build too - a run
        # re-analysed after its fold sweep was narrowed shouldn't keep showing
        # the old curve in the Studio's graphs tab.
        if kind == "accuracy_by_folds" and not sweeps_fold_counts(rows):
            out.unlink(missing_ok=True)
            continue
        plotters[kind](rows, out, slug)
    # Superseded plot kinds (e.g. the old combined accuracy_vs_cost panel) -
    # remove stale copies so they don't linger in the Studio's graphs tab.
    for stale_kind in ("accuracy_vs_cost",):
        stale = plots_dir / plot_filename(stale_kind, slug)
        if stale.exists():
            stale.unlink()
