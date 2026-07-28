"""
analyze_scaling.py
===================

Extra per-experiment plots, on top of the ones in analyze_results.py. Reads a
single run's results.json and writes plots that compare the models tested
*within that experiment* against each other:

  * param_count_vs_accuracy.png           - open-weight parameter count (log)
                                             vs accuracy, one point per model
  * accuracy_by_family.png                - per-family distribution of this
                                             experiment's per-trial accuracy
                                             (box + strip), to compare within-
                                             vs between-family variance
  * success_rate_confidence_intervals.png - success rate with a Wilson score
                                             confidence interval per model

Like analyze_results.py, these are written to <run_dir>/plots/ - so each
experiment only ever shows its own models, never another experiment's.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from analyze_results import BAR_COLOR, get_experiment_name, resolve_results_path

# =============================================================================
#  Open-weight parameter counts (billions of parameters)
#
#  TODO: verify every one of these against the model's official model card
#  before using this plot in the paper. Figures for MoE models are TOTAL
#  parameters (not active-per-token) unless noted - that distinction matters
#  for a "parameter count vs accuracy" comparison. Entries left as `None`
#  are ones we don't have a confidently-sourced figure for; fill those in
#  rather than guessing, or the scatter plot will just skip them.
# =============================================================================
MODEL_PARAM_COUNTS: dict[str, float | None] = {
    "microsoft/phi-4":                      14.0,   # dense
    "meta-llama/Llama-3.3-70B-Instruct":    70.0,   # dense
    "Qwen/Qwen3-235B-A22B-Instruct-2507":  235.0,   # MoE, total (22B active)
    "openai/gpt-oss-120b":                 120.0,   # MoE, total (~5.1B active)
    "deepseek-ai/DeepSeek-R1":             671.0,   # MoE, total (37B active)
    "deepseek-ai/DeepSeek-V3.2":           None,    # unverified - fill in
    "deepseek-ai/DeepSeek-V4-Pro":         None,    # unverified - fill in
    "deepseek-ai/DeepSeek-V4-Flash":       None,    # unverified - fill in
}

# Backends whose weights are open (self-hosted or hosted-open); everything
# else (openai, gemini) is closed-weight and excluded from the scatter plot.
OPEN_WEIGHT_BACKENDS = {"huggingface-api", "huggingface"}

# =============================================================================
#  Model family grouping - edit/extend as new models are tested
# =============================================================================
FAMILY_MAP: dict[str, str] = {
    "gpt-5.4-2026-03-05":                    "GPT-5.x",
    "gpt-5.6-sol":                           "GPT-5.x",
    "gpt-5.6-terra":                         "GPT-5.x",
    "gpt-5.6-luna":                          "GPT-5.x",
    "gpt-4o":                                "GPT-4o",
    "gpt-4o-mini":                           "GPT-4o",
    "o3-2025-04-16":                         "o-series",
    "o4-mini":                               "o-series",
    "openai/gpt-oss-120b":                   "gpt-oss",
    "deepseek-ai/DeepSeek-R1":               "DeepSeek",
    "deepseek-ai/DeepSeek-V3.2":             "DeepSeek",
    "deepseek-ai/DeepSeek-V4-Pro":           "DeepSeek",
    "deepseek-ai/DeepSeek-V4-Flash":         "DeepSeek",
    "Qwen/Qwen3-235B-A22B-Instruct-2507":    "Qwen",
    "Qwen/Qwen2.5-7B-Instruct":              "Qwen",
    "meta-llama/Llama-3.3-70B-Instruct":     "Llama",
    "meta-llama/Llama-3.2-3B-Instruct":      "Llama",
    "microsoft/phi-4":                       "Phi",
    "gemini-2.5-flash":                      "Gemini",
    "gemini-2.5-pro":                        "Gemini",
    "gemini-2.0-flash":                      "Gemini",
    "heuristic-baseline":                    "Baseline",
}

# Models that don't match FAMILY_MAP fall into this bucket rather than
# crashing the plot - main() warns about them so they can be added above.
UNMAPPED_FAMILY = "Other"

# z value for a two-sided 95% confidence interval (no scipy dependency).
WILSON_Z_95 = 1.959963984540054


# =============================================================================
#  Data loading
# =============================================================================
def collect_model_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per model in this experiment that has at least one recorded trial."""
    rows: list[dict[str, Any]] = []
    for model_name, record in results.get("models", {}).items():
        trials = record.get("trials", [])
        if not trials:
            continue
        n_success = sum(1 for t in trials if t.get("success"))
        rows.append({
            "model": model_name,
            "backend": record.get("backend"),
            "n_trials": len(trials),
            "n_success": n_success,
            "accuracy_pct": 100.0 * n_success / len(trials),
        })
    return rows


def resolve_family(model_name: str) -> str:
    return FAMILY_MAP.get(model_name, UNMAPPED_FAMILY)


def wilson_score_interval(successes: int, n: int, z: float = WILSON_Z_95) -> tuple[float, float, float]:
    """Wilson score confidence interval for a binomial proportion.

    More reliable than the naive normal approximation at small n (a handful
    of trials per model here): it can't fall outside [0, 1] and isn't
    overconfident at extreme rates like 8/8 or 0/8.
    Returns (point_estimate, lower_bound, upper_bound), all proportions in [0, 1].
    """
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = successes / n
    denominator = 1.0 + z ** 2 / n
    center = (p_hat + z ** 2 / (2 * n)) / denominator
    margin = (z / denominator) * np.sqrt(p_hat * (1 - p_hat) / n + z ** 2 / (4 * n ** 2))
    return p_hat, max(0.0, center - margin), min(1.0, center + margin)


# =============================================================================
#  Plot 1: parameter count vs accuracy (open-weight models in this experiment)
# =============================================================================
def plot_param_count_vs_accuracy(rows: list[dict[str, Any]], out: Path, experiment_name: str) -> None:
    points = [
        r for r in rows
        if r["backend"] in OPEN_WEIGHT_BACKENDS
        and MODEL_PARAM_COUNTS.get(r["model"]) is not None
    ]

    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    if not points:
        ax.text(0.5, 0.5,
                "No open-weight models with a known parameter count in this run.\n"
                "Fill in MODEL_PARAM_COUNTS at the top of analyze_scaling.py.",
                ha="center", va="center", fontsize=11, color="#555555")
        ax.set_axis_off()
        ax.set_title(f"Parameter count vs accuracy of {experiment_name}")
        fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
        return

    families = sorted({resolve_family(p["model"]) for p in points})
    cmap = plt.get_cmap("tab10" if len(families) <= 10 else "tab20")
    colour_of = {f: cmap(i % cmap.N) for i, f in enumerate(families)}

    # Two different models can share the same declared parameter count (or
    # round to the same accuracy) and would otherwise stack on top of each
    # other, labels included. Fan out same-coordinate points symmetrically -
    # deterministic, so the figure is reproducible.
    clusters: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for p in sorted(points, key=lambda p: p["model"]):
        key = (MODEL_PARAM_COUNTS[p["model"]], round(p["accuracy_pct"], 1))
        clusters.setdefault(key, []).append(p)

    for family in families:
        subset = [p for p in points if resolve_family(p["model"]) == family]
        xs, ys, labels, label_offsets = [], [], [], []
        for p in subset:
            key = (MODEL_PARAM_COUNTS[p["model"]], round(p["accuracy_pct"], 1))
            cluster = clusters[key]
            slot = cluster.index(p)
            spread = (slot - (len(cluster) - 1) / 2) * 0.05
            xs.append(key[0] * (1 + spread))
            ys.append(p["accuracy_pct"])
            labels.append(p["model"].split("/")[-1])
            label_offsets.append(4 + 11 * slot)
        ax.scatter(xs, ys, color=colour_of[family], s=80, edgecolor="white",
                   linewidth=0.6, alpha=0.9, label=family, zorder=3)
        for x, y, label, dy in zip(xs, ys, labels, label_offsets):
            ax.annotate(label, (x, y), fontsize=7, color="#555555",
                        xytext=(4, dy), textcoords="offset points")

    ax.set_xscale("log")
    ax.set_xlabel("Parameter count (billions, log scale)")
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(-5, 105)
    ax.set_title(f"Parameter count vs accuracy of {experiment_name}\n(open-weight models only)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(title="family", fontsize=8, loc="best", framealpha=0.9)
    fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)


# =============================================================================
#  Plot 2: accuracy by model family (box + strip)
# =============================================================================
def plot_accuracy_by_family(results: dict[str, Any], out: Path, experiment_name: str) -> None:
    # Per-trial (not per-model) success values: with usually one model per
    # family in a single experiment, per-model would give each family a
    # single point and no visible within-family spread at all.
    by_family: dict[str, list[float]] = {}
    for model_name, record in results.get("models", {}).items():
        family = resolve_family(model_name)
        for trial in record.get("trials", []):
            by_family.setdefault(family, []).append(100.0 if trial.get("success") else 0.0)

    fig, ax = plt.subplots(figsize=(max(6, 1.4 * max(len(by_family), 1)), 5.5))
    if not by_family:
        ax.text(0.5, 0.5, "No completed trials in this run.",
                ha="center", va="center", fontsize=11, color="#555555")
        ax.set_axis_off()
        ax.set_title(f"Accuracy by model family of {experiment_name}")
        fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
        return

    # Order families by descending median so the between-family comparison
    # reads left-to-right as "best to worst" rather than alphabetically.
    families = sorted(by_family, key=lambda f: -float(np.median(by_family[f])))
    data = [by_family[f] for f in families]

    cmap = plt.get_cmap("tab10" if len(families) <= 10 else "tab20")
    colour_of = {f: cmap(i % cmap.N) for i, f in enumerate(families)}

    box = ax.boxplot(data, tick_labels=families, patch_artist=True, widths=0.55,
                      showmeans=False, showfliers=False, medianprops={"color": "#222222"})
    for patch, family in zip(box["boxes"], families):
        patch.set_facecolor(colour_of[family])
        patch.set_alpha(0.35)

    rs = np.random.RandomState(0)
    for i, family in enumerate(families):
        values = by_family[family]
        jitter = (rs.rand(len(values)) - 0.5) * 0.3
        ax.scatter(np.full(len(values), i + 1) + jitter, values,
                   color=colour_of[family], s=32, edgecolor="white",
                   linewidth=0.5, zorder=3)

    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(-5, 105)
    ax.set_title(f"Accuracy by model family of {experiment_name}\n"
                 "(box = within-family spread, position = between-family gap)")
    ax.spines[["top", "right"]].set_visible(False)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)


# =============================================================================
#  Plot 3: success rate with Wilson confidence intervals
# =============================================================================
def plot_success_rate_confidence_intervals(results: dict[str, Any], out: Path, experiment_name: str) -> None:
    names, rates, lower_err, upper_err, n_labels = [], [], [], [], []
    for name, record in results.get("models", {}).items():
        trials = record.get("trials", [])
        n = len(trials)
        if n == 0:
            continue
        successes = sum(1 for t in trials if t.get("success"))
        p_hat, lower, upper = wilson_score_interval(successes, n)
        names.append(name)
        rates.append(100 * p_hat)
        lower_err.append(100 * (p_hat - lower))
        upper_err.append(100 * (upper - p_hat))
        n_labels.append(n)

    fig, ax = plt.subplots(figsize=(max(6, 1.6 * max(len(names), 1)), 5))
    if not names:
        ax.text(0.5, 0.5, "No completed trials in this run.",
                ha="center", va="center", fontsize=11, color="#555555")
        ax.set_axis_off()
        ax.set_title(f"Success rate of {experiment_name}")
        fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
        return

    x = np.arange(len(names))
    ax.bar(x, rates, color=BAR_COLOR, yerr=[lower_err, upper_err], capsize=4, ecolor="#333333")
    for i, n in enumerate(n_labels):
        ax.text(i, 2, f"n={n}", ha="center", va="bottom", fontsize=8, color="#555555")
    ax.set_xticks(x, names, rotation=20, ha="right")
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(0, 105)
    ax.set_title(f"Success rate of {experiment_name}\n(error bars: 95% Wilson score interval)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)


# =============================================================================
#  Entry point
# =============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Per-experiment scaling/family/CI plots.")
    ap.add_argument("config", nargs="?", default="config.yaml")
    ap.add_argument("--results", help="path to results.json; overrides the config path")
    args = ap.parse_args()

    results_path = resolve_results_path(args)
    results = json.loads(results_path.read_text(encoding="utf-8"))
    rows = collect_model_rows(results)
    experiment_name = get_experiment_name(results, results_path)

    unmapped = sorted({r["model"] for r in rows if resolve_family(r["model"]) == UNMAPPED_FAMILY})
    if unmapped:
        print(f"Note: these models aren't in FAMILY_MAP and were grouped under "
              f"'{UNMAPPED_FAMILY}': {', '.join(unmapped)}")

    missing_param_counts = sorted({
        r["model"] for r in rows
        if r["backend"] in OPEN_WEIGHT_BACKENDS and MODEL_PARAM_COUNTS.get(r["model"]) is None
    })
    if missing_param_counts:
        print(f"Note: these open-weight models have no verified parameter count in "
              f"MODEL_PARAM_COUNTS and were skipped from the scatter plot: "
              f"{', '.join(missing_param_counts)}")

    plots_dir = results_path.parent / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "Parameter count vs accuracy": plots_dir / "param_count_vs_accuracy.png",
        "Accuracy by model family": plots_dir / "accuracy_by_family.png",
        "Success rate with Wilson CIs": plots_dir / "success_rate_confidence_intervals.png",
    }

    plot_param_count_vs_accuracy(rows, output_paths["Parameter count vs accuracy"], experiment_name)
    plot_accuracy_by_family(results, output_paths["Accuracy by model family"], experiment_name)
    plot_success_rate_confidence_intervals(results, output_paths["Success rate with Wilson CIs"], experiment_name)

    print("\nFigures written:")
    for label, path in output_paths.items():
        print(f"  {label}: {path}")


if __name__ == "__main__":
    main()
