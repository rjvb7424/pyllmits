"""The local browser Studio: a stdlib HTTP server (server.py) serving a
single-page app (ui.py) for editing configs, painting worlds, launching
experiments, and browsing results."""

from llmits.studio.server import serve

__all__ = ["serve"]
