"""
analyze_scaling.py
===================

Cross-experiment analysis, on top of the per-experiment plots in
analyze_results.py. Reads every runs/*/results.json and writes plots that
compare models against each other rather than within a single run:

  * param_count_vs_accuracy.png          - open-weight parameter count (log)
                                            vs accuracy, one point per model
                                            per experiment it appears in
  * accuracy_by_family.png               - per-family distribution of
                                            per-model accuracy (box + strip),
                                            to compare within- vs between-
                                            family variance
  * success_rate_confidence_intervals.png - success rate with Wilson score
                                            confidence intervals for the two
                                            small-n Crafter experiments named
                                            in EXPERIMENTS_FOR_CI

Figures are written to OUTPUT_DIR (analysis_output/ by default).
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

from analyze_results import BAR_COLOR, get_experiment_name

# =============================================================================
#  Paths
# =============================================================================
RUNS_DIR = Path("runs")
OUTPUT_DIR = Path("analysis_output")

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

# =============================================================================
#  Crafter experiments to compute Wilson confidence intervals for
# =============================================================================
EXPERIMENTS_FOR_CI = ["tree_opening_12x12", "maze_field_18x18"]

# z value for a two-sided 95% confidence interval (no scipy dependency).
WILSON_Z_95 = 1.959963984540054


# =============================================================================
#  Data loading
# =============================================================================
def load_all_results(runs_dir: Path) -> dict[str, dict[str, Any]]:
    """Load every experiment's results.json under runs_dir.

    Returns {experiment_folder_name: {"results": ..., "display_name": ...}}.
    """
    all_results: dict[str, dict[str, Any]] = {}
    for results_path in sorted(runs_dir.glob("*/results.json")):
        results = json.loads(results_path.read_text())
        all_results[results_path.parent.name] = {
            "results": results,
            "display_name": get_experiment_name(results, results_path),
        }
    return all_results


def collect_model_experiment_rows(all_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (experiment, model) that has at least one recorded trial."""
    rows: list[dict[str, Any]] = []
    for experiment_folder, entry in all_results.items():
        results = entry["results"]
        for model_name, record in results.get("models", {}).items():
            trials = record.get("trials", [])
            if not trials:
                continue
            n_success = sum(1 for t in trials if t.get("success"))
            rows.append({
                "experiment_folder": experiment_folder,
                "experiment_display": entry["display_name"],
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
#  Plot 1: parameter count vs accuracy (open-weight models only)
# =============================================================================
def plot_param_count_vs_accuracy(rows: list[dict[str, Any]], out: Path) -> None:
    points = [
        r for r in rows
        if r["backend"] in OPEN_WEIGHT_BACKENDS
        and MODEL_PARAM_COUNTS.get(r["model"]) is not None
    ]

    fig, ax = plt.subplots(figsize=(8, 5.5))
    if not points:
        ax.text(0.5, 0.5,
                "No open-weight models with a known parameter count yet.\n"
                "Fill in MODEL_PARAM_COUNTS at the top of this file.",
                ha="center", va="center", fontsize=11, color="#555555")
        ax.set_axis_off()
        ax.set_title("Parameter count vs accuracy (open-weight models)")
        fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
        return

    experiments = sorted({p["experiment_display"] for p in points})
    cmap = plt.get_cmap("tab10" if len(experiments) <= 10 else "tab20")
    colour_of = {e: cmap(i % cmap.N) for i, e in enumerate(experiments)}

    # Several (model, experiment) pairs can land on the exact same
    # (param count, accuracy) coordinate (e.g. two 0%-accuracy runs of the
    # same model) and would otherwise silently stack on top of each other,
    # with their labels drawn on top of one another too. Group points by
    # their true (unjittered) coordinate and fan each cluster out
    # symmetrically around it - deterministic, so the figure is reproducible.
    clusters: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for p in sorted(points, key=lambda p: (p["experiment_display"], p["model"])):
        key = (MODEL_PARAM_COUNTS[p["model"]], round(p["accuracy_pct"], 1))
        clusters.setdefault(key, []).append(p)

    for experiment in experiments:
        subset = [p for p in points if p["experiment_display"] == experiment]
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
        ax.scatter(xs, ys, color=colour_of[experiment], s=80, edgecolor="white",
                   linewidth=0.6, alpha=0.85, label=experiment, zorder=3)
        for x, y, label, dy in zip(xs, ys, labels, label_offsets):
            ax.annotate(label, (x, y), fontsize=7, color="#555555",
                        xytext=(4, dy), textcoords="offset points")

    ax.set_xscale("log")
    ax.set_xlabel("Parameter count (billions, log scale)")
    ax.set_ylabel("Accuracy (%)")
    ax.set_ylim(-5, 105)
    ax.set_title("Parameter count vs accuracy (open-weight models)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(title="experiment", fontsize=8, loc="best", framealpha=0.9)
    fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)


# =============================================================================
#  Plot 2: accuracy by model family (box + strip)
# =============================================================================
def plot_accuracy_by_family(rows: list[dict[str, Any]], out: Path) -> None:
    by_family: dict[str, list[float]] = {}
    for r in rows:
        by_family.setdefault(resolve_family(r["model"]), []).append(r["accuracy_pct"])

    # Order families by descending median so the between-family comparison
    # reads left-to-right as "best to worst" rather than alphabetically.
    families = sorted(by_family, key=lambda f: -float(np.median(by_family[f])))
    data = [by_family[f] for f in families]

    fig, ax = plt.subplots(figsize=(max(6, 1.4 * len(families)), 5.5))
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
    ax.set_title("Accuracy by model family\n(box = within-family spread, position = between-family gap)")
    ax.spines[["top", "right"]].set_visible(False)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)


# =============================================================================
#  Plot 3: success rate with Wilson confidence intervals (Crafter experiments)
# =============================================================================
def plot_success_rate_confidence_intervals(
    all_results: dict[str, dict[str, Any]], experiment_folders: list[str], out: Path,
) -> None:
    available = [f for f in experiment_folders if f in all_results]
    fig, axes = plt.subplots(1, max(len(available), 1), figsize=(7 * max(len(available), 1), 5),
                              squeeze=False)
    axes = axes[0]

    if not available:
        axes[0].text(0.5, 0.5, "None of EXPERIMENTS_FOR_CI have results.json yet.",
                     ha="center", va="center", fontsize=11, color="#555555")
        axes[0].set_axis_off()
        fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
        return

    for ax, experiment_folder in zip(axes, available):
        entry = all_results[experiment_folder]
        models = entry["results"].get("models", {})
        names, rates, lower_err, upper_err = [], [], [], []
        for name, record in models.items():
            trials = record.get("trials", [])
            n = len(trials)
            successes = sum(1 for t in trials if t.get("success"))
            if n == 0:
                continue
            p_hat, lower, upper = wilson_score_interval(successes, n)
            names.append(name)
            rates.append(100 * p_hat)
            lower_err.append(100 * (p_hat - lower))
            upper_err.append(100 * (upper - p_hat))

        if not names:
            ax.text(0.5, 0.5, "No completed trials.", ha="center", va="center",
                    color="#555555")
            ax.set_axis_off()
            continue

        x = np.arange(len(names))
        ax.bar(x, rates, color=BAR_COLOR, yerr=[lower_err, upper_err],
               capsize=4, ecolor="#333333")
        ax.set_xticks(x, names, rotation=20, ha="right")
        ax.set_ylabel("Success rate (%)")
        ax.set_ylim(0, 105)
        n_trials_seen = {len(record.get("trials", [])) for record in models.values()
                          if record.get("trials")}
        n_label = ", ".join(str(n) for n in sorted(n_trials_seen))
        ax.set_title(f"{entry['display_name']}\n(n={n_label} trials/model, 95% Wilson CI)")
        ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)


# =============================================================================
#  Entry point
# =============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-experiment scaling/family/CI plots.")
    ap.add_argument("--runs-dir", default=str(RUNS_DIR), help="directory containing runs/*/results.json")
    ap.add_argument("--output-dir", default=str(OUTPUT_DIR), help="directory to write PNGs to")
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_results = load_all_results(runs_dir)
    if not all_results:
        print(f"No runs/*/results.json found under {runs_dir}/ - nothing to plot.")
        return
    rows = collect_model_experiment_rows(all_results)

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

    output_paths = {
        "Parameter count vs accuracy": output_dir / "param_count_vs_accuracy.png",
        "Accuracy by model family": output_dir / "accuracy_by_family.png",
        "Success rate with Wilson CIs": output_dir / "success_rate_confidence_intervals.png",
    }

    plot_param_count_vs_accuracy(rows, output_paths["Parameter count vs accuracy"])
    plot_accuracy_by_family(rows, output_paths["Accuracy by model family"])
    plot_success_rate_confidence_intervals(all_results, EXPERIMENTS_FOR_CI,
                                            output_paths["Success rate with Wilson CIs"])

    print("\nFigures written:")
    for label, path in output_paths.items():
        print(f"  {label}: {path}")


if __name__ == "__main__":
    main()
