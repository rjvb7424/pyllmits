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
  * accuracy_by_model_of_<name>.png     - accuracy ranked best-to-worst
  * accuracy_vs_tokens_of_<name>.png    - accuracy vs average token spend
  * accuracy_vs_time_of_<name>.png      - accuracy vs average response time
  * elapsed_time_by_model_of_<name>.png - average response time per model
  * tokens_by_model_of_<name>.png       - average token consumption per model
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
              "accuracy_vs_tokens", "accuracy_vs_time", "elapsed_time_by_model",
              "tokens_by_model")


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


def plot_accuracy_by_folds(rows, out: Path, experiment_name: str) -> None:
    """Accuracy against how many times the paper was folded - the difficulty
    curve, one line per model.

    This is the plot a fold-range run exists for: each extra fold doubles the
    layers a solver has to unfold mentally, so a model that's really reasoning
    about the geometry should slide downward as folds increase, while one that
    was pattern-matching (or guessing) sits flat near the 20% five-choice
    chance line from the start.

    Trials are grouped by their own recorded "num_folds", so this works
    whatever the run swept - and a run that only ever used one fold count
    simply plots one point per model.
    """
    by_model: dict[str, dict[int, list[int]]] = {}
    for r in rows:
        folds = r.get("num_folds")
        if folds is None:
            continue          # pre-fold-count trial data; nothing to place it at
        m = r.get("model_version", "unknown")
        by_model.setdefault(m, {}).setdefault(int(folds), []).append(1 if r["is_correct"] else 0)

    fold_values = sorted({f for per_folds in by_model.values() for f in per_folds})
    colors = model_color_map(rows)

    fig, ax = plt.subplots(figsize=(10, 6.5))
    if not fold_values:
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

    for model in sorted(by_model, key=overall):
        per_folds = by_model[model]
        xs = [f for f in fold_values if f in per_folds]
        ys = [100 * sum(per_folds[f]) / len(per_folds[f]) for f in xs]
        ax.plot(xs, ys, marker="o", markersize=5, linewidth=1.8,
                color=colors[model], label=model, alpha=0.9, zorder=3)

    ax.axhline(20, linestyle="--", linewidth=1, color="#898781", label="Chance (20%)")
    ax.set_xticks(fold_values)
    ax.set_xticklabels([str(f) for f in fold_values])
    ax.set_xlabel("Number of folds (how many times the paper was folded)",
                  color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Accuracy (% of answers correct)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"Accuracy by number of folds of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    # Paper size is derived from the fold count, so say what the sheet grew
    # to across the x axis - it's the other thing that changed along it, and
    # it's why the prompts get longer toward the right.
    ax.annotate(f"Trials per point: {_trials_per_point(by_model, fold_values)}  |  "
                f"{_paper_size_summary(rows, fold_values)}",
                xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=9, color=LABEL_GRAY)
    ax.set_ylim(-5, 110)
    ax.margins(x=0.06)
    ax.grid(True, alpha=0.3)
    # Outside the axes on the right: a run can hold a dozen-plus models, and an
    # in-axes legend that size covers the lines it's labelling.
    ax.legend(fontsize=8, loc="center left", bbox_to_anchor=(1.01, 0.5),
              frameon=False)
    _finish(fig, ax, out, rotate_xticks=False)


def _trials_per_point(by_model: dict, fold_values: list[int]) -> str:
    """How many trials each point averages over - one number when every model
    ran the same amount at every fold count, a range when they differ (a run
    stopped partway, or a model added late)."""
    counts = {len(per_folds[f]) for per_folds in by_model.values()
              for f in fold_values if f in per_folds}
    if len(counts) == 1:
        return str(counts.pop())
    return f"{min(counts)}-{max(counts)}"


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


def _paper_size_summary(rows, fold_values: list[int]) -> str:
    """How the paper grew across the x axis, in one short phrase - listing
    every fold count separately gets unreadable past a few of them."""
    first, last = _paper_size_label(rows, fold_values[0]), _paper_size_label(rows, fold_values[-1])
    if len(fold_values) == 1 or first == last:
        return f"paper {first}"
    return f"paper {first} at {fold_values[0]} folds, up to {last} at {fold_values[-1]}"


def plot_accuracy_by_model(rows, out: Path, experiment_name: str) -> None:
    """Accuracy broken down by model, ranked best-to-worst. Useful for
    comparing model performance."""
    by_model: dict[str, list[int]] = {}
    for r in rows:
        m = r.get("model_version", "unknown")
        by_model.setdefault(m, []).append(1 if r["is_correct"] else 0)

    # Sort the models by accuracy, so the best model ends up at the top of the chart.
    ranked = sorted(by_model.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    models = [m for m, _ in ranked]
    accuracies = [100 * sum(flags) / len(flags) for _, flags in ranked]
    sample_sizes = [len(flags) for _, flags in ranked]
    colors_map = model_color_map(rows)
    colors = [colors_map[m] for m in models]

    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.6 * len(models) + 1)))
    bars = ax.barh(models, accuracies, color=colors)
    for bar, acc, n_samples in zip(bars, accuracies, sample_sizes):
        ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2,
                f"{acc:.0f}%", va="center", fontsize=9, color="#52514e")
    ax.axvline(20, linestyle="--", linewidth=1, color="#898781", label="Chance (20%)")
    ax.set_xlabel("Accuracy (% of answers correct)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Model (LLM model used)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"Accuracy by model of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    ax.set_xlim(0, 110)
    ax.legend(fontsize=9, loc="lower right")
    _finish(fig, ax, out, rotate_xticks=False)


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
    run has. Ranked so the value increases up the chart."""
    by_model: dict[str, list[float]] = {}
    for r in rows:
        m = r.get("model_version", "unknown")
        by_model.setdefault(m, []).append(float(r.get(field) or 0))

    ranked = sorted(by_model.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    models = [m for m, _ in ranked]
    averages = [sum(v) / len(v) for _, v in ranked]
    colors_map = model_color_map(rows)
    colors = [colors_map[m] for m in models]
    xmax = max(averages, default=0) or 1.0

    fig, ax = plt.subplots(figsize=(8, max(3.5, 0.6 * len(models) + 1)))
    bars = ax.barh(models, averages, color=colors)
    for bar, v in zip(bars, averages):
        ax.text(bar.get_width() + 0.01 * xmax, bar.get_y() + bar.get_height() / 2,
                fmt(v), va="center", fontsize=9, color="#52514e")
    ax.set_xlabel(xlabel, color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Model (LLM model used)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"{metric} of {display_name(experiment_name)} experiment",
                 fontsize=13, pad=28)
    ax.set_xlim(0, 1.15 * xmax)
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
        "accuracy_vs_tokens": plot_accuracy_vs_tokens,
        "accuracy_vs_time": plot_accuracy_vs_time,
        "elapsed_time_by_model": plot_elapsed_time_by_model,
        "tokens_by_model": plot_tokens_by_model,
    }
    plots_dir.mkdir(parents=True, exist_ok=True)
    for kind in PLOT_KINDS:
        plotters[kind](rows, plots_dir / plot_filename(kind, slug), slug)
    # Superseded plot kinds (e.g. the old combined accuracy_vs_cost panel) -
    # remove stale copies so they don't linger in the Studio's graphs tab.
    for stale_kind in ("accuracy_vs_cost",):
        stale = plots_dir / plot_filename(stale_kind, slug)
        if stale.exists():
            stale.unlink()
