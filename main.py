"""
main.py - compatibility launcher
================================

The real entry point lives in ``llmits.cli``; this thin wrapper keeps the two
historical ways of starting pyllmits working:

    python main.py            # from a checkout of this repo
    import main; main.main()  # from the installed pip package (Colab/notebooks)

It is shipped in the distribution as a top-level module precisely so that
``import main`` keeps working for existing users. New code should prefer the
``llmits`` command, ``python -m llmits``, or ``from llmits.cli import main``.
"""

try:
    from llmits.cli import main
except ModuleNotFoundError as exc:  # pragma: no cover - checkout convenience
    if exc.name not in ("llmits", "llmits.cli"):
        raise
    # Running from a fresh checkout without `pip install -e .`: put src/ on the
    # path so `python main.py` still works (dependencies are still required).
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from llmits.cli import main

if __name__ == "__main__":
    main()
