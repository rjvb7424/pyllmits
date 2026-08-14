# 🧩 Pyllmits Documentation & User Guide

_Last updated: August 13, 2026_

> 📓 This guide is also available as an interactive [Google Colab notebook](https://colab.research.google.com/drive/1FRfuSSkJzP3bWz3_0Yi2PcraNPBK10_J?usp=sharing).

**Pyllmits** tests whether AI models can actually do spatial reasoning, using two very different challenges:

1. **Crafter** — drop a model into a hand-built 2D survival world and see if it can navigate, gather resources, and complete an objective, using nothing but a text description of what it sees each turn.
2. **Paper Folding** — a classic spatial puzzle: fold a grid, punch a hole, and ask the model which of five unfolded results matches. You can even swap "north/south/east/west" for made-up words, to check whether a model actually understands direction or just recognizes those specific words.

Both experiments run through the same interface, so testing OpenAI, Gemini, and Hugging Face models side by side is just a matter of adding them to the same run. This guide walks through the website itself — the pages, what they're for, and how they fit together.

**Contents**
1. [Setup](#1--setup)
2. [Adding your API keys](#2--adding-your-api-keys)
3. [Testing a model in Crafter](#3--testing-a-model-in-crafter)
4. [Testing a model with Paper Folding](#4--testing-a-model-with-paper-folding)
5. [Putting it to use](#5--putting-it-to-use)

## 1 · Setup

Three lines gets you in:

```python
!pip install pyllmits
import main
main.main()
```

Running that cell starts a small local server and prints a link — click it and you're in.

(Outside Colab: `pip install pyllmits`, then run `llmits` in a terminal. It opens a browser tab for you automatically.)

## 2 · Adding your API keys

The first thing you'll see is a welcome screen asking for API keys — OpenAI, Gemini, Hugging Face. Paste in whichever ones you have; you don't need all three, just the providers whose models you actually want to test.

Keys are saved locally and never shown back to you in plain text. You can add, remove, or check them at any point later from the **Providers** page, without restarting anything.

## 3 · Testing a model in Crafter

**Configs** is where every experiment you've set up lives, as a card: its world size, its objective, how many trials it's completed, and which models are in it. From each card you can **Run** it, **Edit** it, **Duplicate** it to try a variation, or **Delete** it.

Hit **+ New config** (or **Edit** an existing one) and you land in the **Editor** — this is where an experiment actually gets built. Give it a name, decide how many trials and turns each one gets, and pick a goal (collect wood, craft a pickaxe, defeat a zombie...). The world itself is a grid you paint by hand: click a tile type — grass, water, trees, stone, a zombie, the player's starting spot — and click it onto the map. Below that is the prompt the model will actually see, and the list of models you want to test — add as many as you like, mixing providers freely.

Once it's set up, head to **Run**, pick the config, and hit **Start**. It runs in the background — **Pause** it any time and **Start** picks it up exactly where it left off, or **Stop** it for good — while a live panel shows exactly what's happening turn by turn: which model is playing, what it's looking at, what it just replied, and how long it took to think.

When a run finishes (or even partway through one), **Graphs** turns the results into charts — success rate per model, how long each one took to respond, which trials succeeded or failed — so you can compare models at a glance. If you change something and rerun, hit **Regenerate graphs** to refresh them without rerunning the experiment. **Download all** saves every chart straight to your computer. **Videos** does the same thing for the actual gameplay — a replay clip per model, per run.

Want to test more? Raise the trial count on a config you've already run, or drop in a new model, and hitting Run again only does the new work — it never throws out what's already there.

## 4 · Testing a model with Paper Folding

Paper Folding has its own page, separate from Crafter, with everything on one screen.

**Setup** is where you name a run, decide how many trials each puzzle gets and how hard those puzzles are, and pick your models — same mix-and-match across providers as Crafter. The one thing unique to this test is **direction names**: leave it on real names, type in your own placeholder words (fold "blue-wise" instead of "north"), or let it pick fresh random words for every single trial. That last option is the real test — if a model's accuracy holds up even when the words are meaningless and different every time, that's a much stronger sign it's actually reasoning about the fold rather than just recognizing "north."

**Folds from / to** is how you set the difficulty. Leave both on the same number for one fixed difficulty, or set a range — say 3 to 6 — and the run does your trial count at 3 folds, then the same again at 4, at 5 and at 6. The paper grows to match: every fold halves the sheet, so a 6-fold puzzle starts from a much bigger square than a 2-fold one (16×16 at three folds, 32×32 at six) and none of the folds ever run out of paper. Out of that comes the **accuracy by number of folds** graph — one line per model, folds along the bottom, percent correct up the side. That curve is the interesting part: a model that's really tracking the geometry slides down gradually as folds pile up, while one that was guessing sits flat on the 20% chance line from the start.

Already run something and want to pick up where you left off? The **"resume or edit a previous run"** menu at the top of Setup loads an old run right back into the form — raise the trial count and only the missing trials run, add a new model and just that one starts fresh, or widen the fold range and only the newly added fold counts get run.

**Run** starts it, with a live status panel showing the current model, trial, how many folds this puzzle has (and the paper size that goes with it), its last answer, and — if you're using placeholder words — exactly which words meant which direction on that trial. **Graphs**, right below it, works exactly like Crafter's: pick a run, view or regenerate its charts, or delete it once you're done with it.

Three of those charts are built for comparing runs rather than models: **average accuracy**, **average token consumption** and **average response time**. Each is a single bar — the whole run boiled down to one number — with a thin line through it showing the spread it's hiding (lowest model to highest). Accuracy says whether the change worked; tokens and response time say what it cost, which is the part a pass/fail number hides: made-up direction words that leave accuracy untouched but double the tokens didn't leave the models unbothered, they just made them work harder for the same answer.

The same average also appears as an extra bar on top of each "by model" ranking, so you can see at a glance which models sit above the run's average and which below. And if the run swept a fold range, every average graph adds a bar per fold count too — the difficulty trend as one averaged shape, instead of a dozen crossing lines.

## 5 · Putting it to use

The point of all this is comparison: run the same setup against several models at once, and the graphs show you who's actually good at this versus who just talks a good game. Because everything (results, graphs, replays) is saved to disk the moment it's produced, you can walk away mid-run, come back later, add a model you forgot, or push the trial count higher — and pick up exactly where you left off instead of starting over.

The Paper Folding side pushes that comparison one step further, in two directions. Run it once with real direction names, once with random placeholder words, and compare the two: a big drop in accuracy between them is the clearest signal you'll get that a model's "spatial reasoning" was leaning on the words themselves, not the geometry. That comparison is what the **average** graphs are for — one bar per run, so the difference between two setups is a number that moved rather than a dozen bars you have to re-read every time. Read the three together: accuracy holding steady while tokens and response time climb is still a result, and the opposite of "the wording made no difference". Check the spread line before believing any of them, though: an average that fell because every model fell is a real effect of the wording, while one that fell because a single model collapsed is a fact about that model. And run it across a fold range instead of one fixed difficulty: where each model's curve leaves the chance line tells you how much folding it can actually hold in its head, which a single accuracy number never will.
