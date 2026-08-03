"""
analyze_results.py
==================

Reads a run's results.json and writes plots visualising how well each model
achieved the objective. The experiment name appears in every title (underscores
shown as spaces). Plots are written to <run_dir>/plots/:

  * success_rate.png      - fraction of trials solved, per model
  * think_time.png        - mean seconds per decision, per model
  * success_matrix.png    - model x trial grid, solved/failed/not run
  * turns_to_solve.png    - model x trial grid, turns taken on solved trials
  * turns_to_fail.png     - model x trial grid, turns taken on failed trials
  * tokens_to_solve.png   - model x trial grid, tokens used on solved trials
  * tokens_to_fail.png    - model x trial grid, tokens used on failed trials
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

BAR_COLOR = "#4c72b0"
THINK_TIME_COLOR = "#8172b3"
OK_COLOR = "#2f9e6f"
FAIL_COLOR = "#c44e52"
GRID_BG = "#e9e6df"
NOT_RUN_COLOR = "#c9ccd6"
LABEL_GRAY = "#8a8a8a"


def get_experiment_name(results: dict[str, Any], results_path: Path | None = None) -> str:
    """Extract the experiment name and replace underscores with spaces.

    The run folder name (results_path.parent) is authoritative when available:
    config.py's Config.run_dir is always output_dir/experiment.name, and
    renaming a config in the Studio moves its run folder to match - so the
    folder always reflects the *current* name. The "experiment" field stored
    inside results.json, by contrast, is written once when the run is first
    created (see experiment.py) and never updated afterward, so it goes stale
    the moment a config is renamed. Prefer the folder name; fall back to the
    stored fields only when no path is available (e.g. a bare results dict).
    """
    if results_path is not None:
        name = results_path.parent.name
    else:
        experiment = results.get("experiment", {})
        if isinstance(experiment, dict):
            name = experiment.get("name")
        elif isinstance(experiment, str):
            name = experiment
        else:
            name = None
        name = name or results.get("experiment_name") or results.get("name")
    if not name:
        name = "experiment"
    return str(name).replace("_", " ").strip()


def summarise(results: dict[str, Any]) -> list[dict[str, Any]]:
    """One statistics row per model."""
    num_trials = int(results.get("num_trials", 0))
    rows: list[dict[str, Any]] = []
    for name, record in results.get("models", {}).items():
        trials = record.get("trials", [])
        successes = [t for t in trials if bool(t.get("success", False))]
        solve_turns = [
            int(t["success_turn"]) + 1 for t in successes
            if t.get("success_turn") is not None
        ]
        think_times = [
            float(turn["think_seconds"]) for t in trials
            for turn in t.get("turns", []) if turn.get("think_seconds") is not None
        ]
        rows.append({
            "name": name,
            "error": record.get("error"),
            "n_trials": len(trials),
            "n_success": len(successes),
            "success_rate": len(successes) / len(trials) if trials else 0.0,
            "solve_turns": solve_turns,
            "mean_solve_turns": float(np.mean(solve_turns)) if solve_turns else None,
            "mean_think": float(np.mean(think_times)) if think_times else None,
            "per_trial_success": [bool(t.get("success", False)) for t in trials],
            "expected_trials": num_trials,
        })
    return rows


def plot_success_rate(rows, out, experiment_name):
    names = [r["name"] for r in rows]
    values = [100 * r["success_rate"] for r in rows]
    not_run = [bool(r["error"]) or r["n_trials"] == 0 for r in rows]
    colours = [NOT_RUN_COLOR if nr else BAR_COLOR for nr in not_run]
    fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(names)), 4.5))
    ax.bar(names, values, color=colours)
    for i, r in enumerate(rows):
        if not_run[i]:
            ax.text(i, 2, "error" if r["error"] else "not run",
                    ha="center", va="bottom", fontsize=9, color="#555555")
        else:
            ax.text(i, values[i] + 1, f"{values[i]:.0f}%",
                    ha="center", va="bottom", fontsize=9)
    ax.set_xlabel("Model (LLM model used)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Success rate (% of trials solved)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylim(0, 105)
    ax.set_title(f"Success rate of {experiment_name} experiment", fontsize=13, pad=28)
    _finish(fig, ax, out)


def plot_think_time(rows, out, experiment_name):
    names = [r["name"] for r in rows]
    means = [r["mean_think"] if r["mean_think"] is not None else 0 for r in rows]
    fig, ax = plt.subplots(figsize=(max(6, 1.6 * len(names)), 4.5))
    ax.bar(names, means, color=THINK_TIME_COLOR)
    for i, v in enumerate(means):
        ax.text(i, v, f"{v:.2f}s" if v > 0 else "-", ha="center", va="bottom", fontsize=9)
    ax.set_xlabel("Model (LLM model used)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Average think time (seconds per turn)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"Average thinking time of {experiment_name} experiment", fontsize=13, pad=28)
    _finish(fig, ax, out)


def plot_success_matrix(rows, out, experiment_name):
    names = [r["name"] for r in rows]
    expected = max((int(r["expected_trials"]) for r in rows), default=0)
    recorded = max((int(r["n_trials"]) for r in rows), default=1)
    # Use whichever is larger: the configured num_trials OR the number actually
    # recorded. On a resumed run the stored num_trials can be stale (e.g. 4 when
    # 8 trials were later added), so keying off it alone would hide real trials.
    n_cols = max(expected, recorded, 1)
    grid = np.full((len(names), n_cols), np.nan)
    for mi, r in enumerate(rows):
        for ti, ok in enumerate(r["per_trial_success"]):
            if ti >= n_cols:
                break
            grid[mi, ti] = 1.0 if ok else 0.0
    fig, ax = plt.subplots(figsize=(max(6, 0.8 * n_cols + 3), max(3, 0.7 * len(names) + 2)))
    cmap = matplotlib.colors.ListedColormap([FAIL_COLOR, OK_COLOR])
    ax.set_facecolor(GRID_BG)
    ax.imshow(np.ma.masked_invalid(grid), cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(n_cols), [f"T{i + 1}" for i in range(n_cols)])
    ax.set_yticks(range(len(names)), names)
    for mi in range(len(names)):
        for ti in range(n_cols):
            v = grid[mi, ti]
            if np.isnan(v):
                continue
            ax.text(ti, mi, "\u2713" if v == 1.0 else "\u2717",
                    ha="center", va="center", color="white", fontsize=11)
    ax.set_xlabel("Trial (number of trials executed)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Model (LLM model used)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(f"Success matrix of {experiment_name} experiment", fontsize=13, pad=30)
    # Anchored with a fixed point offset (not an axes-fraction y like 1.07) so
    # it always lands just above the axes and below the title's own pad,
    # regardless of how tall the figure is (many-model runs made the old
    # fraction-based offset grow past the title's pad and render above it).
    ax.annotate("green for solved, red for failed, blank for not run",
                xy=(0.5, 1.0), xycoords="axes fraction",
                xytext=(0, 8), textcoords="offset points",
                ha="center", va="bottom", fontsize=9.5, color=LABEL_GRAY)
    fig.tight_layout()
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def collect_trial_details(results):
    """Per-model list of per-trial stats: whether it solved, how many turns it
    took, and how many tokens it used (None if that trial has no token data).

    "turns_used" is the same convention as summarise()'s solve_turns: for a
    solved trial it's turns up to and including the solving turn; for a failed
    trial it's every turn the trial ran.
    """
    details: dict[str, list[dict[str, Any]]] = {}
    for name, record in results.get("models", {}).items():
        trials_out = []
        for t in record.get("trials", []):
            turns = t.get("turns", [])
            success = bool(t.get("success", False))
            if success and t.get("success_turn") is not None:
                turns_used = int(t["success_turn"]) + 1
            else:
                turns_used = len(turns)
            tok = [int(x["tokens"]) for x in turns if x.get("tokens") is not None]
            trials_out.append({
                "success": success,
                "turns_used": turns_used,
                "tokens_used": sum(tok) if tok else None,
            })
        details[name] = trials_out
    return details


def _sequential_cmap(colour):
    return matplotlib.colors.LinearSegmentedColormap.from_list("seq", ["#ffffff", colour])


def _plot_trial_grid(details, num_trials, out, *, value_key, keep_success,
                      title, subtitle, cbar_label, colour, value_fmt, empty_message):
    """Model x trial grid, one cell per trial that matches keep_success,
    coloured and annotated by value_key. Mirrors plot_success_matrix's grid
    layout so every per-trial plot in this module reads the same way."""
    names = list(details.keys())
    recorded = max((len(v) for v in details.values()), default=1)
    n_cols = max(int(num_trials), recorded, 1)
    grid = np.full((len(names), n_cols), np.nan)
    for mi, name in enumerate(names):
        for ti, trial in enumerate(details[name]):
            if ti >= n_cols or trial["success"] != keep_success:
                continue
            v = trial[value_key]
            if v is not None:
                grid[mi, ti] = v

    fig, ax = plt.subplots(figsize=(max(6, 0.8 * n_cols + 3), max(3, 0.7 * len(names) + 2)))
    if not np.isfinite(grid).any():
        ax.text(0.5, 0.5, empty_message, ha="center", va="center",
                fontsize=11, color="#555555")
        ax.set_axis_off()
        ax.set_title(title, fontsize=13, pad=14)
        fig.tight_layout(); fig.savefig(out, dpi=130, bbox_inches="tight"); plt.close(fig)
        return

    ax.set_facecolor(GRID_BG)
    masked = np.ma.masked_invalid(grid)
    vmin = float(np.nanmin(grid))
    vmax = float(np.nanmax(grid))
    im = ax.imshow(masked, cmap=_sequential_cmap(colour), aspect="auto", vmin=vmin, vmax=vmax)
    ax.set_xticks(range(n_cols), [f"T{i + 1}" for i in range(n_cols)])
    ax.set_yticks(range(len(names)), names)
    for mi in range(len(names)):
        for ti in range(n_cols):
            v = grid[mi, ti]
            if np.isnan(v):
                continue
            # Base the text colour on the same [vmin, vmax] normalisation the
            # colormap itself uses - not on v/vmax - so a cell that happens to
            # be the grid's minimum (rendered white) never gets white text.
            norm = (v - vmin) / (vmax - vmin) if vmax > vmin else 0.5
            text_colour = "white" if norm > 0.55 else "#222222"
            ax.text(ti, mi, value_fmt(v), ha="center", va="center",
                    color=text_colour, fontsize=10)
    ax.set_xlabel("Trial (number of trials executed)", color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel("Model (LLM model used)", color=LABEL_GRAY, fontsize=10)
    ax.set_title(title, fontsize=13, pad=30)
    # Fixed point offset, not an axes-fraction y - see plot_success_matrix for why.
    ax.annotate(subtitle, xy=(0.5, 1.0), xycoords="axes fraction",
                xytext=(0, 8), textcoords="offset points",
                ha="center", va="bottom", fontsize=9.5, color=LABEL_GRAY)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(cbar_label, color=LABEL_GRAY, fontsize=10)
    cbar.ax.tick_params(colors=LABEL_GRAY, labelsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def plot_turns_to_solve(results, out, experiment_name):
    """Model x trial grid: turns taken on trials that were solved."""
    _plot_trial_grid(
        collect_trial_details(results), results.get("num_trials", 0), out,
        value_key="turns_used", keep_success=True,
        title=f"Turns to solve of {experiment_name} experiment",
        subtitle="blank = trial failed or wasn't run",
        cbar_label="Turns", colour=OK_COLOR,
        value_fmt=lambda v: f"{int(round(v))}",
        empty_message="No solved trials in this run.",
    )


def plot_turns_to_fail(results, out, experiment_name):
    """Model x trial grid: turns taken on trials that failed."""
    _plot_trial_grid(
        collect_trial_details(results), results.get("num_trials", 0), out,
        value_key="turns_used", keep_success=False,
        title=f"Turns to fail of {experiment_name} experiment",
        subtitle="blank = trial solved or wasn't run",
        cbar_label="Turns", colour=FAIL_COLOR,
        value_fmt=lambda v: f"{int(round(v))}",
        empty_message="No failed trials in this run.",
    )


def plot_tokens_to_solve(results, out, experiment_name):
    """Model x trial grid: tokens used on trials that were solved."""
    _plot_trial_grid(
        collect_trial_details(results), results.get("num_trials", 0), out,
        value_key="tokens_used", keep_success=True,
        title=f"Tokens to solve of {experiment_name} experiment",
        subtitle="blank = trial failed, wasn't run, or has no token data",
        cbar_label="Tokens", colour=OK_COLOR,
        value_fmt=lambda v: f"{int(round(v)):,}",
        empty_message="No token data for solved trials in this run.",
    )


def plot_tokens_to_fail(results, out, experiment_name):
    """Model x trial grid: tokens used on trials that failed."""
    _plot_trial_grid(
        collect_trial_details(results), results.get("num_trials", 0), out,
        value_key="tokens_used", keep_success=False,
        title=f"Tokens to fail of {experiment_name} experiment",
        subtitle="blank = trial solved, wasn't run, or has no token data",
        cbar_label="Tokens", colour=FAIL_COLOR,
        value_fmt=lambda v: f"{int(round(v)):,}",
        empty_message="No token data for failed trials in this run.",
    )


def _finish(fig, ax, out):
    ax.spines[["top", "right"]].set_visible(False)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def print_summary(results, rows):
    objective = results.get("objective", {})
    if isinstance(objective, dict):
        objective_name = objective.get("label", objective.get("target", "?"))
    else:
        objective_name = str(objective)
    print(f"\nObjective: {objective_name}")
    print(f"{'model':<34} {'success':>9} {'rate':>7} {'avg turns':>10} {'avg think':>10}")
    print("-" * 74)
    for r in rows:
        turns_text = f"{r['mean_solve_turns']:.1f}" if r["mean_solve_turns"] is not None else "-"
        think_text = f"{r['mean_think']:.2f}s" if r["mean_think"] is not None else "-"
        flag = "  [load error]" if r["error"] else ""
        print(f"{r['name']:<34} {r['n_success']:>4}/{r['n_trials']:<4} "
              f"{100 * r['success_rate']:>6.0f}% {turns_text:>10} {think_text:>10}{flag}")
    print()


def resolve_results_path(args):
    if args.results:
        return Path(args.results)
    from config import load_config
    return load_config(args.config).results_path


def main():
    ap = argparse.ArgumentParser(description="Plot Crafter experiment results.")
    ap.add_argument("config", nargs="?", default="config.yaml")
    ap.add_argument("--results", help="path to results.json; overrides the config path")
    args = ap.parse_args()

    results_path = resolve_results_path(args)
    results = json.loads(results_path.read_text(encoding="utf-8"))
    rows = summarise(results)
    experiment_name = get_experiment_name(results, results_path)

    plots_dir = results_path.parent / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    plot_success_rate(rows, plots_dir / "success_rate.png", experiment_name)
    plot_think_time(rows, plots_dir / "think_time.png", experiment_name)
    plot_success_matrix(rows, plots_dir / "success_matrix.png", experiment_name)
    plot_turns_to_solve(results, plots_dir / "turns_to_solve.png", experiment_name)
    plot_turns_to_fail(results, plots_dir / "turns_to_fail.png", experiment_name)
    plot_tokens_to_solve(results, plots_dir / "tokens_to_solve.png", experiment_name)
    plot_tokens_to_fail(results, plots_dir / "tokens_to_fail.png", experiment_name)

    print_summary(results, rows)
    print(f"Plots written to {plots_dir}/")


if __name__ == "__main__":
    main()