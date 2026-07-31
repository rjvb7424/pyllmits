"""
analyze_scaling.py
===================

Extra per-experiment plots, on top of the ones in analyze_results.py. Reads a
single run's results.json and writes plots that compare the models tested
*within that experiment* against each other:

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

# z value for a two-sided 95% confidence interval (no scipy dependency).
WILSON_Z_95 = 1.959963984540054


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
#  Plot: success rate with Wilson confidence intervals
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
    experiment_name = get_experiment_name(results, results_path)

    plots_dir = results_path.parent / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    output_paths = {
        "Success rate with Wilson CIs": plots_dir / "success_rate_confidence_intervals.png",
    }

    plot_success_rate_confidence_intervals(results, output_paths["Success rate with Wilson CIs"], experiment_name)

    print("\nFigures written:")
    for label, path in output_paths.items():
        print(f"  {label}: {path}")


if __name__ == "__main__":
    main()
