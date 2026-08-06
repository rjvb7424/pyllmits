"""
llmits.paperfold.analysis
=========================

Reads a paper-folding run's results.json and writes plots visualising how
well each model solved the puzzle. Ported from the original prototype's
analyze_results.py; the plotting logic itself is unchanged, only:
  * results.json is now nested by model (matching the rest of this project's
    convention) instead of one flat list, so flatten() reconstructs the flat
    per-trial view every plot function still expects.
  * model_color_map()/_detect_provider() prefer the real backend field
    (populated by paperfold/runner.py) over guessing a provider from the
    model name - more reliable, and it generalises to any backend models/
    supports without needing a new regex every time.

Plots are written to <run_dir>/plots/ as <kind>_of_<name>.png, matching the
naming convention analyze_results.py (Crafter's) already uses:
  * letter_distribution_of_<name>.png - predicted vs correct answer letter
  * accuracy_by_model_of_<name>.png   - accuracy ranked best-to-worst
  * accuracy_vs_cost_of_<name>.png    - accuracy vs tokens spent / time spent
  * elapsed_time_by_model_of_<name>.png - average response time per model
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

# The letters used for the candidates in the spatial visualisation test.
LETTERS = ["A", "B", "C", "D", "E"]

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

PLOT_KINDS = ("letter_distribution", "accuracy_by_model", "accuracy_vs_cost", "elapsed_time_by_model")


def plot_filename(kind: str, name_slug: str) -> str:
    """Filename for a plot, e.g. accuracy_by_model_of_my_run.png."""
    return f"{kind}_of_{name_slug}.png"


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


def _finish(fig, out) -> None:
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

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([i - width / 2 for i in x], predicted_vals, width, label="Predicted", color="#2a78d6")
    ax.bar([i + width / 2 for i in x], correct_vals, width, label="Correct", color="#eda100")
    ax.set_xticks(list(x))
    ax.set_xticklabels(LETTERS)
    ax.set_ylabel("Count")
    ax.set_title(f"Predicted vs correct answer letter of {experiment_name}")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    _finish(fig, out)


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

    fig, ax = plt.subplots(figsize=(8, max(3, 0.6 * len(models))))
    bars = ax.barh(models, accuracies, color=colors)
    for bar, acc, n_samples in zip(bars, accuracies, sample_sizes):
        ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2,
                f"{acc:.0f}%", va="center", fontsize=9, color="#52514e")
    ax.axvline(20, linestyle="--", linewidth=1, color="#898781", label="Chance (20%)")
    ax.set_xlabel("Accuracy (%)")
    ax.set_title(f"Accuracy by model of {experiment_name}")
    ax.set_xlim(0, 110)
    ax.legend(fontsize=9, loc="lower right")
    _finish(fig, out)


def plot_accuracy_vs_cost(rows, out: Path, experiment_name: str) -> None:
    """The efficiency view: accuracy vs how much the model spent to get
    there (tokens and time). One point per model, bubble size = number
    of trials. Top-left = accurate AND cheap (good). Bottom-right =
    expensive AND wrong (bad)."""
    by_model: dict[str, list[dict]] = {}
    for r in rows:
        m = r.get("model_version", "unknown")
        by_model.setdefault(m, []).append(r)

    models = sorted(by_model.keys())
    colors = model_color_map(rows)

    fig, (ax_tokens, ax_time) = plt.subplots(1, 2, figsize=(13, 5.5))

    for ax, field, xlabel in [
        (ax_tokens, "total_tokens", "Avg total tokens per trial"),
        (ax_time, "elapsed_seconds", "Avg response time (s) per trial"),
    ]:
        for m in models:
            rs = by_model[m]
            acc = 100 * sum(1 for r in rs if r["is_correct"]) / len(rs)
            avg_cost = sum((r.get(field) or 0) for r in rs) / len(rs)
            n = len(rs)
            ax.scatter(avg_cost, acc, s=max(80, 25 * n), color=colors[m],
                       alpha=0.8, edgecolors="white", linewidths=1, zorder=3)
            ax.annotate(m, (avg_cost, acc), textcoords="offset points",
                        xytext=(6, 6), fontsize=8, color="#52514e")
        ax.axhline(20, linestyle="--", linewidth=1, color="#898781")
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Accuracy (%)")
        ax.set_ylim(-5, 105)
        ax.grid(True, alpha=0.3)

    ax_tokens.set_title("Accuracy vs tokens spent")
    ax_time.set_title("Accuracy vs time spent")
    fig.suptitle(f"Efficiency of {experiment_name} (bubble size = number of trials)", fontsize=10, color="#898781")
    _finish(fig, out)


def plot_elapsed_time_by_model(rows, out: Path, experiment_name: str) -> None:
    """Average response time per model, since slower/thinking models
    and fast/lite models are worth comparing directly."""
    by_model: dict[str, list[float]] = {}
    for r in rows:
        m = r.get("model_version", "unknown")
        by_model.setdefault(m, []).append(r.get("elapsed_seconds") or 0)

    models = sorted(by_model.keys())
    avg_elapsed = [sum(by_model[m]) / len(by_model[m]) for m in models]
    colors_map = model_color_map(rows)
    colors = [colors_map[m] for m in models]

    fig, ax = plt.subplots(figsize=(max(6, 1.5 * len(models)), 4))
    ax.bar(models, avg_elapsed, color=colors)
    ax.set_xlabel("Model")
    ax.set_ylabel("Avg elapsed seconds")
    ax.set_title(f"Average response time by model of {experiment_name}")
    ax.tick_params(axis="x", labelrotation=15)
    _finish(fig, out)
