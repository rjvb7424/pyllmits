"""pyllmits - Large Language Model Instinct Testing under Survival.

Benchmark LLMs in a hand-built Crafter survival world. The package is
organised by concern:

    llmits.cli         command-line entry point (``llmits`` / ``python -m llmits``)
    llmits.config      YAML config -> typed, validated dataclasses
    llmits.experiment  the trial runner (logging, crash-safe saving, resume)
    llmits.env         the game side: world, observation, prompt, actions, success
    llmits.models      model backends (OpenAI, Gemini, HuggingFace, mock) + registry
    llmits.analysis    results.json -> plots, replay viewer, run videos
    llmits.studio      the local browser Studio (server + single-page UI)
    llmits.paperfold   the independent paper-folding spatial-reasoning benchmark
"""

__version__ = "0.6.0"
