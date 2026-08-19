"""
llmits.paperfold.confusion
==========================

Confusion matrices for the paper-folding test - every answer the models gave,
laid out against everything that could have been driving it.

``analysis.py`` answers "which model is best inside this run" and
``comparison.py`` answers "what did changing the wording do". Both of them read
one number off each trial: right or wrong. That number is exactly where a bias
hides. A model that answers "C" to everything scores 20% on a five-way choice,
which is also what a model that reasoned and got unlucky scores - and no
accuracy chart can tell those two apart. A confusion matrix can: it keeps *what
was asked* and *what was answered* as two separate axes and never collapses
them, so "wrong" stops being one bucket and becomes a shape.

The module builds two shapes of grid, and every table on the page is one of
them:

  * **Distribution grids** - rows are some condition (the correct letter, the
    model, the fold count, where the hole was punched, ...) and columns are the
    letter the model actually answered. The cell is how many trials landed
    there. The question is always the same: does the answer distribution change
    down the rows? If it doesn't, that condition wasn't reaching the model. If
    it does, it was.

  * **Accuracy grids** - rows and columns are both conditions, and the cell is
    the percent correct within it. These answer "where does this model fail"
    rather than "what does it say", which is the other half of the same
    question: an even answer spread with a hole in one region is still a bias,
    just not one the letters show.

Every distribution grid carries its own statistics, because "this row looks
different" is a claim about noise as much as about the model:

  * **Expected counts** under the null that the row doesn't matter
    (row total x column total / n) - the grid you'd see if the condition
    changed nothing.
  * **Adjusted residuals** per cell, which are approximately standard normal,
    so |r| > 2 marks a cell that is pulling away from that null and |r| > 3 one
    that is doing so hard. This is the number that actually finds a bias, and
    the plots mark those cells rather than leaving them to be spotted by eye.
  * **A chi-square test of independence**, with Cramer's V beside it - the
    p-value says whether the grid as a whole moved, V says whether the move is
    worth caring about. Both are reported, because 5,000 trials will hand you a
    significant p-value for an effect too small to matter.

Trials with no readable answer are not dropped. A model that stopped producing
a letter at eight folds is one of the clearest results this test can produce,
and filtering it out for tidiness would delete it - so ``?`` is a column like
any other, present only when it has something in it.

Plots are written to a confusion directory as ``<key>.png``: one heatmap per
grid, plus three small-multiple sheets (per model, per fold count, per run)
that put a whole family of 5x5 confusions on one page.

Styling follows ``analysis`` and ``comparison`` - the same muted gray labels,
plain-language axis captions and subtitle-above-the-axes - so a confusion
heatmap reads as part of the same family as the charts on the other tabs.
"""

from __future__ import annotations

import hashlib
import json
import math
import textwrap
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")

import matplotlib.colors
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np

from llmits.paperfold import analysis as ar
from llmits.paperfold.cognitive_test import paper_size_for_folds

LETTERS: list[str] = list(ar.LETTERS)
# The column for a trial the model answered but no letter could be read out of.
# Deliberately not filtered away: see the module docstring.
NO_ANSWER = "?"
LABEL_GRAY = ar.LABEL_GRAY
CHANCE = 100.0 / len(LETTERS)          # five candidates, so guessing lands here
DIRECTIONS = ("north", "south", "east", "west")

# Residual thresholds. Adjusted residuals are ~N(0, 1) under the null, so these
# are the usual two-sigma / three-sigma marks: "leaning" and "leaning hard".
RESIDUAL_NOTABLE = 2.0
RESIDUAL_STRONG = 3.0

# A row with almost nothing in it will happily produce a 100% or a 0% and an
# enormous residual. Rows below this many trials are kept in the grid (dropping
# them would hide which conditions went untested) but never generate a finding.
MIN_ROW_TRIALS = 20


# =============================================================================
#  Statistics - chi-square without scipy
# =============================================================================
def _gamma_series(a: float, x: float) -> float:
    """Lower regularized incomplete gamma P(a, x) by its series expansion,
    which converges quickly for x < a + 1."""
    total, term = 1.0 / a, 1.0 / a
    for n in range(1, 500):
        term *= x / (a + n)
        total += term
        if abs(term) < abs(total) * 1e-14:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gamma_cf(a: float, x: float) -> float:
    """Upper regularized incomplete gamma Q(a, x) by continued fraction (the
    modified Lentz method), which is the convergent branch for x >= a + 1."""
    tiny = 1e-300
    b, c, d = x + 1.0 - a, 1.0 / tiny, 1.0 / (x + 1.0 - a)
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h * math.exp(-x + a * math.log(x) - math.lgamma(a))


def chi2_sf(stat: float, df: int) -> float:
    """P(chi-square with ``df`` degrees of freedom > ``stat``).

    Written out here rather than imported: scipy is a heavy dependency to add
    for one survival function, and this is the standard two-branch incomplete
    gamma every implementation of it uses.
    """
    if df <= 0 or stat <= 0 or not math.isfinite(stat):
        return 1.0
    a, x = df / 2.0, stat / 2.0
    if x < a + 1.0:
        return max(0.0, min(1.0, 1.0 - _gamma_series(a, x)))
    return max(0.0, min(1.0, _gamma_cf(a, x)))


def p_text(p: float | None) -> str:
    """A p-value as it should be read out loud, not as six decimal places."""
    if p is None or not math.isfinite(p):
        return "n/a"
    if p < 0.0001:
        return "p < 0.0001"
    return f"p = {p:.4f}".rstrip("0").rstrip(".") if p < 0.001 else f"p = {p:.3f}"


def independence_test(counts: np.ndarray) -> dict[str, Any] | None:
    """Chi-square test of independence on a contingency table, plus the effect
    size that keeps it honest.

    A significant p-value on five thousand trials can mean a lean of one
    percentage point, so Cramer's V is reported next to it: p says the grid
    moved, V says by how much (0 = the rows are interchangeable, 1 = the row
    tells you the answer outright).
    """
    counts = np.asarray(counts, dtype=float)
    # Empty rows and columns carry no information and would only inflate the
    # degrees of freedom, so they're dropped before the test rather than
    # contributing zero cells to it.
    counts = counts[counts.sum(axis=1) > 0][:, counts.sum(axis=0) > 0]
    n = counts.sum()
    if counts.shape[0] < 2 or counts.shape[1] < 2 or n < 2:
        return None
    expected = np.outer(counts.sum(axis=1), counts.sum(axis=0)) / n
    with np.errstate(divide="ignore", invalid="ignore"):
        stat = float(np.nansum((counts - expected) ** 2 / expected))
    df = (counts.shape[0] - 1) * (counts.shape[1] - 1)
    k = min(counts.shape) - 1
    return {
        "stat": round(stat, 2),
        "df": int(df),
        "p": chi2_sf(stat, df),
        "cramers_v": round(math.sqrt(stat / (n * k)) if n and k else 0.0, 3),
        # The smallest expected count, so a reader can see when the test is
        # being asked to work on a table too thin to support it.
        "min_expected": round(float(expected.min()), 1),
    }


def goodness_of_fit(observed: Iterable[float], expected: Iterable[float]) -> dict[str, Any] | None:
    """Chi-square goodness of fit of one distribution against another - how the
    answers were spread against how the correct answers were."""
    obs = np.asarray(list(observed), dtype=float)
    exp = np.asarray(list(expected), dtype=float)
    keep = exp > 0
    obs, exp = obs[keep], exp[keep]
    if obs.size < 2 or exp.sum() <= 0:
        return None
    exp = exp * (obs.sum() / exp.sum())          # scale to the observed total
    stat = float(((obs - exp) ** 2 / exp).sum())
    df = obs.size - 1
    return {"stat": round(stat, 2), "df": int(df), "p": chi2_sf(stat, df),
            "min_expected": round(float(exp.min()), 1)}


def stratified_independence(tables: Iterable[np.ndarray]) -> dict[str, Any] | None:
    """Test the same contingency table inside every model, then add the results
    up - never on the models pooled together.

    This is the difference between a real finding and the commonest false one on
    this page. Suppose one model answers A most of the time and another almost
    never does. Pool their trials and *any* row variable that isn't perfectly
    balanced across the two will look associated with the answer, because the
    pooled marginals are a blend of two different habits and no single cell
    matches either. Run the numbers that way on this project's own data and
    "the previous answer predicts the next one" comes out at p < 1e-9 - on a
    test where every trial is a fresh conversation and nothing can carry over.
    Inside each model the same grid gives p = 0.41: there was never anything
    there but the mixture.

    So each model contributes its own table, and under the null those per-model
    chi-square statistics are independent - their sum is a chi-square with their
    degrees of freedom summed. Anything this test calls a bias is one that holds
    *within* a model, which is the only kind worth reporting.
    """
    stat, df, n = 0.0, 0, 0.0
    smallest = math.inf
    strata = 0
    for table in tables:
        test = independence_test(table)
        if not test:
            continue
        stat += test["stat"]
        df += test["df"]
        n += float(np.asarray(table).sum())
        smallest = min(smallest, test["min_expected"])
        strata += 1
    if df <= 0:
        return None
    k = 1
    return {"stat": round(stat, 2), "df": int(df), "p": chi2_sf(stat, df),
            # Approximate: the pooled effect size for a pooled statistic. Read
            # it as an order of magnitude, not a fourth decimal place.
            "cramers_v": round(math.sqrt(max(stat - df, 0) / (n * k)) if n else 0.0, 3),
            "min_expected": None if smallest is math.inf else round(smallest, 1),
            "stratified": True, "strata": strata}


def adjusted_residuals(counts: np.ndarray) -> np.ndarray:
    """Per-cell adjusted (standardized) residuals for a contingency table.

    (observed - expected) scaled by the cell's own standard error, which makes
    the result approximately standard normal - so one threshold means the same
    thing in a cell of 12 trials and a cell of 1,200, and "which cell is the
    bias in" becomes a question with a numeric answer instead of a judgement
    about shades of blue.
    """
    counts = np.asarray(counts, dtype=float)
    n = counts.sum()
    if n <= 0:
        return np.zeros_like(counts)
    row = counts.sum(axis=1, keepdims=True)
    col = counts.sum(axis=0, keepdims=True)
    expected = row * col / n
    variance = expected * (1 - row / n) * (1 - col / n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (counts - expected) / np.sqrt(variance)
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


# =============================================================================
#  Loading, and the per-trial facts every grid is cut by
# =============================================================================
def load_run(run_dir: Path) -> dict[str, Any]:
    """One run's results.json as {name, results, rows}.

    Unlike ``comparison.load_run`` this keeps trials whose answer couldn't be
    parsed. They are answers - just not letters - and a condition that stops a
    model producing a letter at all is the strongest bias this page can find.
    Trials that never reached a model (a load failure, a run stopped early)
    aren't in results.json in the first place, so nothing unanswerable is being
    counted here either way.
    """
    results = json.loads((run_dir / "results.json").read_text())
    rows = [r for r in ar.flatten(results) if r.get("correct_choice")]
    return {"name": run_dir.name, "results": results, "rows": rows}


def answer_of(row: dict) -> str:
    """The letter a trial was answered with, or ``?`` when none could be read."""
    predicted = row.get("predicted_choice")
    return predicted if predicted in LETTERS else NO_ANSWER


def is_correct(row: dict) -> bool:
    """Graded here rather than trusting the stored flag, so a row that predates
    a field or arrived from an older run is scored the same way as a fresh one."""
    return answer_of(row) == row.get("correct_choice")


def answer_columns(rows) -> list[str]:
    """A-E, plus the no-answer column only when some trial actually needs it -
    an empty column in twenty grids is twenty pieces of furniture saying nothing."""
    return LETTERS + ([NO_ANSWER] if any(answer_of(r) == NO_ANSWER for r in rows) else [])


def paper_size(row: dict) -> tuple[int, int]:
    """The sheet this trial started from. Recorded per trial on newer runs;
    derived from the fold count for older ones, which is where it came from."""
    width, height = row.get("paper_width"), row.get("paper_height")
    if width and height:
        return int(width), int(height)
    folds = int(row.get("num_folds") or 0)
    return paper_size_for_folds(folds)


def folded_size(row: dict) -> tuple[int, int] | None:
    """The size of the folded sheet the hole was punched through.

    Not stored on the trial, but fully determined by what is: each east/west
    fold halves the width and each north/south fold halves the height, so the
    fold history and the starting sheet give it exactly. Needed because the
    punch position is a coordinate *on the folded paper*, and a raw (3, 4)
    means something different on a 4x8 sheet than on a 32x32 one.
    """
    history = row.get("fold_history")
    if not history:
        return None
    width, height = paper_size(row)
    horizontal = sum(1 for d in history if d in ("east", "west"))
    vertical = sum(1 for d in history if d in ("north", "south"))
    width //= 2 ** horizontal
    height //= 2 ** vertical
    return (width, height) if width > 0 and height > 0 else None


def punch_halves(row: dict) -> tuple[str, str] | None:
    """Which half of the folded sheet the hole was punched in, vertically and
    horizontally, as ("top"|"bottom", "left"|"right").

    Halves rather than thirds on purpose: every folded side is a power of two,
    so halves split it exactly and each band holds the same number of positions.
    Thirds of a 4-wide sheet would be 2/1/1, and the "bias" that fell out would
    partly be the binning.
    """
    position, size = row.get("punch_position"), folded_size(row)
    if not position or not size or len(position) < 2:
        return None
    x, y = int(position[0]), int(position[1])
    width, height = size
    if not (0 <= x < width and 0 <= y < height):
        return None
    return ("top" if y < height / 2 else "bottom",
            "left" if x < width / 2 else "right")


def punch_quadrant(row: dict) -> str | None:
    halves = punch_halves(row)
    return f"{halves[0]}-{halves[1]}" if halves else None


QUADRANTS = ("top-left", "top-right", "bottom-left", "bottom-right")


def folded_shape(row: dict) -> str | None:
    """Whether the folded sheet ended up taller than it was wide, square, or
    wider than tall - which axis the fold plan happened to load up on."""
    size = folded_size(row)
    if not size:
        return None
    width, height = size
    if width == height:
        return "square"
    return "taller than wide" if height > width else "wider than tall"


SHAPES = ("taller than wide", "square", "wider than tall")


def _quartile_labels() -> list[str]:
    return ["shortest 25%", "second 25%", "third 25%", "longest 25%"]


def effort_band(rows) -> dict[int, str]:
    """Which quartile of *its own model's* token spend each trial sits in.

    Within the model, not across the field: one reasoning model can spend five
    times what the rest of the field does on every single trial, and a global
    split would just re-label that model "the longest 25%" and measure nothing.
    Keyed by id() of the row dict, which is stable for the life of one analysis.
    """
    labels = _quartile_labels()
    out: dict[int, str] = {}
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_model[r.get("model_version", "unknown")].append(r)
    for model_rows in by_model.values():
        ordered = sorted(model_rows, key=lambda r: float(r.get("total_tokens") or 0))
        if len(ordered) < 4:
            continue
        cut = len(ordered) / 4
        for index, row in enumerate(ordered):
            out[id(row)] = labels[min(3, int(index // cut))]
    return out


def phase_band(rows) -> dict[int, str]:
    """Which fifth of its model's run each trial sits in, by trial number.

    A model is a fresh conversation every trial, so nothing should drift across
    a run - which is exactly why it is worth checking. Drift here means
    something outside the prompt (a provider rerouting, a degrading cache, a
    rate limiter) is reaching the answers.
    """
    labels = ["first fifth", "second fifth", "third fifth", "fourth fifth", "last fifth"]
    out: dict[int, str] = {}
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_model[r.get("model_version", "unknown")].append(r)
    for model_rows in by_model.values():
        ordered = sorted(model_rows, key=lambda r: int(r.get("trial") or 0))
        if len(ordered) < 5:
            continue
        cut = len(ordered) / 5
        for index, row in enumerate(ordered):
            out[id(row)] = labels[min(4, int(index // cut))]
    return out


PHASES = ["first fifth", "second fifth", "third fifth", "fourth fifth", "last fifth"]


# =============================================================================
#  The two grid shapes
# =============================================================================
def distribution_grid(key: str, group: str, title: str, caption: str, *,
                      row_label: str, col_label: str,
                      rows: list[str], cols: list[str],
                      cells: dict[tuple[str, str], int],
                      row_trials: dict[str, int] | None = None,
                      row_hits: dict[str, int] | None = None,
                      symmetric: bool = False,
                      strata: dict[str, dict[tuple[str, str], int]] | None = None,
                      rings: bool = True,
                      note: str | None = None) -> dict[str, Any]:
    """A "what was answered, by condition" grid, with its own statistics.

    ``cells`` is sparse - only the (row, column) pairs that happened - so a
    caller can count with a Counter and never has to build the empty grid
    itself. ``row_hits``/``row_trials`` are supplied when accuracy means
    something for a row (it does for every condition; it doesn't for the
    transition grid, whose rows are previous answers rather than trials).

    ``strata`` is the same counts split per model. Where it is given, the
    headline test is the stratified one and the pooled test is kept beside it,
    because the two disagreeing is itself worth seeing: it means the grid's
    shape is the field's mixture of habits rather than any one model's
    behaviour (see ``stratified_independence``).
    """
    counts = np.array([[float(cells.get((r, c), 0)) for c in cols] for r in rows])
    residuals = adjusted_residuals(counts)
    total = float(counts.sum())
    row_totals = counts.sum(axis=1)
    col_totals = counts.sum(axis=0)
    expected = (np.outer(row_totals, col_totals) / total) if total else np.zeros_like(counts)

    pooled_test = independence_test(counts)
    stratified_test = stratified_independence(
        np.array([[float(stratum.get((r, c), 0)) for c in cols] for r in rows])
        for stratum in strata.values()) if strata else None

    accuracy = None
    if row_trials is not None and row_hits is not None:
        accuracy = [round(100 * row_hits.get(r, 0) / row_trials[r], 1)
                    if row_trials.get(r) else None for r in rows]

    return {
        "key": key, "group": group, "kind": "distribution",
        "title": title, "caption": caption,
        "row_label": row_label, "col_label": col_label,
        "rows": rows, "cols": cols,
        "counts": counts.astype(int).tolist(),
        "expected": np.round(expected, 2).tolist(),
        "residuals": np.round(residuals, 2).tolist(),
        "row_totals": row_totals.astype(int).tolist(),
        "col_totals": col_totals.astype(int).tolist(),
        "n": int(total),
        "row_accuracy": accuracy,
        "symmetric": symmetric,
        # Whether marking the cells that deviate says anything. On a plain
        # confusion matrix it doesn't: the diagonal is over-expected because the
        # models are right, which is the one thing the grid already shows.
        "rings": rings,
        "chi2": stratified_test or pooled_test,
        "pooled_chi2": pooled_test if stratified_test else None,
        "note": note,
    }


def _stratified_column_test(hit_grid: np.ndarray, total_grid: np.ndarray) -> dict[str, Any] | None:
    """Does the *column* change accuracy, once each row is held fixed?

    On a grid whose rows are models, an ordinary test of the whole table is
    guaranteed to come back significant - models differ, that is the entire
    point of the experiment - and it says nothing at all about the columns.
    This tests each row on its own and adds the results up: under the null that
    the column is irrelevant, the per-row chi-square statistics are independent,
    so their sum is a chi-square with their degrees of freedom summed. What
    comes out is the question actually worth asking of these grids - "does where
    the hole was punched matter *to a given model*" - with the model differences
    stratified out rather than drowning it.
    """
    stat, df, strata = 0.0, 0, 0
    for hit_row, total_row in zip(hit_grid, total_grid):
        keep = total_row > 0
        if keep.sum() < 2 or total_row[keep].sum() < 2:
            continue
        table = np.vstack([hit_row[keep], (total_row - hit_row)[keep]]).T
        test = independence_test(table)
        if test:
            stat += test["stat"]
            df += test["df"]
            strata += 1
    if df <= 0:
        return None
    # Cramer's V for the pooled table, as a rough size for the same effect -
    # the statistic above answers "is it there", never "is it big".
    n = float(total_grid.sum())
    return {"stat": round(stat, 2), "df": int(df), "p": chi2_sf(stat, df),
            "cramers_v": round(math.sqrt(max(stat - df, 0) / n) if n else 0.0, 3),
            "min_expected": None, "stratified": True, "strata": strata}


def accuracy_grid(key: str, group: str, title: str, caption: str, *,
                  row_label: str, col_label: str,
                  rows: list[str], cols: list[str],
                  hits: dict[tuple[str, str], int],
                  totals: dict[tuple[str, str], int],
                  stratify_rows: bool = False,
                  note: str | None = None) -> dict[str, Any]:
    """A "where does it fail" grid: percent correct in each (row, column) cell.

    The trial counts travel with the percentages rather than being rounded away,
    because a 0% built from three trials and a 0% built from three hundred are
    the same colour and completely different findings.

    ``stratify_rows`` says the rows are a dimension we already know varies (the
    models, the difficulty, the run) and the question is about the columns. It
    swaps the headline test for the stratified one and adds a per-column average
    that gives every row the same weight, so a column can't be dragged by
    whichever model happened to answer most of its trials.
    """
    hit_grid = np.array([[float(hits.get((r, c), 0)) for c in cols] for r in rows])
    total_grid = np.array([[float(totals.get((r, c), 0)) for c in cols] for r in rows])
    with np.errstate(divide="ignore", invalid="ignore"):
        values = np.where(total_grid > 0, 100 * hit_grid / total_grid, np.nan)

    # Whether accuracy really differs across the grid, tested on the 2xN table
    # of right against wrong - the same question the colours are asking.
    flat_hits = hit_grid.flatten()
    flat_miss = (total_grid - hit_grid).flatten()
    keep = (flat_hits + flat_miss) > 0
    test = independence_test(np.vstack([flat_hits[keep], flat_miss[keep]]).T) \
        if keep.sum() >= 2 else None
    pooled_test = test
    if stratify_rows:
        test = _stratified_column_test(hit_grid, total_grid)
    # Column averages with every row weighted equally. Computed by hand rather
    # than with nanmean so a column no row has any trials in comes out empty
    # instead of raising on an all-NaN slice.
    counted = np.where(np.isnan(values), 0.0, values).sum(axis=0)
    present = (~np.isnan(values)).sum(axis=0)
    column_mean = np.where(present > 0, counted / np.maximum(present, 1), np.nan)

    return {
        "stratified": bool(stratify_rows),
        "column_mean": [None if math.isnan(v) else round(float(v), 1) for v in column_mean],
        "key": key, "group": group, "kind": "accuracy",
        "title": title, "caption": caption,
        "row_label": row_label, "col_label": col_label,
        "rows": rows, "cols": cols,
        "values": [[None if math.isnan(v) else round(float(v), 1) for v in row]
                   for row in values],
        "hits": hit_grid.astype(int).tolist(),
        "totals": total_grid.astype(int).tolist(),
        "row_totals": total_grid.sum(axis=1).astype(int).tolist(),
        "col_totals": total_grid.sum(axis=0).astype(int).tolist(),
        "n": int(total_grid.sum()),
        "chi2": test,
        "pooled_chi2": pooled_test if stratify_rows else None,
        "note": note,
    }


def _confusion_cells(rows) -> dict[tuple[str, str], int]:
    return Counter((r["correct_choice"], answer_of(r)) for r in rows)


def confusion_of(rows, key: str, title: str, caption: str,
                 group: str = "core", errors_only: bool = False,
                 note: str | None = None) -> dict[str, Any]:
    """The classic grid: the letter that was right against the letter that was
    given. Every other grid on the page is a re-cut of this one.

    ``errors_only`` marks a grid the correct answers have been taken out of. Its
    diagonal is empty by construction, so accuracy, recall and precision are all
    zero by definition there - reporting them would be reporting the filter
    rather than the models, so they're left off entirely.
    """
    cols = answer_columns(rows)
    per_letter = Counter(r["correct_choice"] for r in rows)
    correct = Counter(r["correct_choice"] for r in rows if is_correct(r))
    grid = distribution_grid(
        key, group, title, caption,
        row_label="Correct answer (the letter the puzzle actually was)",
        col_label="Model's answer (the letter it picked)",
        rows=LETTERS, cols=cols, cells=_confusion_cells(rows),
        row_trials=None if errors_only else per_letter,
        row_hits=None if errors_only else correct,
        symmetric=True, rings=errors_only, note=note)
    grid["errors_only"] = errors_only
    if errors_only:
        return grid
    # Recall and precision per letter - the two readings of the same grid, one
    # along the rows and one down the columns. A letter with high precision and
    # low recall is one the model only reaches for when it is sure; the reverse
    # is a letter it falls back on.
    answered = Counter(answer_of(r) for r in rows)
    grid["recall"] = {l: round(100 * correct.get(l, 0) / per_letter[l], 1)
                      if per_letter.get(l) else None for l in LETTERS}
    grid["precision"] = {l: round(100 * correct.get(l, 0) / answered[l], 1)
                         if answered.get(l) else None for l in LETTERS}
    grid["marginal_test"] = goodness_of_fit(
        [answered.get(l, 0) for l in LETTERS], [per_letter.get(l, 0) for l in LETTERS])
    grid["accuracy"] = round(100 * sum(correct.values()) / len(rows), 1) if rows else None
    return grid


# =============================================================================
#  Cutting the trials up
# =============================================================================
def _distribution_by(rows, row_of):
    """(cells, trials, hits, strata) keyed by whatever ``row_of`` calls each trial.

    Trials the function can't place (an older run with no punch position, say)
    are skipped rather than bucketed into an "unknown" row that would then get
    tested for bias against the rows that do mean something.

    ``strata`` is the same counts split by model, which is what the grid is
    actually tested on - see ``stratified_independence`` for why pooling the
    models first would invent associations that aren't there.
    """
    cells: Counter = Counter()
    trials: Counter = Counter()
    hits: Counter = Counter()
    strata: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        key = row_of(r)
        if key is None:
            continue
        cells[(key, answer_of(r))] += 1
        strata[r.get("model_version", "unknown")][(key, answer_of(r))] += 1
        trials[key] += 1
        if is_correct(r):
            hits[key] += 1
    return cells, trials, hits, dict(strata)


def _accuracy_by(rows, row_of, col_of):
    """(hits, totals) keyed by a pair of conditions."""
    hits: Counter = Counter()
    totals: Counter = Counter()
    for r in rows:
        a, b = row_of(r), col_of(r)
        if a is None or b is None:
            continue
        totals[(a, b)] += 1
        if is_correct(r):
            hits[(a, b)] += 1
    return hits, totals


def _model_order(rows, models) -> list[str]:
    """Models best-first, so reading down any grid is reading a leaderboard and
    a grid that reorders it is visibly doing so."""
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_model[r.get("model_version", "unknown")].append(r)
    return sorted(models, key=lambda m: (
        -(100 * sum(1 for r in by_model[m] if is_correct(r)) / len(by_model[m]))
        if by_model.get(m) else 1, m))


def build_grids(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """Every confusion grid this selection can support, in reading order.

    Grids that a selection can't answer are left out rather than drawn empty: a
    difficulty cut needs more than one fold count, a wording cut needs more than
    one run. What's here is what the data can actually be asked.
    """
    rows = ctx["rows"]
    models = ctx["models"]
    folds = ctx["folds"]
    runs = ctx["run_names"]
    grids: list[dict[str, Any]] = []

    # -- core -----------------------------------------------------------------
    grids.append(confusion_of(
        rows, "answer_confusion", "Correct answer against the answer given",
        "The whole test in one grid. The diagonal is every trial answered "
        "correctly; everything off it is an error, placed by where it went. A "
        "column that is dark all the way down is a letter the models drift "
        "toward whatever the right answer was, which is the bias this page "
        "exists to find."))

    wrong = [r for r in rows if not is_correct(r)]
    if wrong:
        grids.append(confusion_of(
            wrong, "error_flow", "Where the wrong answers went",  # errors_only below
            "The same grid with every correct answer removed, so the diagonal "
            "is empty by construction and the only thing left is the shape of "
            "the mistakes. Under real reasoning gone wrong these spread evenly "
            "across the four remaining letters; a fallback letter shows up here "
            "as a stripe.", group="core", errors_only=True))

    # -- per model ------------------------------------------------------------
    cells, trials, hits, strata = _distribution_by(rows, lambda r: r.get("model_version", "unknown"))
    grids.append(distribution_grid(
        "model_answer_share", "model", "What each model answered",
        "One row per model, ranked best first. A row that matches the correct "
        "distribution (roughly a fifth in each column) is a model spreading its "
        "answers the way the puzzle does; a row with one heavy column has a "
        "favourite letter, and the accuracy column tells you whether that "
        "favourite is costing it anything.",
        row_label="Model", col_label="Model's answer",
        rows=models, cols=answer_columns(rows), cells=cells,
        row_trials=trials, row_hits=hits))

    if wrong:
        wcells, _, _, wstrata = _distribution_by(wrong, lambda r: r.get("model_version", "unknown"))
        grids.append(distribution_grid(
            "model_error_share", "model", "What each model answered when it was wrong",
            "The purest per-model bias signal on the page: with the correct "
            "answers taken out, whatever is left of a row is where that model "
            "goes when it doesn't know. Even across the letters means it was "
            "still working the puzzle. One column carrying the row means it had "
            "a default.",
            row_label="Model", col_label="Model's answer (wrong answers only)",
            rows=models, cols=answer_columns(wrong), cells=wcells))

    ahits, atotals = _accuracy_by(rows, lambda r: r.get("model_version", "unknown"),
                                  lambda r: r["correct_choice"])
    grids.append(accuracy_grid(
        "model_letter_recall", "model", "How often each model found the answer, by which letter it was",
        "Accuracy split by the letter the answer happened to be. The puzzle "
        "picks that letter at random, so a model reasoning about the paper "
        "should score the same across the row. A cell that sags is a letter the "
        "model struggles to select even when it is right - the mirror image of "
        "a favourite.",
        row_label="Model", col_label="Correct answer",
        rows=models, cols=LETTERS, hits=ahits, totals=atotals, stratify_rows=True))

    # -- difficulty -----------------------------------------------------------
    if len(folds) > 1:
        fold_name = lambda r: (f"{int(r['num_folds'])} folds"
                               if r.get("num_folds") is not None else None)
        fold_rows = [f"{f} folds" for f in folds]
        cells, trials, hits, strata = _distribution_by(rows, fold_name)
        grids.append(distribution_grid(
            "folds_answer_share", "difficulty", "What was answered, by how hard the puzzle was",
            "Reading down these rows is watching the field run out of road. "
            "Answers stay spread while the geometry is still being tracked and "
            "collapse toward one or two letters when it isn't - and that "
            "collapse usually shows up a fold before the accuracy curve does.",
            row_label="Puzzle difficulty", col_label="Model's answer",
            rows=fold_rows, cols=answer_columns(rows), cells=cells,
            row_trials=trials, row_hits=hits, strata=strata))

        ahits, atotals = _accuracy_by(rows, fold_name, lambda r: r["correct_choice"])
        grids.append(accuracy_grid(
            "folds_letter_recall", "difficulty", "Accuracy by difficulty and by which letter was correct",
            "If the letter is irrelevant - as it should be - every row here is "
            "flat and only the rows themselves fall away as folds pile up. A "
            "column that stays high while the rest of its row drops is a letter "
            "still being picked at difficulties where nothing is being solved.",
            row_label="Puzzle difficulty", col_label="Correct answer",
            rows=fold_rows, cols=LETTERS, hits=ahits, totals=atotals, stratify_rows=True))

        ahits, atotals = _accuracy_by(rows, lambda r: r.get("model_version", "unknown"), fold_name)
        grids.append(accuracy_grid(
            "model_folds_accuracy", "difficulty", "Accuracy of each model at each difficulty",
            "The difficulty curve as a grid. Where a row reaches the 20% chance "
            "line is how much folding that model could hold in its head; a row "
            "that starts there never had it.",
            row_label="Model", col_label="Puzzle difficulty",
            rows=models, cols=fold_rows, hits=ahits, totals=atotals, stratify_rows=True))

    # -- spatial --------------------------------------------------------------
    if any(punch_quadrant(r) for r in rows):
        cells, trials, hits, strata = _distribution_by(rows, punch_quadrant)
        grids.append(distribution_grid(
            "punch_quadrant_answer_share", "spatial", "What was answered, by where the hole was punched",
            "The hole's position on the folded sheet, in quarters. This is a "
            "fact about the puzzle the model can see but that says nothing "
            "about which letter is right, so these four rows should be "
            "identical. Where they aren't, something about the picture - not "
            "the reasoning - is steering the answer.",
            row_label="Where the hole was punched (on the folded sheet)",
            col_label="Model's answer",
            rows=list(QUADRANTS), cols=answer_columns(rows), cells=cells,
            row_trials=trials, row_hits=hits, strata=strata))

        ahits, atotals = _accuracy_by(
            rows, lambda r: (punch_halves(r) or (None, None))[0],
            lambda r: (punch_halves(r) or (None, None))[1])
        grids.append(accuracy_grid(
            "punch_quadrant_accuracy", "spatial", "Accuracy by where on the paper the hole was",
            "The same four quarters as accuracy. A blind spot here - one corner "
            "materially worse than the others - is a spatial bias in the "
            "clearest sense: the same puzzle, solved less often depending on "
            "which part of the grid it had to be read from.",
            row_label="Vertical half of the folded sheet",
            col_label="Horizontal half of the folded sheet",
            rows=["top", "bottom"], cols=["left", "right"],
            hits=ahits, totals=atotals))

        ahits, atotals = _accuracy_by(rows, lambda r: r.get("model_version", "unknown"),
                                      punch_quadrant)
        grids.append(accuracy_grid(
            "model_quadrant_accuracy", "spatial", "Each model's accuracy by where the hole was",
            "Blind spots are usually one model's, not the field's - averaging "
            "the quarters over everybody hides a model that can't read the "
            "bottom of a grid behind three that can. This is the row-by-row "
            "version of the grid above.",
            row_label="Model", col_label="Where the hole was punched",
            rows=models, cols=list(QUADRANTS), hits=ahits, totals=atotals, stratify_rows=True))

    if any(r.get("fold_history") for r in rows):
        # A trial folded east, south, west belongs to three of these rows, so
        # the rows overlap and the totals sum past the trial count. That's the
        # honest way to ask "does this direction being in the plan change
        # anything" - the alternative, one row per whole plan, splits the data
        # into dozens of rows too thin to test.
        dcells: Counter = Counter()
        dtrials: Counter = Counter()
        dhits: Counter = Counter()
        dstrata: dict[str, Counter] = defaultdict(Counter)
        for r in rows:
            for direction in {d for d in (r.get("fold_history") or []) if d in DIRECTIONS}:
                dcells[(direction, answer_of(r))] += 1
                dstrata[r.get("model_version", "unknown")][(direction, answer_of(r))] += 1
                dtrials[direction] += 1
                if is_correct(r):
                    dhits[direction] += 1
        if dtrials:
            grids.append(distribution_grid(
                "fold_direction_answer_share", "spatial",
                "What was answered, by which directions the paper was folded in",
                "One row per direction that appeared anywhere in the fold plan. "
                "Rows overlap - a three-fold trial sits in up to three of them - "
                "so read this for differences between rows, not for the totals. "
                "On runs where the direction words were replaced, this is the "
                "grid that shows whether one particular word was doing the "
                "damage.",
                row_label="Direction used in the fold plan (real direction, whatever it was called)",
                col_label="Model's answer",
                rows=list(DIRECTIONS), cols=answer_columns(rows), cells=dcells,
                row_trials=dtrials, row_hits=dhits, strata=dstrata,
                note="Rows overlap: one trial appears in a row for each distinct "
                     "direction its fold plan used."))

        first_last = [r for r in rows if len(r.get("fold_history") or []) >= 2]
        if first_last:
            ahits, atotals = _accuracy_by(
                first_last, lambda r: r["fold_history"][0], lambda r: r["fold_history"][-1])
            grids.append(accuracy_grid(
                "fold_plan_accuracy", "spatial", "Accuracy by the first and last fold of the plan",
                "Order effects: whether starting a plan one way, or finishing "
                "it another, makes the same amount of folding harder. The fold "
                "plan is drawn at random and balanced across the two axes, so "
                "every cell here is the same puzzle difficulty - any structure "
                "is the model's, not the test's.",
                row_label="First fold", col_label="Last fold",
                rows=list(DIRECTIONS), cols=list(DIRECTIONS), hits=ahits, totals=atotals))

    if any(folded_shape(r) for r in rows):
        ahits, atotals = _accuracy_by(rows, lambda r: r.get("model_version", "unknown"),
                                      folded_shape)
        grids.append(accuracy_grid(
            "shape_accuracy", "spatial", "Accuracy by the shape the folded paper ended up",
            "An odd number of folds leaves the sheet twice as long on one axis "
            "as the other, and which axis that is gets drawn at random. Same "
            "difficulty either way - so a model that does better on wide sheets "
            "than tall ones is reading the grid, not the geometry.",
            row_label="Model", col_label="Shape of the folded sheet",
            rows=models, cols=list(SHAPES), hits=ahits, totals=atotals, stratify_rows=True))

    # -- sequence -------------------------------------------------------------
    transitions: Counter = Counter()
    transition_strata: dict[str, Counter] = defaultdict(Counter)
    by_model_run: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by_model_run[(r.get("__run", ""), r.get("model_version", "unknown"))].append(r)
    for (_, model), series in by_model_run.items():
        ordered = sorted(series, key=lambda r: int(r.get("trial") or 0))
        for previous, current in zip(ordered, ordered[1:]):
            if int(current.get("trial") or 0) - int(previous.get("trial") or 0) != 1:
                continue          # a gap in the numbering isn't a real adjacency
            transitions[(answer_of(previous), answer_of(current))] += 1
            transition_strata[model][(answer_of(previous), answer_of(current))] += 1
    if sum(transitions.values()) >= 50:
        cols = sorted({c for _, c in transitions}, key=lambda c: (c == NO_ANSWER, c))
        rows_t = sorted({p for p, _ in transitions}, key=lambda c: (c == NO_ANSWER, c))
        grids.append(distribution_grid(
            "answer_transition", "sequence", "Each answer against the one before it",
            "Every trial is a fresh conversation with the model reset, and the "
            "puzzles are independent, so this grid should be featureless: what "
            "was answered last time cannot legitimately predict this time. A "
            "heavy diagonal means answers are sticking, and anything else with "
            "structure means state is surviving between trials somewhere it "
            "shouldn't.",
            row_label="Previous answer (same model, previous trial)",
            col_label="This answer",
            rows=rows_t, cols=cols, cells=transitions, symmetric=True,
            strata={m: c for m, c in transition_strata.items()},
            note="Consecutive trials of one model within one run; the very "
                 "first trial of each model has no predecessor and is not counted."))

    phases = phase_band(rows)
    if phases:
        cells, trials, hits, strata = _distribution_by(rows, lambda r: phases.get(id(r)))
        grids.append(distribution_grid(
            "phase_answer_share", "sequence", "What was answered, by how far into the run it was",
            "The run split into fifths by trial number. Nothing carries between "
            "trials, so this should be flat - a lean that grows toward the last "
            "fifth is drift from outside the experiment (a provider rerouting "
            "the model, a rate limiter, a degrading cache), and it would "
            "otherwise be invisible in an accuracy average.",
            row_label="Position in the run", col_label="Model's answer",
            rows=[p for p in PHASES if trials.get(p)], cols=answer_columns(rows),
            cells=cells, row_trials=trials, row_hits=hits, strata=strata))

    # -- effort ---------------------------------------------------------------
    effort = effort_band(rows)
    if effort:
        bands = _quartile_labels()
        cells, trials, hits, strata = _distribution_by(rows, lambda r: effort.get(id(r)))
        grids.append(distribution_grid(
            "effort_answer_share", "effort", "What was answered, by how much the model wrote",
            "Trials sorted into quarters by token spend, within each model so a "
            "verbose model and a terse one are each measured against "
            "themselves. The cheap quarter is where giving up lives: a letter "
            "that is over-represented there and nowhere else is the answer that "
            "gets produced instead of reasoning.",
            row_label="Token spend (quartile within each model)",
            col_label="Model's answer",
            rows=bands, cols=answer_columns(rows), cells=cells,
            row_trials=trials, row_hits=hits, strata=strata))

        ahits, atotals = _accuracy_by(rows, lambda r: r.get("model_version", "unknown"),
                                      lambda r: effort.get(id(r)))
        grids.append(accuracy_grid(
            "model_effort_accuracy", "effort", "Each model's accuracy by how much it wrote",
            "Whether thinking longer actually bought anything. A row that rises "
            "left to right spends its tokens on the hard trials and gets them "
            "back; a flat row is spending them either way; a row that falls is "
            "a model that writes most when it is lost.",
            row_label="Model", col_label="Token spend (quartile within each model)",
            rows=models, cols=bands, hits=ahits, totals=atotals, stratify_rows=True))

    # -- wording (only meaningful with more than one run selected) ------------
    if len(runs) > 1:
        cells, trials, hits, strata = _distribution_by(rows, lambda r: r.get("__run"))
        grids.append(distribution_grid(
            "run_answer_share", "wording", "What was answered, by experiment",
            "One row per run, the same models and difficulties underneath each. "
            "The puzzle never changed between these rows - only what the four "
            "directions were called - so a row whose answers redistribute is "
            "the wording reaching the answer itself, which is a stronger "
            "statement than the same run merely scoring lower.",
            row_label="Experiment", col_label="Model's answer",
            rows=runs, cols=answer_columns(rows), cells=cells,
            row_trials=trials, row_hits=hits, strata=strata))

        ahits, atotals = _accuracy_by(rows, lambda r: r.get("__run"),
                                      lambda r: r["correct_choice"])
        grids.append(accuracy_grid(
            "run_letter_recall", "wording", "Accuracy by experiment and by which letter was correct",
            "Whether a wording made the whole puzzle harder or only made one "
            "answer harder to reach. A run that lost accuracy evenly across the "
            "row lost reasoning; a run that lost it in one column developed a "
            "blind spot for a position.",
            row_label="Experiment", col_label="Correct answer",
            rows=runs, cols=LETTERS, hits=ahits, totals=atotals, stratify_rows=True))

    return grids


# =============================================================================
#  Findings - what the grids say, in words
# =============================================================================
def letter_skew(counts: dict[str, int]) -> float:
    """How far a spread of answers is from an even fifth each, 0-100.

    Total variation distance from uniform: 0 is perfectly even, 80 is every
    answer on one letter. The same measure the Compare page reports, so a skew
    quoted there and one quoted here are the same number.
    """
    total = sum(counts.values())
    if not total:
        return 0.0
    return round(100 * sum(abs(counts.get(l, 0) / total - 1 / len(LETTERS))
                           for l in LETTERS) / 2, 1)


def _grid(grids, key):
    return next((g for g in grids if g["key"] == key), None)


def _moved(grid, min_v: float = 0.05, alpha: float = 0.01) -> bool:
    """Whether a grid's rows really differ - significant *and* big enough to
    bother reporting. Five thousand trials will hand you p < 0.001 for a lean
    of half a percentage point, so the effect size has a veto."""
    test = grid and grid.get("chi2")
    return bool(test and test["p"] < alpha and test["cramers_v"] >= min_v)


def _strong_cells(grid, limit: int = 3, positive_only: bool = True) -> list[tuple[str, str, float, int]]:
    """The cells pulling hardest away from "this row changes nothing", biggest
    first: (row, column, adjusted residual, count).

    Over-representation only by default. A cell can only be short of expected
    because some other cell in its row is over it, so the negative residuals are
    the same finding stated backwards - and on an errors-only grid the biggest
    negative residual is always the empty diagonal, which is the filter talking
    rather than the models.
    """
    out = []
    for i, row in enumerate(grid["rows"]):
        for j, col in enumerate(grid["cols"]):
            residual = grid["residuals"][i][j]
            if grid.get("errors_only") and row == col:
                continue
            if abs(residual) < RESIDUAL_NOTABLE or (positive_only and residual <= 0):
                continue
            out.append((row, col, residual, grid["counts"][i][j]))
    out.sort(key=lambda t: -abs(t[2]))
    return out[:limit]


def findings(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Plain-language readings of the whole page, most load-bearing first.

    Every claim here is checked against noise before it is made: a lean that
    doesn't clear its chi-square test, or clears it on effect size too small to
    matter, is reported as "no bias found" rather than quietly dropped. "No
    detectable bias" is a result this page can return, and on a test whose whole
    purpose is to catch guessing, it is the good one.
    """
    grids = payload["grids"]
    out: list[dict[str, str]] = []
    core = _grid(grids, "answer_confusion")
    n = payload["scope"]["trials"]

    # -- the headline: is the answer distribution flat -------------------------
    answered = {l: core["col_totals"][core["cols"].index(l)] for l in LETTERS
                if l in core["cols"]}
    expected_letters = {l: core["row_totals"][i] for i, l in enumerate(core["rows"])}
    skew = letter_skew(answered)
    test = core.get("marginal_test")
    worst = max(LETTERS, key=lambda l: answered.get(l, 0) / max(n, 1)
                - expected_letters.get(l, 0) / max(n, 1))
    over = (100 * answered.get(worst, 0) / n) - (100 * expected_letters.get(worst, 0) / n)
    if test and test["p"] < 0.01 and skew >= 3:
        out.append({"kind": "bad", "title": f"The answers lean toward {worst}",
                    "text": f"Across {n:,} trials the models answered {worst} on "
                            f"{100 * answered.get(worst, 0) / n:.1f}% of them, against "
                            f"{100 * expected_letters.get(worst, 0) / n:.1f}% of trials where "
                            f"{worst} was actually correct - {over:+.1f} points more often than "
                            f"the puzzle called for. Overall skew away from an even fifth each is "
                            f"{skew:.1f} points ({p_text(test['p'])}). The correct letter is drawn "
                            f"at random, so nothing about the puzzle justifies a preference."})
    elif test:
        out.append({"kind": "good", "title": "No overall letter preference",
                    "text": f"Answers were spread across A-E almost exactly as the correct "
                            f"answers were ({skew:.1f} points of skew, {p_text(test['p'])}). "
                            f"Whatever else these {n:,} trials show, the field as a whole is not "
                            f"falling back on a favourite letter - so read the per-model grid "
                            f"next, where one model's habit can hide inside a flat average."})

    # -- accuracy in context ---------------------------------------------------
    accuracy = core.get("accuracy") or 0.0
    diag = [core["counts"][i][core["cols"].index(l)] for i, l in enumerate(core["rows"])
            if l in core["cols"]]
    out.append({"kind": "note", "title": f"{accuracy:.1f}% correct overall, against {CHANCE:.0f}% for guessing",
                "text": f"{sum(diag):,} of {n:,} trials landed on the diagonal. Every claim below "
                        f"is measured against that: on a five-way choice, a bias only means "
                        f"something once you know how much of the grid was reasoning in the first "
                        f"place."})

    if NO_ANSWER in core["cols"]:
        blank = core["col_totals"][core["cols"].index(NO_ANSWER)]
        out.append({"kind": "warn", "title": f"{blank:,} trials produced no readable letter",
                    "text": f"{100 * blank / n:.1f}% of answers had no A-E in them at all. They "
                            f"are kept as their own column rather than dropped - a condition that "
                            f"stops a model answering is a stronger finding than one that makes it "
                            f"answer wrongly."})

    # -- per-model habits ------------------------------------------------------
    leaning = []
    for model, stats in payload["per_model"].items():
        marginal = stats.get("marginal_test")
        if stats["trials"] >= MIN_ROW_TRIALS and marginal and marginal["p"] < 0.01 \
                and stats["skew"] >= 8:
            leaning.append((stats["skew"], model, stats))
    leaning.sort(reverse=True)
    if leaning:
        worst_skew, worst_model, stats = leaning[0]
        others = ", ".join(m for _, m, _ in leaning[1:5])
        out.append({"kind": "bad",
                    "title": f"{len(leaning)} model{'' if len(leaning) == 1 else 's'} "
                             f"answer{'s' if len(leaning) == 1 else ''} with a favourite letter",
                    "text": f"{worst_model} put {stats['top_share']:.0f}% of its answers on "
                            f"{stats['top_letter']} ({worst_skew:.0f} points of skew, "
                            f"{p_text(stats['marginal_test']['p'])}) while scoring "
                            f"{stats['accuracy']:.0f}% overall."
                            + (f" Also leaning: {others}." if others else "")
                            + " Check these rows in the wrong-answers-only grid: a preference that "
                              "survives there is a fallback, not a coincidence of the puzzles it "
                              "happened to get."})
    elif payload["per_model"]:
        out.append({"kind": "good", "title": "No model has a favourite letter",
                    "text": "Every model's answer spread is within noise of the letters it was "
                            "actually shown. Whatever is separating the good models from the bad "
                            "ones here, it is not one of them guessing the same letter every time."})

    # -- which letters are hard to reach --------------------------------------
    recall = {l: v for l, v in (core.get("recall") or {}).items() if v is not None}
    if len(recall) >= 2:
        low = min(recall, key=recall.get)
        high = max(recall, key=recall.get)
        gap = recall[high] - recall[low]
        precision = (core.get("precision") or {}).get(low)
        if gap >= 8:
            out.append({"kind": "warn", "title": f"Answer {low} is the hardest one to land on",
                        "text": f"When {low} was the correct answer the models found it "
                                f"{recall[low]:.0f}% of the time, against {recall[high]:.0f}% for "
                                f"{high} - a {gap:.0f} point gap between two letters that are "
                                f"interchangeable by construction."
                                + (f" When they did answer {low} they were right {precision:.0f}% "
                                   f"of the time." if precision is not None else "")})
        else:
            out.append({"kind": "good", "title": "No letter is harder to find than any other",
                        "text": f"Recall runs from {recall[low]:.0f}% ({low}) to "
                                f"{recall[high]:.0f}% ({high}), a spread small enough to be the "
                                f"luck of which puzzles each letter drew."})

    # -- errors: spread or concentrated ---------------------------------------
    error_grid = _grid(grids, "error_flow")
    if error_grid and error_grid["n"] >= MIN_ROW_TRIALS:
        cells = _strong_cells(error_grid, 1)
        if cells:
            row, col, residual, count = cells[0]
            out.append({"kind": "warn", "title": f"Errors concentrate on {row} being answered {col}",
                        "text": f"{count:,} of the {error_grid['n']:,} wrong answers are this one "
                                f"pair, {residual:+.1f} standard deviations more than an even "
                                f"spread of mistakes would put there. A specific confusion, rather "
                                f"than a uniform one, is a clue about what the models are "
                                f"misreading rather than just evidence that they are."})
        else:
            out.append({"kind": "note", "title": "Errors are spread evenly across the letters",
                        "text": f"No pair of letters is confused for another more than chance "
                                f"would explain across {error_grid['n']:,} wrong answers - the "
                                f"signature of reasoning that failed rather than of a rule being "
                                f"misapplied."})

    # -- everything else, grid by grid ----------------------------------------
    readings = [
        ("folds_answer_share", "how hard the puzzle was",
         "The answer spread changes with how hard the puzzle is",
         "The answers are spread the same way at every difficulty"),
        ("punch_quadrant_answer_share", "where the hole was punched",
         "Where the hole was punched changes what gets answered",
         "Where the hole was punched doesn't change what gets answered"),
        ("fold_direction_answer_share", "which directions the paper was folded in",
         "Which directions the paper was folded in changes what gets answered",
         "No fold direction pulls the answers one way"),
        ("effort_answer_share", "how much the model wrote",
         "Short answers and long answers go to different letters",
         "Answer length doesn't predict which letter comes out"),
        ("phase_answer_share", "how far into the run a trial was",
         "The answers drift over the course of a run",
         "No drift over the course of a run"),
        ("answer_transition", "what was answered last time",
         "The previous answer predicts the next one",
         "Each answer is independent of the one before it"),
        ("run_answer_share", "the wording of the direction names",
         "The wording changes what gets answered, not just how often it is right",
         "Every wording produced the same spread of answers"),
    ]
    for key, subject, bad_title, good_title in readings:
        grid = _grid(grids, key)
        if not grid or grid["n"] < MIN_ROW_TRIALS:
            continue
        test = grid["chi2"]
        if not test:
            continue
        if _moved(grid):
            detail = "; ".join(
                f"{row} answered {col} {count:,} times ({residual:+.1f} sd above expected)"
                for row, col, residual, count in _strong_cells(grid, 2))
            out.append({"kind": "bad", "title": bad_title,
                        "text": f"Chi-square across the grid: {p_text(test['p'])}, V "
                                f"{test['cramers_v']:.3f} over {grid['n']:,} trials, with each "
                                f"model tested on its own answers so this is not the field's "
                                f"mixture of habits showing through."
                                + (f" Pulling hardest: {detail}." if detail else "")
                                + f" Nothing about {subject} says which letter is correct, so this "
                                  f"is the answer responding to something other than the puzzle."})
        else:
            close = ", which is close enough to matter only if you have more trials" \
                if test["p"] < 0.05 else ""
            pooled = grid.get("pooled_chi2")
            mixture = ""
            if pooled and pooled["p"] < 0.01:
                mixture = (f" Worth knowing: pooling every model together instead makes this look "
                           f"like a real effect ({p_text(pooled['p'])}). It isn't - it is the "
                           f"field's mixture of letter habits showing through, and it disappears "
                           f"the moment each model is held to its own answers.")
            out.append({"kind": "good", "title": good_title,
                        "text": f"{p_text(test['p'])} with V {test['cramers_v']:.3f} over "
                                f"{grid['n']:,} trials{close} - the rows are interchangeable, which "
                                f"is what {subject} not reaching the answers looks like." + mixture})

    # -- accuracy grids: where it fails, rather than what it says --------------
    # The grids whose rows are models are read down their columns instead: that
    # models differ is not a finding, and the stratified test in the grid holds
    # each model fixed so the column is the only thing being asked about.
    for key, subject, title_bad, title_good in [
        ("punch_quadrant_accuracy", "where the hole was punched",
         "Accuracy depends on where the hole was punched",
         "Accuracy is the same wherever the hole was punched"),
        ("fold_plan_accuracy", "how the fold plan started and ended",
         "Accuracy depends on how the fold plan started and ended",
         "The order of the folds doesn't change accuracy"),
        ("model_quadrant_accuracy", "where the hole was punched",
         "Models have blind spots in particular corners of the sheet",
         "No model has a blind spot in one corner of the sheet"),
        ("shape_accuracy", "the shape the folded sheet ended up",
         "A tall folded sheet and a wide one are not equally easy",
         "The shape of the folded sheet doesn't change accuracy"),
        ("model_effort_accuracy", "how much the model wrote",
         "Writing more changes how often a model is right",
         "Writing more doesn't change how often a model is right"),
        ("model_letter_recall", "which letter was correct",
         "Models find some letters more often than others",
         "No letter is systematically harder for a model to land on"),
    ]:
        grid = _grid(grids, key)
        if not grid or grid["n"] < MIN_ROW_TRIALS or not grid["chi2"]:
            continue
        test = grid["chi2"]
        # Column averages give every row the same weight, so the comparison is
        # not tilted by whichever row happened to answer most of the trials.
        columns = [(v, grid["cols"][j]) for j, v in enumerate(grid.get("column_mean") or [])
                   if v is not None] if grid.get("stratified") else \
                  [(v, f"{grid['rows'][i]} / {grid['cols'][j]}")
                   for i, row in enumerate(grid["values"]) for j, v in enumerate(row)
                   if v is not None and grid["totals"][i][j] >= MIN_ROW_TRIALS]
        if len(columns) < 2:
            continue
        low, high = min(columns), max(columns)
        weighed = "averaged over the models, each counting once" if grid.get("stratified") \
            else "over the whole field"
        if _moved(grid, min_v=0.03):
            out.append({"kind": "bad", "title": title_bad,
                        "text": f"{high[0]:.0f}% correct at {high[1]} against {low[0]:.0f}% at "
                                f"{low[1]} ({weighed}); {p_text(test['p'])} across "
                                f"{grid['n']:,} trials"
                                + (", with each model held fixed so this is the column talking, "
                                   "not the gap between models" if grid.get("stratified") else "")
                                + f". Every cell here is the same puzzle at the same difficulty, so "
                                  f"a gap by {subject} is the model's, not the test's."})
        else:
            out.append({"kind": "good", "title": title_good,
                        "text": f"{p_text(test['p'])} across {grid['n']:,} trials, with the spread "
                                f"running from {low[0]:.0f}% at {low[1]} to {high[0]:.0f}% at "
                                f"{high[1]} ({weighed}) - not enough to clear both the significance "
                                f"and the effect-size bar, so {subject} is not where these models "
                                f"are losing trials."})

    return out


# =============================================================================
#  Plots
# =============================================================================
def _wrap(text: str, width: int = 18) -> str:
    return textwrap.fill(str(text), width)


def _title_pad(subtitle: str) -> float:
    """Room above the axes for the subtitle, so the title clears it instead of
    landing on top of the top line."""
    return 18 + 13 * (subtitle.count("\n") + 1)


def _subtitle(ax, text: str) -> None:
    """The gray line between the title and the axes - same placement as the
    single-run and comparison charts, so all three families read alike."""
    ax.annotate(text, xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 8),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=9, color=LABEL_GRAY, linespacing=1.5)


def _cell_text_color(cmap, norm, value) -> str:
    """White on dark cells, near-black on light ones, decided from the cell's
    own luminance rather than from a threshold on the value - which breaks the
    moment the colour scale changes."""
    r, g, b, _ = cmap(norm(value))
    return "#ffffff" if (0.299 * r + 0.587 * g + 0.114 * b) < 0.55 else "#1a1a1a"


def _grid_lines(ax, n_cols: int, n_rows: int) -> None:
    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.4)
    ax.tick_params(which="minor", length=0)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)


def _save(fig, out: Path) -> None:
    fig.tight_layout()
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _test_note(grid) -> str:
    """The grid's statistics as one line, in the words they should be read in:
    the p-value for "did anything move", Cramer's V for "by enough to care",
    and which of the two tests it came from."""
    test = grid.get("chi2")
    if not test:
        return "Too few rows or columns with anything in them to test"
    verdict = ("rows differ beyond noise" if test["p"] < 0.01 and test["cramers_v"] >= 0.05
               else "within noise of identical rows")
    unit = "row" if grid.get("kind") == "accuracy" else "model"
    how = ("all trials pooled" if not test.get("stratified") else
           f"the one {unit} with anything to test, on its own" if test["strata"] == 1 else
           f"each of the {test['strata']} {unit}s tested separately and summed")
    line = (f"Chi-square {test['stat']:,.1f} on {test['df']} df, {p_text(test['p'])}, "
            f"V {test['cramers_v']:.3f} ({how}) - {verdict}")
    pooled = grid.get("pooled_chi2")
    if pooled and (pooled["p"] < 0.01) != (test["p"] < 0.01):
        line += ("\nPooling the models instead would say " + p_text(pooled["p"]) +
                 " - that difference is the models' mixture of habits, not this grid")
    return line


def plot_distribution(grid, out: Path) -> None:
    """One distribution grid as a heatmap.

    Two decisions carry this chart. The numbers in the cells are row
    percentages (with the raw count under them), because the rows are almost
    never the same size and a model with twice the trials of another would
    otherwise be the darkest row on every chart for no reason but its trial
    count.

    The *colour*, though, is the deviation from what that column runs at across
    the whole grid - not the percentage itself. A grid of rows that all behave
    the same should look blank, and it does: white is "this row is doing what
    everyone does", red is "more of this answer than the field", blue is
    "less". Colouring by the raw share instead would paint every ordinary row
    the same mid-blue and leave the reader comparing shades to find the one
    that differs, which is the job the chart is supposed to be doing for them.
    Ringed cells are the ones whose deviation clears two (dashed) or three
    (solid) standard deviations, so the eye and the statistics agree.
    """
    counts = np.array(grid["counts"], dtype=float)
    residuals = np.array(grid["residuals"], dtype=float)
    row_totals = counts.sum(axis=1)
    grand = counts.sum()
    if not counts.size or grand <= 0:
        return
    with np.errstate(divide="ignore", invalid="ignore"):
        shares = np.where(row_totals[:, None] > 0, 100 * counts / row_totals[:, None], np.nan)
    field = 100 * counts.sum(axis=0) / grand           # what each column runs at overall
    deviation = shares - field[None, :]

    # The scale stops at the 95th percentile of the deviations rather than the
    # largest one: a single model answering 84% "A" would otherwise set the
    # contrast for the whole grid and leave every other row the same white.
    magnitudes = np.abs(deviation[~np.isnan(deviation)])
    limit = float(np.percentile(magnitudes, 95)) if magnitudes.size else 10.0
    limit = max(8.0, limit)
    saturated = bool(magnitudes.size and magnitudes.max() > 1.05 * limit)

    n_rows, n_cols = counts.shape
    cmap = plt.get_cmap("RdBu_r")
    norm = matplotlib.colors.TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit)
    fig, ax = plt.subplots(figsize=(max(6.6, 1.25 * n_cols + 4.2),
                                    max(3.8, 0.66 * n_rows + 3.0)))
    image = ax.imshow(np.nan_to_num(deviation), aspect="auto", cmap=cmap, norm=norm)

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels([f"{_wrap(c, 12)}\n({field[j]:.0f}% overall)"
                        for j, c in enumerate(grid["cols"])], fontsize=9)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels([f"{_wrap(r, 26)}\n(n={int(row_totals[i]):,})"
                        for i, r in enumerate(grid["rows"])], fontsize=8.5)
    ax.set_xlabel(grid["col_label"], color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel(grid["row_label"], color=LABEL_GRAY, fontsize=10)

    lines = ["Cells show that row's share and its trial count; colour is how far "
             "the share sits from what the column runs at overall"]
    if grid.get("rings", True):
        lines.append(f"Ringed: more (red) or less (blue) than expected by over two "
                     f"standard deviations, solid past three - rows under "
                     f"{MIN_ROW_TRIALS} trials are never ringed")
    lines.append(_test_note(grid))
    if grid.get("note"):
        lines.append(grid["note"])
    subtitle = "\n".join(textwrap.fill(line, 116) for line in lines)
    ax.set_title(grid["title"], fontsize=13, pad=_title_pad(subtitle))
    _subtitle(ax, subtitle)

    for i in range(n_rows):
        for j in range(n_cols):
            share = shares[i, j]
            if np.isnan(share):
                ax.text(j, i, "-", ha="center", va="center", fontsize=8, color="#9a9894")
                continue
            ax.text(j, i, f"{share:.0f}%\n{int(counts[i, j]):,}", ha="center", va="center",
                    fontsize=8.5, linespacing=1.35,
                    color=_cell_text_color(cmap, norm, deviation[i, j]))
            # A row of one or two trials will happily produce a 100% and an
            # enormous residual. Those rows keep their numbers - a model that
            # only got one thing wrong is worth seeing - but they are not
            # decorated as findings.
            if grid.get("rings", True) and row_totals[i] >= MIN_ROW_TRIALS \
                    and abs(residuals[i, j]) >= RESIDUAL_NOTABLE:
                strong = abs(residuals[i, j]) >= RESIDUAL_STRONG
                ax.add_patch(plt.Rectangle(
                    (j - 0.46, i - 0.46), 0.92, 0.92, fill=False,
                    edgecolor="#8c2f26" if residuals[i, j] > 0 else "#1c4e80",
                    linewidth=2.0 if strong else 1.2,
                    linestyle="-" if strong else (0, (3, 2))))

    # On a confusion grid proper the diagonal is the answer, so it is marked as
    # such rather than left to be inferred from where the colour happens to be.
    if grid.get("symmetric"):
        for i, name in enumerate(grid["rows"]):
            if name in grid["cols"]:
                ax.add_patch(plt.Rectangle(
                    (grid["cols"].index(name) - 0.5, i - 0.5), 1, 1, fill=False,
                    edgecolor="#2e8b57", linewidth=1.8))

    _grid_lines(ax, n_cols, n_rows)
    bar = fig.colorbar(image, ax=ax, shrink=0.75, pad=0.02,
                       extend="both" if saturated else "neither")
    bar.set_label("Percentage points above or below the column's overall share",
                  color=LABEL_GRAY, fontsize=9)
    _save(fig, out)


def plot_accuracy(grid, out: Path) -> None:
    """One accuracy grid as a heatmap, on a fixed 0-100 scale with the chance
    line marked on the colour bar.

    Fixed rather than stretched to the data: a grid whose cells all sit between
    18% and 24% is a page of models guessing, and a scale that spreads those six
    points across the whole colormap would draw it as a dramatic pattern.
    """
    values = np.array([[np.nan if v is None else v for v in row]
                       for row in grid["values"]], dtype=float)
    totals = np.array(grid["totals"], dtype=float)
    if not values.size:
        return

    n_rows, n_cols = values.shape
    cmap = plt.get_cmap("RdYlGn")
    norm = matplotlib.colors.Normalize(0, 100)
    fig, ax = plt.subplots(figsize=(max(6.4, 1.3 * n_cols + 4.0),
                                    max(3.6, 0.55 * n_rows + 2.8)))
    image = ax.imshow(values, aspect="auto", cmap=cmap, norm=norm)

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels([_wrap(c, 14) for c in grid["cols"]], fontsize=9)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels([_wrap(r, 30) for r in grid["rows"]], fontsize=9)
    ax.set_xlabel(grid["col_label"], color=LABEL_GRAY, fontsize=10)
    ax.set_ylabel(grid["row_label"], color=LABEL_GRAY, fontsize=10)
    lines = [f"Percent correct in each cell, with the trials it was measured over  |  "
             f"{CHANCE:.0f}% is guessing", _test_note(grid)]
    if grid.get("note"):
        lines.append(grid["note"])
    subtitle = "\n".join(textwrap.fill(line, 116) for line in lines)
    ax.set_title(grid["title"], fontsize=13, pad=_title_pad(subtitle))
    _subtitle(ax, subtitle)

    for i in range(n_rows):
        for j in range(n_cols):
            value = values[i, j]
            if np.isnan(value):
                ax.text(j, i, "-", ha="center", va="center", fontsize=8, color="#9a9894")
                continue
            ax.text(j, i, f"{value:.0f}%\nn={int(totals[i, j]):,}", ha="center", va="center",
                    fontsize=8.5, linespacing=1.35,
                    color=_cell_text_color(cmap, norm, value))

    _grid_lines(ax, n_cols, n_rows)
    bar = fig.colorbar(image, ax=ax, shrink=0.75, pad=0.02)
    bar.set_label("Accuracy (% of trials correct)", color=LABEL_GRAY, fontsize=9)
    # The chance line marked on the bar itself rather than beside it, where it
    # would collide with the bar's own label.
    bar.ax.axhline(CHANCE, color="#1a1a1a", linewidth=1.2)
    bar.ax.annotate("chance", xy=(0.5, CHANCE), xycoords=("axes fraction", "data"),
                    fontsize=7.5, color="#1a1a1a", ha="center", va="bottom",
                    path_effects=[pe.withStroke(linewidth=2.4, foreground="white")])
    _save(fig, out)


def plot_confusion_sheet(panels: list[tuple[str, dict]], out: Path, *,
                         title: str, subtitle: str) -> None:
    """A whole family of 5x5 confusions on one page - one panel per model, per
    fold count, or per run.

    The point of a sheet rather than twenty separate files is that a bias is a
    difference between panels, and a difference you have to remember between two
    downloads is one you will not see. Panels are row-normalised so a model with
    fewer trials still reads at the same contrast as one with more.
    """
    panels = [(name, grid) for name, grid in panels if grid["n"] > 0]
    if not panels:
        return
    columns = min(4, len(panels))
    rows_of_panels = math.ceil(len(panels) / columns)
    cmap = plt.get_cmap("Blues")
    norm = matplotlib.colors.Normalize(0, 100)

    fig, axes = plt.subplots(rows_of_panels, columns,
                             figsize=(3.15 * columns + 1.0, 3.35 * rows_of_panels + 1.4),
                             squeeze=False)
    for index, ax in enumerate(axes.flatten()):
        if index >= len(panels):
            ax.axis("off")
            continue
        name, grid = panels[index]
        counts = np.array(grid["counts"], dtype=float)
        totals = counts.sum(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            shares = np.where(totals[:, None] > 0, 100 * counts / totals[:, None], np.nan)
        ax.imshow(np.nan_to_num(shares), cmap=cmap, norm=norm, aspect="auto")
        ax.set_xticks(range(len(grid["cols"])))
        ax.set_xticklabels(grid["cols"], fontsize=8)
        ax.set_yticks(range(len(grid["rows"])))
        ax.set_yticklabels(grid["rows"], fontsize=8)
        accuracy = grid.get("accuracy")
        # A panel of sixteen trials sitting beside one of four thousand is a
        # perfectly round 100% next to a real result. The count is always
        # printed, and below the point where a 5x5 grid can say anything the
        # panel says so outright rather than leaving it to be worked out.
        thin = "  (too few to read)" if grid["n"] < 50 else ""
        ax.set_title(f"{_wrap(name, 26)}\n{accuracy:.0f}% correct · {grid['n']:,} trials{thin}"
                     if accuracy is not None else _wrap(name, 26),
                     fontsize=9.5, pad=6,
                     color="#7a7a7a" if thin else "#1a1a1a")
        for i in range(counts.shape[0]):
            for j in range(counts.shape[1]):
                share = shares[i, j]
                if np.isnan(share):
                    continue
                ax.text(j, i, f"{share:.0f}", ha="center", va="center", fontsize=7.5,
                        color=_cell_text_color(cmap, norm, share))
        for i, letter in enumerate(grid["rows"]):
            if letter in grid["cols"]:
                ax.add_patch(plt.Rectangle(
                    (grid["cols"].index(letter) - 0.5, i - 0.5), 1, 1,
                    fill=False, edgecolor="#31d17e", linewidth=1.6))
        _grid_lines(ax, len(grid["cols"]), len(grid["rows"]))

    # Both sit above the axes area rather than inside the padding tight_layout
    # reserves, so a two-line heading can't land on the top row of panels.
    # bbox_inches="tight" at save time keeps whatever ends up past y=1.
    fig.suptitle(title, fontsize=14, y=1.035)
    fig.text(0.5, 1.0, subtitle, ha="center", va="top", fontsize=9.5, color=LABEL_GRAY,
             wrap=True)
    fig.supxlabel("Model's answer", color=LABEL_GRAY, fontsize=10)
    fig.supylabel("Correct answer", color=LABEL_GRAY, fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.975))
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def build_all_plots(payload: dict[str, Any], plots_dir: Path) -> list[str]:
    """Draw every grid this selection produced, plus the three sheets.

    Any PNG left over from a previous, wider selection in the same folder is
    removed rather than left to be served next to charts it no longer belongs
    with - the folder is addressed by which runs are in the comparison, not by
    which filters were on when it was last drawn.
    """
    plots_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for grid in payload["grids"]:
        out = plots_dir / f"{grid['key']}.png"
        (plot_distribution if grid["kind"] == "distribution" else plot_accuracy)(grid, out)
        if out.exists():
            written.append(out.name)

    sheets = [
        ("model_confusion_sheet", payload["per_model"], "Every model's confusion matrix",
         "Correct answer down, given answer across; cells are the percent of that row. "
         "Green rings the diagonal - a panel with colour off it in one column has a favourite."),
        ("folds_confusion_sheet", payload["per_folds"], "Confusion matrix at each difficulty",
         "The same grid at each fold count. Watch a column darken as the puzzle gets harder: "
         "that is the field falling back on a letter as the geometry runs out."),
        ("run_confusion_sheet", payload["per_run"], "Confusion matrix for each experiment",
         "One panel per run, same models and difficulties underneath each. The puzzle is "
         "identical across these panels - only the direction words changed."),
    ]
    for key, source, title, subtitle in sheets:
        out = plots_dir / f"{key}.png"
        panels = [(stats.get("display") or name, stats["confusion"])
                  for name, stats in source.items() if stats.get("confusion")]
        if len(panels) < 2:
            out.unlink(missing_ok=True)
            continue
        plot_confusion_sheet(panels, out, title=title, subtitle=subtitle)
        if out.exists():
            written.append(out.name)

    keep = set(written)
    for stale in plots_dir.glob("*.png"):
        if stale.name not in keep:
            stale.unlink(missing_ok=True)
    return sorted(written)


# =============================================================================
#  Scoping, and the whole analysis in one call
# =============================================================================
def models_of(rows) -> set[str]:
    return {r.get("model_version", "unknown") for r in rows}


def folds_of(rows) -> list[int]:
    return sorted({int(r["num_folds"]) for r in rows if r.get("num_folds") is not None})


def scope_rows(rows, models: set[str] | None, folds: set[int] | None) -> list[dict]:
    """Trim rows to a set of models and fold counts.

    Same rule as the Compare page, for the same reason: two runs are only
    comparable over the models and difficulties they both actually ran, and a
    run that swept extra folds would otherwise bring its own difficulty mixture
    into every grid. Trials recorded before fold counts were written into
    results are kept - there is nothing to place them at, and dropping them
    would silently empty an old run.
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


def _breakdown(rows, key: str, title: str) -> dict[str, Any]:
    """The per-slice block the UI drills into and the sheets are drawn from:
    one confusion matrix per model / fold count / run, plus the two or three
    numbers that summarise it."""
    answered = Counter(answer_of(r) for r in rows)
    correct = sum(1 for r in rows if is_correct(r))
    top = max(LETTERS, key=lambda l: answered.get(l, 0)) if rows else None
    grid = confusion_of(rows, f"confusion_{key}", title,
                        "Correct answer down the side, given answer across the top.",
                        group="breakdown")
    return {
        # Keyed by the raw name everywhere (the page's selectors match on it);
        # this is the same thing spelled for a human, which is what the charts
        # put in their panel titles.
        "display": title,
        "trials": len(rows),
        "accuracy": round(100 * correct / len(rows), 1) if rows else None,
        "skew": letter_skew(answered),
        "top_letter": top,
        "top_share": round(100 * answered.get(top, 0) / len(rows), 1) if rows and top else None,
        "no_answer": answered.get(NO_ANSWER, 0),
        "marginal_test": grid.get("marginal_test"),
        "confusion": grid,
    }


def analyse(run_dirs, *, restrict: bool = True, only_models: list[str] | None = None,
            only_folds: list[int] | None = None,
            plots_dir: Path | None = None) -> dict[str, Any]:
    """Every confusion grid for a selection of runs, and the charts for them.

    The single entry point the Studio server calls, so the server never has to
    know how scoping works or which grids exist - adding one to
    ``build_grids`` is all it takes for it to appear on the page, in the JSON,
    and as a chart.
    """
    from llmits.paperfold import comparison as cmp     # label_profile, for run wording

    runs = [load_run(d) for d in run_dirs]
    runs = [r for r in runs if r["rows"]]
    if not runs:
        return {"ok": False, "error":
                "no answered trials in the selected run(s) - run some trials first"}

    names = [r["name"] for r in runs]
    shared_models = sorted(set.intersection(*(models_of(r["rows"]) for r in runs)))
    shared_folds = sorted(set.intersection(*(set(folds_of(r["rows"])) for r in runs)))
    all_models = sorted(set().union(*(models_of(r["rows"]) for r in runs)))
    all_folds = sorted(set().union(*(set(folds_of(r["rows"])) for r in runs)))

    model_scope = set(shared_models) if (restrict and len(runs) > 1) else set(all_models)
    fold_scope = set(shared_folds) if (restrict and len(runs) > 1) else set(all_folds)
    # Explicit picks from the page narrow whatever the scope rule already
    # allowed; they never widen it back out to models a run doesn't have.
    if only_models:
        model_scope &= set(only_models)
    if only_folds:
        fold_scope &= {int(f) for f in only_folds}
    if not model_scope:
        return {"ok": False, "error":
                "no models left after filtering - the selected runs share none of them"}
    if not fold_scope:
        return {"ok": False, "error":
                "the selected runs have no difficulty in common - "
                + "; ".join(f"{r['name']} ran at "
                            + ", ".join(f"{f}" for f in folds_of(r["rows"])) + " folds"
                            for r in runs)
                + ". Turn off \"compare like for like\" to read each run on its own "
                  "difficulties instead."}

    scoped: list[dict] = []
    per_run_rows: dict[str, list[dict]] = {}
    for run in runs:
        kept = scope_rows(run["rows"], model_scope, fold_scope)
        for row in kept:
            row["__run"] = run["name"]
        per_run_rows[run["name"]] = kept
        scoped.extend(kept)

    empty = [name for name, kept in per_run_rows.items() if not kept]
    if empty:
        return {"ok": False, "error":
                "no comparable trials left for " + ", ".join(empty) +
                " - turn off \"compare like for like\", or widen the model and "
                "difficulty filters."}

    models = _model_order(scoped, sorted(models_of(scoped)))
    folds = folds_of(scoped)
    answered = Counter(answer_of(r) for r in scoped)
    correct = sum(1 for r in scoped if is_correct(r))

    ctx = {"rows": scoped, "models": models, "folds": folds, "run_names": names}
    grids = build_grids(ctx)

    payload: dict[str, Any] = {
        "ok": True,
        "grids": grids,
        "models": models,
        "folds": folds,
        "scope": {
            "runs": names,
            "restricted": bool(restrict and len(runs) > 1),
            "models_used": sorted(model_scope & set(models_of(scoped))),
            "models_dropped": [m for m in all_models if m not in model_scope],
            "folds_used": folds,
            "folds_dropped": {r["name"]: [f for f in folds_of(r["rows"]) if f not in fold_scope]
                              for r in runs
                              if any(f not in fold_scope for f in folds_of(r["rows"]))},
            "trials": len(scoped),
            "accuracy": round(100 * correct / len(scoped), 1) if scoped else None,
            "skew": letter_skew(answered),
            "no_answer": answered.get(NO_ANSWER, 0),
            "answered": {l: answered.get(l, 0) for l in LETTERS},
        },
        "runs": [{
            "name": run["name"],
            "display": ar.display_name(run["name"]),
            "kind": cmp.label_profile(
                {"results": run["results"], "rows": per_run_rows[run["name"]]})["kind"],
            **{k: v for k, v in _breakdown(
                per_run_rows[run["name"]], run["name"], ar.display_name(run["name"])).items()
               if k != "confusion"},
        } for run in runs],
        "per_model": {m: _breakdown([r for r in scoped if r.get("model_version") == m], m, m)
                      for m in models},
        "per_run": {name: _breakdown(rows_, name, ar.display_name(name))
                    for name, rows_ in per_run_rows.items()} if len(runs) > 1 else {},
        "per_folds": {f"{f} folds": _breakdown(
            [r for r in scoped if r.get("num_folds") == f], f"{f}_folds", f"{f} folds")
            for f in folds} if len(folds) > 1 else {},
    }
    payload["findings"] = findings(payload)
    if plots_dir is not None:
        payload["plots"] = build_all_plots(payload, plots_dir)
    return payload


# =============================================================================
#  Where a confusion analysis lives on disk
# =============================================================================
def confusion_slug(names) -> str:
    """A stable folder name for one selection of runs, so re-opening the same
    selection overwrites its own charts instead of leaving a new pile behind
    every time the page is refreshed."""
    digest = hashlib.sha1("\n".join(sorted(names)).encode()).hexdigest()[:10]
    return f"cfm_{digest}"


def prune_confusions(root: Path, keep: int = 12) -> None:
    """Keep only the most recently written confusion folders - these are pure
    derived output, rebuildable from the runs in a second, so an unbounded pile
    of them is just clutter. Only folders this module named are ever touched."""
    if not root.exists():
        return
    folders = [d for d in root.iterdir() if d.is_dir() and d.name.startswith("cfm_")]
    for old in sorted(folders, key=lambda d: d.stat().st_mtime, reverse=True)[keep:]:
        for f in old.glob("*"):
            if f.is_file():
                f.unlink()
        try:
            old.rmdir()
        except OSError:
            pass          # something unexpected in there - leave it alone
