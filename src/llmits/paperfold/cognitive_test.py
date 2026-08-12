"""
paperfold/cognitive_test.py
============================

The paper-folding spatial-reasoning puzzle itself: fold a square grid, punch a
hole through the folded layers, and ask a solver to pick which of five
candidates matches the paper once fully unfolded. Ported from the original
standalone prototype; the grading logic and the fold/unfold grid math are
unchanged, and two things about how a puzzle is *generated* have moved on:

  * the paper is sized from the fold count (paper_size_for_folds) instead of
    always being 16x16, so more folds means a bigger sheet and the last folds
    always have paper left to halve - at 3 folds it still works out to the
    original 16x16;
  * fold directions are drawn balanced across the two axes
    (balanced_fold_plan) rather than uniformly at random, which is what keeps
    that sizing rule modest and every trial at a given fold count comparable.

``CognitiveTest.run()`` takes any ``solver(prompt: str) -> dict | None``
callable, so it has no idea which AI provider (or whether an AI at all)
answered the prompt - that wiring lives in paperfold/runner.py.
"""

import random
import copy
import re

# The four fold orientations the puzzle logic works in. build_prompt() can
# present these under placeholder names (see CognitiveTest's direction_labels)
# without changing anything about how folding/unfolding actually works -
# labeling is presentation only, never touches the grid math.
DIRECTIONS = ("north", "south", "east", "west")

# A bank of short, unambiguous, unrelated words to draw placeholder direction
# names from (paperfold/runner.py's "random per trial" mode samples 4 of
# these). Deliberately generic - no accidental compass/spatial connotation.
DEFAULT_LABEL_POOL = (
    "red", "blue", "green", "yellow", "purple", "orange",
    "pink", "teal", "gold", "silver", "indigo", "crimson",
)

# The smallest side the *folded* paper is ever allowed to end up with. One
# trial needs six distinct punch positions on the folded face (five candidates
# plus the real answer, all different, so no two choices can look alike), and
# every fold halves a side - so the paper has to start big enough that what's
# left after the last fold is still a real grid. At 4 there are at least 4x4 =
# 16 positions to draw those six from.
MIN_FOLDED_SIDE = 4


def random_direction_labels(pool=DEFAULT_LABEL_POOL):
    """A fresh random {direction: placeholder} mapping, one word per
    direction, no word reused."""
    return dict(zip(DIRECTIONS, random.sample(pool, len(DIRECTIONS))))


def folds_per_axis(num_folds: int) -> tuple[int, int]:
    """How ``num_folds`` folds are split between the two axes, as evenly as
    possible: (folds on the busier axis, folds on the other one)."""
    fewer = int(num_folds) // 2
    return int(num_folds) - fewer, fewer


def paper_size_for_folds(num_folds: int, min_folded_side: int = MIN_FOLDED_SIDE) -> tuple[int, int]:
    """The (width, height) a square paper must start at to survive
    ``num_folds`` folds - the answer to "how big does the paper have to be?".

    A fold halves one side, so a side taking k folds has to start at
    ``min_folded_side * 2**k``. balanced_fold_plan() never puts more than
    ceil(num_folds / 2) folds on the same axis, so that is the exponent the
    square is cut to:

        folds:  0    1    2    3      4      5      6      7      8
        paper:  4x4  8x8  8x8  16x16  16x16  32x32  32x32  64x64  64x64

    A 2-fold puzzle therefore gets a much smaller sheet than a 5-fold one,
    and 3 folds lands on 16x16 - exactly the fixed size this test used before
    paper size was derived from the fold count, so 3-fold runs are unchanged.
    """
    per_axis = folds_per_axis(num_folds)[0]
    side = int(min_folded_side) * 2 ** per_axis
    return side, side


def balanced_fold_plan(num_folds: int) -> list[str]:
    """A random fold sequence whose folds are split as evenly as possible
    between the vertical (north/south) and horizontal (east/west) axes.

    Folding only shrinks the axis it is applied to, so an unconstrained
    sequence has to be sized for its worst case - every fold landing on the
    same axis - which doubles the paper, and with it the prompt, for each
    extra fold. Balancing the axes means the paper only doubles every
    *second* fold, and it also means every trial at a given fold count is
    handed the same square sheet: an accuracy-vs-folds comparison isn't
    confounded by some trials getting a 4x128 strip and others a 32x32
    square.

    Which axis takes the extra fold when ``num_folds`` is odd is itself
    random, so neither axis is systematically folded more often.
    """
    busier, other = folds_per_axis(num_folds)
    axes = [("north", "south"), ("east", "west")]
    random.shuffle(axes)
    plan = [random.choice(axes[0]) for _ in range(busier)]
    plan += [random.choice(axes[1]) for _ in range(other)]
    random.shuffle(plan)
    return plan


class Paper:
    """Class representing a piece of paper that can be folded and punched."""
    def __init__(self, current_width=16, current_height=16, layer=1):
        # Store the original dimensions of the paper
        self.ORIGINAL_WIDTH = current_width
        self.ORIGINAL_HEIGHT = current_height
        # Store the current dimensions of the paper
        self.current_width = current_width
        self.current_height = current_height
        # The current face of the paper, represented as a 2D grid
        self.face = self.generate_face()
        # Track the orientation of folds applied to the paper
        self.fold_history = []
        # Track the number of layers of paper (doubles with each fold)
        self.layer = layer

    def generate_face(self):
        """Generate a blank 2D grid matching the current dimensions."""
        return [[0 for _ in range(self.current_width)] for _ in range(self.current_height)]

    def face_to_string(self):
        """Render the current face as a plain string grid."""
        return "\n".join(" ".join(str(c) for c in row) for row in self.face)

    def can_fold(self, orientation="north") -> bool:
        """Whether there is still enough paper left to fold this way - i.e.
        whether the side this fold halves is an even number of cells."""
        side = self.current_height if orientation in ("north", "south") else self.current_width
        return side >= 2 and side % 2 == 0

    def fold(self, orientation="north"):
        """Fold the paper in the given orientation."""
        if orientation not in DIRECTIONS:
            raise ValueError(f"Unknown fold orientation: {orientation!r}")
        if not self.can_fold(orientation):
            # Without this the paper silently folded itself out of existence:
            # a side of 1 halves to 0 (integer division), leaving an empty
            # face with nowhere to punch a hole. Size the paper up front with
            # paper_size_for_folds(num_folds) instead of folding past what it
            # can take.
            side = self.current_height if orientation in ("north", "south") else self.current_width
            raise ValueError(
                f"Paper is too small to fold {orientation}: that side is {side} "
                f"cell(s) ({self.current_width}x{self.current_height} after "
                f"{len(self.fold_history)} fold(s)). Start from a bigger sheet - "
                f"see paper_size_for_folds()."
            )
        # Halve the current dimensions based on the fold orientation
        if orientation in ("north", "south"):
            self.current_height //= 2
        else:
            self.current_width //= 2
        # Double the layer count to reflect the fold
        self.layer *= 2
        self.fold_history.append(orientation)
        self.face = self.generate_face()

    def punch(self, x, y):
        """Punch a hole at the given (x, y) coordinates on the current face of the paper.
        Returns True if the punch was successful (in bounds), False otherwise."""
        if 0 <= x < self.current_width and 0 <= y < self.current_height:
            self.face[y][x] = 1
            return True
        return False

    def unfold(self):
        """Unfold the paper back to its original state, poping the fold_history in the process."""
        while self.layer != 1:
            last_fold = self.fold_history.pop()
            if last_fold == "north":
                # Current face was the north half; mirror it downward.
                new_face = self.face + self.face[::-1]
            elif last_fold == "south":
                # Current face was the south half; mirror it upward.
                new_face = self.face[::-1] + self.face
            elif last_fold == "west":
                # Current face was the west half; mirror it rightward.
                new_face = [row + row[::-1] for row in self.face]
            elif last_fold == "east":
                # Current face was the east half; mirror it leftward.
                new_face = [row[::-1] + row for row in self.face]

            if last_fold in ("north", "south"):
                self.current_height *= 2
            else:
                self.current_width *= 2
            # Update the face and layer count after unfolding
            self.face = new_face
            self.layer //= 2


class CognitiveTest:
    """Class representing a cognitive test involving folding and punching paper."""
    def __init__(self, num_folds=3, width=None, height=None, direction_labels=None):
        # How many folds this puzzle is built for. The paper is sized from it
        # (rather than being a fixed 16x16 for every difficulty): a 5-fold
        # puzzle needs a far bigger sheet than a 2-fold one, or the last folds
        # would have nothing left to halve. width/height override it only for
        # callers that really want a specific sheet - fold() refuses anyway
        # once a paper runs out of room, so an undersized override fails loudly
        # instead of producing a broken puzzle.
        self.num_folds = int(num_folds)
        default_width, default_height = paper_size_for_folds(self.num_folds)
        self.test_paper = Paper(default_width if width is None else width,
                                default_height if height is None else height)
        self.choices = {"A": None, "B": None, "C": None, "D": None, "E": None}
        # Track the sequence of fold orientations applied to the test paper
        # This is done seperately because paper.unfold() will pop the fold history
        # So we need to keep a copy for the prompt
        self.fold_orientations = []
        # Track the position of the punched hole and the correct choice
        self.punch_position = None
        self.correct_choice = None
        # Positions already used, so no two choices
        # (including the correct one) can ever land on the same spot.
        self.used_positions = set()
        # Optional {"north": "yellow", "south": "green", "east": "blue",
        # "west": "red"}-style mapping. When set, build_prompt() explains and
        # uses these placeholder names instead of the real direction words -
        # a probe for whether a solver is doing real spatial reasoning or
        # just pattern-matching on "north"/"south"/"east"/"west" specifically.
        # None (the default) reproduces the original prompt exactly.
        self.direction_labels = direction_labels

    def fold(self, orientation):
        """Fold the test paper in the given orientation and record it."""
        self.test_paper.fold(orientation)
        self.fold_orientations.append(orientation)

    def fold_random(self, num_folds=None):
        """Fold the test paper n times in random orientations, spread across
        both axes so the sheet paper_size_for_folds() picked is guaranteed to
        take all of them (see balanced_fold_plan)."""
        if num_folds is None:
            num_folds = self.num_folds
        for orientation in balanced_fold_plan(num_folds):
            self.fold(orientation)

    def generate_choices(self):
        """Generate five choice papers by copying the test paper, """
        """and punching a hole at a random position in each, avoiding """
        """any position that's already been used by another choice."""
        for key in self.choices:
            candidate = copy.deepcopy(self.test_paper)
            remaining = [
                (px, py)
                for py in range(self.test_paper.current_height)
                for px in range(self.test_paper.current_width)
                if (px, py) not in self.used_positions
            ]
            if not remaining:
                print("[warning] No unused positions left; reusing a position.")
                x = random.randint(0, self.test_paper.current_width - 1)
                y = random.randint(0, self.test_paper.current_height - 1)
            else:
                x, y = random.choice(remaining)
            self.used_positions.add((x, y))
            candidate.punch(x, y)
            self.choices[key] = candidate

    def punch_random(self):
        """Punch the real test paper at a random in-bounds position that """
        """hasn't already been used by one of the decoy choices."""
        remaining = [
            (px, py)
            for py in range(self.test_paper.current_height)
            for px in range(self.test_paper.current_width)
            if (px, py) not in self.used_positions
        ]
        if not remaining:
            print("[warning] No unused positions left; reusing a position.")
            x = random.randint(0, self.test_paper.current_width - 1)
            y = random.randint(0, self.test_paper.current_height - 1)
        else:
            x, y = random.choice(remaining)
        self.used_positions.add((x, y))
        self.test_paper.punch(x, y)
        self.punch_position = (x, y)
        return x, y

    def generate_answer(self):
        """Sets a random choice to be the correct answer and returns it."""
        self.test_paper.unfold()
        correct_choice = random.choice(list(self.choices.keys()))
        self.choices[correct_choice] = self.test_paper
        # Unfold all other choice papers to their original state
        for choice_paper in self.choices.values():
            if choice_paper.layer != 1:
                choice_paper.unfold()
        # Store the correct choice for later evaluation
        self.correct_choice = correct_choice
        return correct_choice

    def build_prompt(self):
        """Build the text prompt sent to the AI model for evaluation. """
        """Returns a string containing the test description, fold sequence, and choice papers."""
        labels = self.direction_labels
        # When direction_labels is set, every direction word shown to the
        # model is the placeholder, never the real one - only this function's
        # own bookkeeping (fold_orientations, Paper.fold, unfold, ...) still
        # deals in real directions, so puzzle logic is unaffected.
        name = (lambda d: labels[d] if labels else d)

        lines = []
        if labels:
            legend = ", ".join(f"{labels[d]} means {d}" for d in DIRECTIONS)
            lines.append(
                "For this puzzle, fold directions are referred to by these "
                f"names instead of their usual ones: {legend}."
            )
        lines += [
            f"A square paper with dimensions {self.test_paper.ORIGINAL_WIDTH}x"
            f"{self.test_paper.ORIGINAL_HEIGHT} is folded in this order: "
            f"{' -> '.join(name(d) for d in self.fold_orientations)}.",
            f"After these folds, the papers dimensions are {self.folded_width}x"
            f"{self.folded_height}. "
            "A hole is then punched through all layers at one position on "
            "this folded paper. Here is the folded paper with the hole "
            "punched (1 = hole, 0 = no hole):",
            f"\n{self.folded_face}\n",
            "If this folded, punched paper were fully unfolded back to its "
            "original size, it would match exactly one of the five candidates "
            "below (A-E). 1 = hole, 0 = no hole.",
        ]
        for key, choice_paper in self.choices.items():
            lines.append(f"\nChoice {key}:")
            lines.append(choice_paper.face_to_string())
        lines.append(
            "\nWhich choice (A, B, C, D, or E) matches the paper above once "
            "fully unfolded? Respond with only the single letter."
        )
        return "\n".join(lines)

    def extract_choice(self, response_text):
        """Extract the predicted choice (A-E) from the AI model's response text."""
        """Returns the predicted choice as a single uppercase letter, or None if no valid choice is found."""
        text = response_text.strip()
        # First, look for explicit patterns indicating the final answer
        final_answer_patterns = [
            r"\\boxed\{([A-E])\}",
            r"final answer[^A-E]{0,20}([A-E])\b",
            r"answer is[:\s]*([A-E])\b",
        ]
        # If no explicit patterns are found, look for any standalone letters A-E in the text
        for pattern in final_answer_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).upper()
        # If no explicit patterns are found, look for any standalone letters A-E in the text
        # This is a fallback in case the model doesn't follow the expected format.
        matches = re.findall(r"\b([A-E])\b", text.upper())
        # Return the last match found, as it is likely to be the final answer.
        return matches[-1] if matches else None

    def run(self, num_folds=None, solver=None):
        """Run a single trial of the cognitive test, the solver will be the AIs API call."""
        if num_folds is not None and int(num_folds) != self.num_folds:
            # Paper size follows the fold count, so a count other than the one
            # this test was constructed for needs a fresh sheet. Safe here:
            # nothing has been folded or punched yet.
            self.num_folds = int(num_folds)
            self.test_paper = Paper(*paper_size_for_folds(self.num_folds))
        # Perform the random folds, generate the choice papers, punch the test paper, and determine the correct answer.
        self.fold_random(self.num_folds)
        self.generate_choices()
        x, y = self.punch_random()
        # Snapshot the folded, punched paper here,
        # generate_answer() below unfolds test_paper back to full size.
        # build_prompt() needs to show THIS state, not the unfolded one.
        self.folded_width = self.test_paper.current_width
        self.folded_height = self.test_paper.current_height
        self.folded_face = self.test_paper.face_to_string()
        correct_choice = self.generate_answer()
        prompt = self.build_prompt()
        # Call the solver (AI model) with the generated prompt, if a solver is provided.
        solver_result = solver(prompt) if solver else None
        # Compile the results of the trial into a dictionary
        result = {
            "num_folds": self.num_folds,
            # The sheet this trial started from. Recorded per trial because it
            # is derived from num_folds, so a run sweeping several fold counts
            # uses a different (bigger) paper for each of them.
            "paper_width": self.test_paper.ORIGINAL_WIDTH,
            "paper_height": self.test_paper.ORIGINAL_HEIGHT,
            "fold_history": list(self.fold_orientations),
            "punch_position": (x, y),
            "correct_choice": correct_choice,
            "prompt": prompt,
        }
        # If the solver returned a result, extract the predicted choice and other relevant information.
        if solver_result:
            predicted = self.extract_choice(solver_result["text"])
            result.update({
                "raw_response": solver_result["text"],
                "predicted_choice": predicted,
                "is_correct": predicted == correct_choice,
                "elapsed_seconds": solver_result["elapsed_seconds"],
                "total_tokens": solver_result["total_tokens"],
                "model_version": solver_result["model_version"],
            })
        else:
            result.update({"raw_response": None, "predicted_choice": None, "is_correct": None})
            # Return the result dictionary containing all relevant information about the trial.
        return result
