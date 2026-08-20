"""
llmits.paperfold.confusion
==========================

Confusion matrices for one paper-folding experiment, and nothing else.

``analysis.py`` answers "which model is best inside this run" and
``comparison.py`` answers "what did changing the wording do". Both read one bit
off each trial - right or wrong - and that bit is exactly where a bias hides. A
model that reasoned and got unlucky scores 20% on a five-way choice, and a model
that answers "C" to everything also scores 20%. No accuracy chart can separate
those two. A confusion matrix can, because it never collapses the two halves of
a trial: what the puzzle actually was stays on one axis, what the model said
stays on the other, and the diagonal is where they agree.

Everything off that diagonal is an error placed by *where it went*, which is a
shape rather than a tally. The bias shows up as a column: a letter that stays
dark all the way down, whatever the correct answer happened to be, is a letter
the model reaches for when it has stopped solving the puzzle.

One experiment at a time, at three levels of aggregation:

  * **Every model together** - the experiment's own matrix. A lean here is a
    fact about the prompt, since a bias shared by the whole field is unlikely
    to be seventeen coincidences.
  * **By family** - the models grouped by who built them. Providers train on
    their own data with their own formatting conventions, so a fallback letter
    is very often a family trait rather than a model one, and grouping is the
    only way to see that.
  * **Model by model** - where the habit actually lives. A single model with a
    favourite letter disappears into a field average; here it is a panel with a
    vertical stripe down it.

Each matrix carries the column marginal underneath it: how often each letter
was answered, against how often it was the right answer. Those two numbers
being equal is what "no bias" looks like, and the gap between them is the bias
measured in percentage points - checked against a chi-square goodness-of-fit
test, so a lean too small to distinguish from the luck of the draw is reported
as no lean at all.

Plots are written to a confusion directory as ``<key>.png``, one per matrix,
plus two small-multiple sheets (all the families on a page, all the models on a
page). Styling follows ``analysis`` and ``comparison`` so these read as part of
the same family as the charts on the other tabs.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import textwrap
from pathlib import Path
from typing import Any, Iterable

import matplotlib
matplotlib.use("Agg")

import matplotlib.colors
import matplotlib.pyplot as plt
import numpy as np

from llmits.paperfold import analysis as ar

LETTERS: list[str] = list(ar.LETTERS)
# The column for a trial the model answered but no letter could be read out of.
# Deliberately not filtered away: a condition that stops a model answering at
# all is a stronger result than one that makes it answer wrongly.
NO_ANSWER = "?"
LABEL_GRAY = ar.LABEL_GRAY
AXIS_DARK = "#4a4a4a"          # the headline half of an axis caption
CHANCE = 100.0 / len(LETTERS)  # five candidates, so guessing lands here

# How much a lean has to clear before it is called one at all. Both bars have
# to be cleared: with a few thousand trials a chi-square will happily flag a
# drift of half a percentage point, which is true and useless.
BIAS_ALPHA = 0.01
BIAS_SKEW = 3.0                # points away from an even fifth each

# Below this many trials a five-row matrix is mostly quantisation - four trials
# a row makes every cell a multiple of 25% - and the panel says so.
SMALL_SAMPLE = 25


# =============================================================================
#  Who built each model
# =============================================================================
# Matched in order, first hit wins. Keyed off the model name rather than the
# backend because the backend only says which API the call went through -
# DeepSeek, Llama, Qwen and Phi all arrive over the same Hugging Face backend
# and are four different families with four different training pipelines.
FAMILY_RULES: tuple[tuple[str, str], ...] = (
    (r"^gemini|^google/", "Google (Gemini)"),
    (r"^gpt|^o\d|^chatgpt|^openai/", "OpenAI (GPT)"),
    (r"claude|^anthropic/", "Anthropic (Claude)"),
    (r"deepseek", "DeepSeek"),
    (r"llama|^meta-", "Meta (Llama)"),
    (r"qwen", "Alibaba (Qwen)"),
    (r"phi-|^microsoft/", "Microsoft (Phi)"),
    (r"mistral|mixtral", "Mistral"),
    (r"gemma", "Google (Gemma)"),
    (r"grok|^xai/", "xAI (Grok)"),
    (r"command|^cohere/", "Cohere"),
)


def model_family(name: str, backend: str | None = None) -> str:
    """Which provider family a model belongs to.

    Falls back to the publisher prefix a Hugging Face repo id carries
    ("someone/their-model" -> "Someone"), and only then to the backend, so a
    model this project has never seen still lands somewhere sensible instead of
    in a growing "other" bucket that would make the family view useless.
    """
    lowered = str(name).lower()
    for pattern, family in FAMILY_RULES:
        if re.search(pattern, lowered):
            return family
    if "/" in str(name):
        publisher = str(name).split("/", 1)[0]
        return publisher[:1].upper() + publisher[1:]
    if backend:
        return str(backend)[:1].upper() + str(backend)[1:]
    return "Other"


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
        return "not enough data to test"
    if p < 0.0001:
        return "p less than 0.0001"
    return f"p = {p:.3f}"


def goodness_of_fit(observed: Iterable[float], expected: Iterable[float]) -> dict[str, Any] | None:
    """Chi-square goodness of fit of one distribution against another - how the
    answers were spread, against how the correct answers were.

    The right comparison for this test, and not the same as testing against a
    flat fifth each: the puzzle draws its correct letter at random, so over a
    few hundred trials the letters it actually handed out are themselves a
    little uneven, and holding the model to a perfectly flat distribution would
    charge it for the puzzle's own sampling noise.
    """
    obs = np.asarray(list(observed), dtype=float)
    exp = np.asarray(list(expected), dtype=float)
    keep = exp > 0
    obs, exp = obs[keep], exp[keep]
    if obs.size < 2 or exp.sum() <= 0 or obs.sum() <= 0:
        return None
    exp = exp * (obs.sum() / exp.sum())          # scale to the observed total
    stat = float(((obs - exp) ** 2 / exp).sum())
    df = obs.size - 1
    return {"stat": round(stat, 2), "df": int(df), "p": chi2_sf(stat, df),
            "min_expected": round(float(exp.min()), 1)}


# =============================================================================
#  Loading, and grading
# =============================================================================
def load_run(run_dir: Path) -> dict[str, Any]:
    """One run's results.json as {name, results, rows}.

    Unlike ``comparison.load_run`` this keeps trials whose answer couldn't be
    parsed - they are answers, just not letters. Trials that never reached a
    model (a load failure, a run stopped early) aren't in results.json in the
    first place, so nothing unanswerable is being counted either way.
    """
    results = json.loads((run_dir / "results.json").read_text())
    rows = [r for r in ar.flatten(results) if r.get("correct_choice")]
    return {"name": run_dir.name, "results": results, "rows": rows}


def answer_of(row: dict) -> str:
    """The letter a trial was answered with, or ``?`` when none could be read."""
    predicted = row.get("predicted_choice")
    return predicted if predicted in LETTERS else NO_ANSWER


def is_correct(row: dict) -> bool:
    """Graded here rather than trusting the stored flag, so a row from an older
    run is scored exactly the same way as a fresh one."""
    return answer_of(row) == row.get("correct_choice")


def answer_columns(rows) -> list[str]:
    """A-E, plus the no-answer column only when some trial actually needs it."""
    return LETTERS + ([NO_ANSWER] if any(answer_of(r) == NO_ANSWER for r in rows) else [])


def letter_skew(counts: dict[str, int], total: int) -> float:
    """How far a spread of answers is from an even fifth each, 0-100.

    Total variation distance from uniform: 0 is perfectly even, 80 is every
    answer on one letter. The same measure the Compare page reports, so a skew
    quoted there and one quoted here are the same number.
    """
    if not total:
        return 0.0
    return round(100 * sum(abs(counts.get(l, 0) / total - 1 / len(LETTERS))
                           for l in LETTERS) / 2, 1)


# =============================================================================
#  One confusion matrix
# =============================================================================
def confusion(rows, *, key: str, level: str, name: str,
              models: list[str] | None = None) -> dict[str, Any]:
    """The matrix, and everything needed to read it.

    ``level`` is which of the three views this belongs to ("all", "family" or
    "model") and only decides where it is shown. Everything numeric below is
    computed the same way whatever the level, so a family matrix and the model
    matrices inside it always add up.
    """
    cols = answer_columns(rows)
    counts = np.array([[sum(1 for r in rows
                            if r["correct_choice"] == truth and answer_of(r) == given)
                        for given in cols] for truth in LETTERS], dtype=float)
    n = float(counts.sum())
    row_totals = counts.sum(axis=1)        # how often each letter was the answer
    col_totals = counts.sum(axis=0)        # how often each letter was given
    correct = float(sum(counts[i][cols.index(l)] for i, l in enumerate(LETTERS)
                        if l in cols))

    with np.errstate(divide="ignore", invalid="ignore"):
        row_share = np.where(row_totals[:, None] > 0, 100 * counts / row_totals[:, None], np.nan)

    # The two column marginals, which is where a bias reads: how often each
    # letter was answered, against how often it was the right answer. Equal is
    # what no bias looks like; the gap between them is the lean, in points.
    answered = {l: (100 * col_totals[j] / n if n else 0.0) for j, l in enumerate(cols)}
    was_right = {l: (100 * row_totals[i] / n if n else 0.0) for i, l in enumerate(LETTERS)}
    lean = {l: round(answered.get(l, 0.0) - was_right.get(l, 0.0), 1) for l in LETTERS}

    letter_counts = {l: int(col_totals[cols.index(l)]) if l in cols else 0 for l in LETTERS}
    top = max(LETTERS, key=lambda l: letter_counts[l]) if n else None
    most_over = max(LETTERS, key=lambda l: lean[l]) if n else None
    bias_test = goodness_of_fit([letter_counts[l] for l in LETTERS],
                                [row_totals[i] for i in range(len(LETTERS))])
    skew = letter_skew(letter_counts, int(n))
    status = _bias_status(n, correct, skew, bias_test)

    return {
        "key": key, "level": level, "name": name,
        "models": sorted(models or {r.get("model_version", "unknown") for r in rows}),
        "rows": LETTERS, "cols": cols,
        "counts": counts.astype(int).tolist(),
        "row_share": [[None if math.isnan(v) else round(float(v), 1) for v in row]
                      for row in row_share],
        "row_totals": row_totals.astype(int).tolist(),
        "col_totals": col_totals.astype(int).tolist(),
        "n": int(n),
        "correct": int(correct),
        "accuracy": round(100 * correct / n, 1) if n else None,
        # Per-letter readings of the same grid, one along the rows and one down
        # the columns. High precision with low recall is a letter the model only
        # reaches for when it is sure; the reverse is one it falls back on.
        "recall": {l: (round(100 * counts[i][cols.index(l)] / row_totals[i], 1)
                       if row_totals[i] and l in cols else None)
                   for i, l in enumerate(LETTERS)},
        "precision": {l: (round(100 * counts[LETTERS.index(l)][cols.index(l)]
                                / col_totals[cols.index(l)], 1)
                          if l in cols and col_totals[cols.index(l)] else None)
                      for l in LETTERS},
        "answered_share": {l: round(answered.get(l, 0.0), 1) for l in LETTERS},
        "correct_share": {l: round(was_right.get(l, 0.0), 1) for l in LETTERS},
        "lean": lean,
        "letter_counts": letter_counts,
        "no_answer": int(col_totals[cols.index(NO_ANSWER)]) if NO_ANSWER in cols else 0,
        "skew": skew,
        "top_letter": top,
        "top_share": round(answered.get(top, 0.0), 1) if top else None,
        "most_over_picked": most_over,
        "bias_test": bias_test,
        "status": status,
        "leaning": status == "leaning",
        "verdict": _verdict(status, n, most_over, answered, was_right, lean, bias_test),
    }


def _bias_status(n: float, correct: float, skew: float,
                 bias_test: dict | None) -> str:
    """Which of four things this matrix is, before it is put into words.

    The middle case is the one worth having. Forty trials is not many, and a
    model that put 45% of its answers on one letter over forty trials will miss
    a 1-in-100 bar while being fairly obviously biased. Calling that "no bias
    found" is wrong in the direction that matters, so it gets its own verdict
    saying what was seen and that the run is too short to settle it.
    """
    if not n:
        return "empty"
    if bias_test and bias_test["p"] < BIAS_ALPHA and skew >= BIAS_SKEW:
        return "leaning"
    if skew >= 8 and bias_test and bias_test["p"] < 0.10:
        return "unsettled"
    if 100 * correct / n <= CHANCE + 5:
        return "chance"
    return "even"


def _verdict(status: str, n: float, most_over: str | None, answered: dict,
             was_right: dict, lean: dict, bias_test: dict | None) -> str:
    """One sentence under the matrix saying what it shows.

    Deliberately says "no lean" out loud when there isn't one. On a test whose
    whole point is catching a model that has stopped solving the puzzle, a
    matrix with a clean diagonal and even columns is the result you want, and
    leaving that unsaid would make the page look like it only ever found
    problems.
    """
    if status == "empty":
        return "No answered trials here."
    given = answered.get(most_over, 0.0)
    right = was_right.get(most_over, 0.0)
    gap = lean.get(most_over, 0.0)
    if status == "leaning":
        return (f"Answers lean toward {most_over}: it came back as the answer on "
                f"{given:.0f}% of trials, against the {right:.0f}% where it was actually "
                f"correct - {abs(gap):.0f} points more often than the puzzle called for "
                f"({p_text(bias_test['p'])}).")
    if status == "unsettled":
        return (f"{most_over} came back on {given:.0f}% of trials against the {right:.0f}% "
                f"where it was correct, but over only {int(n):,} trials that gap does not "
                f"clear the noise ({p_text(bias_test['p'])}). More trials would settle it.")
    if status == "chance":
        return ("No letter is favoured, but the diagonal is at chance - these answers are "
                "spread evenly because they are spread at random.")
    return (f"No letter is favoured: the answers are spread across A-E much as the correct "
            f"answers were ({p_text(bias_test['p']) if bias_test else 'too few trials to test'}).")


# =============================================================================
#  Plots
# =============================================================================
def _wrap(text: str, width: int = 18) -> str:
    return textwrap.fill(str(text), width)


def _cell_text_color(cmap, norm, value) -> str:
    """White on dark cells, near-black on light ones, decided from the cell's
    own luminance rather than from a threshold on the value - which breaks the
    moment the colour scale changes."""
    r, g, b, _ = cmap(norm(value))
    return "#ffffff" if (0.299 * r + 0.587 * g + 0.114 * b) < 0.55 else "#1a1a1a"


def _heading(fig, ax, title: str, lines: list[str]) -> None:
    """Title, then one short sentence per line underneath it.

    One idea per line and no separators between them. A heading that packs
    three facts onto one row divided by pipes reads as a status bar, and the
    reader has to parse the punctuation before they can read the sentence.
    """
    # Wrapped here rather than left to run: bbox_inches="tight" sizes the saved
    # PNG to its widest element, so one long sentence would stretch the whole
    # figure and leave the grid floating in the middle of it.
    wrapped = [w for line in lines for w in textwrap.wrap(line, 92)] or [""]
    body = "\n".join(wrapped)
    ax.set_title(title, fontsize=14, pad=20 + 15 * len(wrapped))
    ax.annotate(body, xy=(0.5, 1.0), xycoords="axes fraction", xytext=(0, 10),
                textcoords="offset points", ha="center", va="bottom",
                fontsize=10, color=LABEL_GRAY, linespacing=1.6)


def _axis_captions(ax, *, x_title: str, x_note: str, y_title: str, y_note: str,
                   x_pad: float = 34, y_pad: float = 60,
                   y_centre: float | None = None) -> None:
    """Both axes captioned in two parts: what the axis is, then a short line
    saying what that means in the puzzle.

    Two text objects per axis rather than one label, because the two halves are
    doing different jobs - the first names the axis, the second explains it -
    and a reader who already knows the first should be able to skip the second
    at a glance. Matplotlib will not size two parts of one label differently,
    so they are placed here instead, at offsets that clear the tick labels this
    module writes.
    """
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.annotate(x_title, xy=(0.5, 0), xycoords="axes fraction", xytext=(0, -x_pad),
                textcoords="offset points", ha="center", va="top",
                fontsize=11.5, color=AXIS_DARK, fontweight="bold")
    ax.annotate(x_note, xy=(0.5, 0), xycoords="axes fraction", xytext=(0, -x_pad - 17),
                textcoords="offset points", ha="center", va="top",
                fontsize=9.5, color=LABEL_GRAY)
    # Anchored to the middle row of the grid rather than to the middle of the
    # axes: the axes are taller than the grid (the marginal strip lives in the
    # space below it), so an axes-centred caption would sit low and read as a
    # label for the strip.
    coords = "axes fraction" if y_centre is None else ("axes fraction", "data")
    anchor = (0, 0.5) if y_centre is None else (0, y_centre)
    ax.annotate(y_title, xy=anchor, xycoords=coords, xytext=(-y_pad, 0),
                textcoords="offset points", ha="center", va="center", rotation=90,
                fontsize=11.5, color=AXIS_DARK, fontweight="bold")
    ax.annotate(y_note, xy=anchor, xycoords=coords, xytext=(-y_pad - 16, 0),
                textcoords="offset points", ha="center", va="center", rotation=90,
                fontsize=9.5, color=LABEL_GRAY)


X_TITLE = "What the model answered"
X_NOTE = "the letter it picked out of the five candidates it was shown"
Y_TITLE = "What the answer actually was"
Y_NOTE = "the letter matching the paper once it is unfolded"


def _marginal_strip(ax, matrix, n_rows: int, n_cols: int, cmap, norm) -> None:
    """The column marginal, drawn in the space below the grid.

    This is where a bias reads, so it belongs on the matrix rather than in a
    caption: for each letter, how often it was given as an answer against how
    often it was the right answer. The two matching is what no bias looks like;
    the gap is the lean, coloured only when it is large enough to be worth
    looking at.
    """
    base = n_rows - 0.5
    ax.axhline(base + 0.28, color="#c9c9c9", linewidth=1.0)
    # Labelled down the right-hand margin rather than the left: the left is
    # already carrying the row ticks and both axis captions, and a third column
    # of text there would collide with them on any narrow figure.
    for offset, text, color in ((0.62, "given as the answer", "#1a1a1a"),
                                (1.02, "was the correct answer", LABEL_GRAY),
                                (1.42, "difference", LABEL_GRAY)):
        ax.annotate(text, xy=(n_cols - 0.4, base + offset), xycoords="data", ha="left",
                    va="center", fontsize=8.5, color=color, annotation_clip=False)
    for j, letter in enumerate(matrix["cols"]):
        answered = matrix["answered_share"].get(letter)
        was_right = matrix["correct_share"].get(letter)
        if answered is None:
            continue
        ax.text(j, base + 0.62, f"{answered:.0f}%", ha="center", va="center",
                fontsize=9, color="#1a1a1a")
        ax.text(j, base + 1.02, f"{was_right:.0f}%" if was_right is not None else "-",
                ha="center", va="center", fontsize=9, color=LABEL_GRAY)
        gap = matrix["lean"].get(letter)
        if gap is None:
            continue
        strong = abs(gap) >= 5
        ax.text(j, base + 1.42, f"{gap:+.0f}", ha="center", va="center",
                fontsize=9, fontweight="bold" if strong else "normal",
                color=("#c0392b" if gap > 0 else "#1c4e80") if strong else LABEL_GRAY)


def plot_matrix(matrix, out: Path, *, experiment: str) -> None:
    """One confusion matrix as a heatmap.

    Cells are row percentages with the trial count under them - the rows are
    rarely the same size, and colouring by raw counts would just draw whichever
    letter the puzzle happened to pick most often. Reading across a row is "when
    the answer was this, here is what came back"; reading down a column is "here
    is what this model reaches for", which is the reading a bias lives in.
    """
    counts = np.array(matrix["counts"], dtype=float)
    if not counts.size or not matrix["n"]:
        return
    shares = np.array([[np.nan if v is None else v for v in row]
                       for row in matrix["row_share"]], dtype=float)
    n_rows, n_cols = counts.shape

    cmap = plt.get_cmap("Blues")
    norm = matplotlib.colors.Normalize(0, 100)
    fig, ax = plt.subplots(figsize=(max(6.8, 1.15 * n_cols + 4.4), 6.2))
    ax.imshow(np.nan_to_num(shares), aspect="auto", cmap=cmap, norm=norm)

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels([("no letter\nin the reply" if c == NO_ANSWER else c)
                        for c in matrix["cols"]], fontsize=11)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels([f"{l}\n{matrix['row_totals'][i]:,} trials"
                        for i, l in enumerate(matrix["rows"])], fontsize=10)
    ax.tick_params(length=0)

    accuracy = matrix["accuracy"] or 0.0
    lines = [_headline_line(matrix, experiment),
             f"{matrix['n']:,} trials, {accuracy:.0f}% of them answered correctly, "
             f"against {CHANCE:.0f}% for guessing",
             matrix["verdict"]]
    _heading(fig, ax, _matrix_title(matrix, experiment), lines)
    _axis_captions(ax, x_title=X_TITLE, x_note=X_NOTE, y_title=Y_TITLE, y_note=Y_NOTE,
                   y_centre=(n_rows - 1) / 2)

    for i in range(n_rows):
        for j in range(n_cols):
            share = shares[i, j]
            if np.isnan(share):
                ax.text(j, i, "-", ha="center", va="center", fontsize=9, color="#9a9894")
                continue
            ax.text(j, i, f"{share:.0f}%\n{int(counts[i, j]):,}", ha="center", va="center",
                    fontsize=10, linespacing=1.4, color=_cell_text_color(cmap, norm, share))

    # The diagonal is the answer, so it is marked as such rather than left to be
    # inferred from where the dark cells happen to be.
    for i, letter in enumerate(matrix["rows"]):
        if letter in matrix["cols"]:
            ax.add_patch(plt.Rectangle(
                (matrix["cols"].index(letter) - 0.5, i - 0.5), 1, 1,
                fill=False, edgecolor="#2e8b57", linewidth=2.2, zorder=5))

    ax.set_xticks(np.arange(-0.5, n_cols, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, n_rows, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.6)
    ax.tick_params(which="minor", length=0)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)

    ax.set_ylim(n_rows + 1.2, -0.5)          # room under the grid for the marginal
    _marginal_strip(ax, matrix, n_rows, n_cols, cmap, norm)
    fig.tight_layout()
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _matrix_title(matrix, experiment: str) -> str:
    """Every title names the experiment, so a downloaded PNG says which run it
    came from instead of depending on the page it was downloaded from."""
    run = ar.display_name(experiment)
    if matrix["level"] == "all":
        return f"Every model on the {run} experiment"
    if matrix["level"] == "family":
        return f"{matrix['name']} on the {run} experiment"
    return f"{matrix['name']} on the {run} experiment"


def _headline_line(matrix, experiment: str) -> str:
    count = len(matrix["models"])
    if matrix["level"] == "all":
        return f"All {count} model{'' if count == 1 else 's'} pooled together"
    if matrix["level"] == "family":
        return (f"{count} model{'' if count == 1 else 's'} from this family: "
                + ", ".join(matrix["models"][:4])
                + (", and others" if count > 4 else ""))
    return "One model on its own"


def plot_sheet(matrices: list[dict], out: Path, *, experiment: str,
               title: str, note: str) -> None:
    """A whole level on one page - every family, or every model.

    A sheet rather than a folder of separate files because a bias is a
    difference between panels, and a difference you have to remember between two
    downloads is one you will not see. Panels are row-normalised so a model with
    fewer trials still reads at the same contrast as one with more.
    """
    matrices = [m for m in matrices if m["n"] > 0]
    if len(matrices) < 2:
        return
    columns = min(4, len(matrices))
    rows_of_panels = math.ceil(len(matrices) / columns)
    cmap = plt.get_cmap("Blues")
    norm = matplotlib.colors.Normalize(0, 100)

    fig, axes = plt.subplots(rows_of_panels, columns,
                             figsize=(3.3 * columns + 1.2, 3.75 * rows_of_panels + 1.6),
                             squeeze=False)
    for index, ax in enumerate(axes.flatten()):
        if index >= len(matrices):
            ax.axis("off")
            continue
        matrix = matrices[index]
        shares = np.array([[np.nan if v is None else v for v in row]
                           for row in matrix["row_share"]], dtype=float)
        ax.imshow(np.nan_to_num(shares), cmap=cmap, norm=norm, aspect="auto")
        ax.set_xticks(range(len(matrix["cols"])))
        ax.set_xticklabels(matrix["cols"], fontsize=8.5)
        ax.set_yticks(range(len(matrix["rows"])))
        ax.set_yticklabels(matrix["rows"], fontsize=8.5)
        ax.tick_params(length=0)
        # Each fact on its own line. Run together on one, a long panel caption
        # overflows into the neighbouring panel's title, and on a sheet of
        # sixteen panels there is nowhere for it to go.
        # Flagged only when a panel is genuinely too thin to read - five rows
        # over twenty trials is four trials a row, and every cell is then a
        # multiple of 25%. A normal run of thirty or forty trials per model is
        # not remarkable, and marking all seventeen panels for it would bury
        # the one that really is short.
        thin = matrix["n"] < SMALL_SAMPLE
        notes = []
        if matrix["status"] == "leaning":
            notes.append(f"leans {matrix['most_over_picked']}")
        elif matrix["status"] == "unsettled":
            notes.append(f"may lean {matrix['most_over_picked']}")
        if thin:
            notes.append(f"only {matrix['n']:,} trials, read with care")
        caption = [_wrap(matrix["name"], 24),
                   f"{matrix['accuracy']:.0f}% correct on {matrix['n']:,} trials"]
        if notes:
            caption.append(" \u00b7 ".join(notes))
        ax.set_title("\n".join(caption), fontsize=9.5, pad=6,
                     color="#7a7a7a" if thin else "#1a1a1a", linespacing=1.35)
        for i in range(len(matrix["rows"])):
            for j in range(len(matrix["cols"])):
                share = shares[i, j]
                if np.isnan(share):
                    continue
                ax.text(j, i, f"{share:.0f}", ha="center", va="center", fontsize=8,
                        color=_cell_text_color(cmap, norm, share))
        for i, letter in enumerate(matrix["rows"]):
            if letter in matrix["cols"]:
                ax.add_patch(plt.Rectangle(
                    (matrix["cols"].index(letter) - 0.5, i - 0.5), 1, 1,
                    fill=False, edgecolor="#31d17e", linewidth=1.8, zorder=5))
        ax.set_xticks(np.arange(-0.5, len(matrix["cols"]), 1), minor=True)
        ax.set_yticks(np.arange(-0.5, len(matrix["rows"]), 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=1.4)
        ax.tick_params(which="minor", length=0)
        ax.spines[["top", "right", "left", "bottom"]].set_visible(False)

    fig.suptitle(f"{title} on the {ar.display_name(experiment)} experiment",
                 fontsize=14, y=1.035)
    fig.text(0.5, 1.0, note, ha="center", va="top", fontsize=10, color=LABEL_GRAY)
    fig.text(0.5, -0.008, X_TITLE + "\n" + X_NOTE, ha="center", va="top",
             fontsize=10.5, color=AXIS_DARK, linespacing=1.5)
    fig.text(-0.006, 0.5, Y_TITLE + "\n" + Y_NOTE, ha="center", va="bottom",
             rotation=90, fontsize=10.5, color=AXIS_DARK, linespacing=1.5)
    fig.tight_layout(rect=(0.012, 0.02, 1, 0.975))
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)


def build_all_plots(payload: dict[str, Any], plots_dir: Path) -> list[str]:
    """One PNG per matrix, plus the two sheets.

    Any PNG left over from a previous analysis in the same folder is removed
    rather than served next to charts it no longer belongs with - the folder is
    addressed by which experiment it is for, not by which models it had when it
    was last drawn.
    """
    plots_dir.mkdir(parents=True, exist_ok=True)
    experiment = payload["experiment"]["name"]
    written: list[str] = []

    for matrix in [payload["overall"], *payload["families"], *payload["models"]]:
        out = plots_dir / f"{matrix['key']}.png"
        plot_matrix(matrix, out, experiment=experiment)
        if out.exists():
            written.append(out.name)

    sheets = [
        ("sheet_by_family", payload["families"], "Every provider family",
         "One panel per family, cells are the percent of that row. Green rings the "
         "diagonal, so colour anywhere else in one column is a letter that family "
         "reaches for."),
        ("sheet_by_model", payload["models"], "Every model",
         "One panel per model, cells are the percent of that row. A vertical stripe "
         "is a model with a favourite letter, and it is unmistakable next to the "
         "panels that do not have one."),
    ]
    for key, source, title, note in sheets:
        out = plots_dir / f"{key}.png"
        if len(source) < 2:
            out.unlink(missing_ok=True)
            continue
        plot_sheet(source, out, experiment=experiment, title=title, note=note)
        if out.exists():
            written.append(out.name)

    keep = set(written)
    for stale in plots_dir.glob("*.png"):
        if stale.name not in keep:
            stale.unlink(missing_ok=True)
    return written


# =============================================================================
#  The whole analysis in one call
# =============================================================================
def _safe_key(prefix: str, name: str) -> str:
    """A filename-safe key for a matrix, unique within one analysis. Model names
    carry slashes and dots ("deepseek-ai/DeepSeek-V3.2"), so they are flattened
    rather than used to build a path."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_") or "unnamed"
    return f"{prefix}_{slug}"[:80]


def analyse(run_dir: Path, *, plots_dir: Path | None = None) -> dict[str, Any]:
    """Every confusion matrix for one experiment, and the charts for them.

    The single entry point the Studio server calls. One run in, three levels of
    matrix out - the whole field, each provider family, each model - with the
    models ranked best first at both of the lower levels, so reading down the
    page is reading a leaderboard and a panel that breaks the order is visibly
    doing so.
    """
    run = load_run(Path(run_dir))
    rows = run["rows"]
    if not rows:
        return {"ok": False, "error":
                "this run has no answered trials yet - run some on the Paper Folding tab first"}

    by_model: dict[str, list[dict]] = {}
    backends: dict[str, str | None] = {}
    for r in rows:
        model = r.get("model_version", "unknown")
        by_model.setdefault(model, []).append(r)
        backends.setdefault(model, r.get("backend"))

    def accuracy_of(model_rows) -> float:
        return 100 * sum(1 for r in model_rows if is_correct(r)) / len(model_rows)

    ordered_models = sorted(by_model, key=lambda m: (-accuracy_of(by_model[m]), m))

    families: dict[str, list[str]] = {}
    for model in ordered_models:
        families.setdefault(model_family(model, backends.get(model)), []).append(model)
    ordered_families = sorted(
        families, key=lambda f: (-sum(accuracy_of(by_model[m]) for m in families[f])
                                 / len(families[f]), f))

    overall = confusion(rows, key="all_models", level="all", name="Every model",
                        models=ordered_models)
    family_matrices = [
        confusion([r for m in families[family] for r in by_model[m]],
                  key=_safe_key("family", family), level="family", name=family,
                  models=families[family])
        for family in ordered_families]
    model_matrices = [
        confusion(by_model[model], key=_safe_key("model", model), level="model",
                  name=model, models=[model])
        for model in ordered_models]

    results = run["results"]
    fold_counts = results.get("fold_counts") or [results.get("num_folds", 3)]
    payload: dict[str, Any] = {
        "ok": True,
        "experiment": {
            "name": run["name"],
            "display": ar.display_name(run["name"]),
            "trials": len(rows),
            "models": ordered_models,
            "families": {f: families[f] for f in ordered_families},
            "direction_mode": results.get("direction_mode", "real"),
            "direction_labels": (results.get("config_fingerprint") or {}).get("direction_labels"),
            "fold_counts": sorted(fold_counts),
            "accuracy": round(100 * sum(1 for r in rows if is_correct(r)) / len(rows), 1),
        },
        "overall": overall,
        "families": family_matrices,
        "models": model_matrices,
    }
    if plots_dir is not None:
        payload["plots"] = build_all_plots(payload, plots_dir)
    return payload


# =============================================================================
#  Where an analysis lives on disk
# =============================================================================
def confusion_slug(name: str) -> str:
    """A stable folder name for one experiment, so re-opening it overwrites its
    own charts instead of leaving a new pile behind every time."""
    return f"cfm_{hashlib.sha1(str(name).encode()).hexdigest()[:10]}"


def prune_confusions(root: Path, keep: int = 12) -> None:
    """Keep only the most recently written folders - these are pure derived
    output, rebuildable from the runs in a second, so an unbounded pile of them
    is just clutter. Only folders this module named are ever touched."""
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
