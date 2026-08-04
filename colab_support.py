"""colab_support.py
====================

Best-effort Google Colab support for the two local web servers this project
runs (the Studio UI in studio.py, the live view in live_viewer.py).

Both servers bind to 127.0.0.1 and open a browser tab pointed at it. On Colab
that doesn't work: the kernel runs on a remote VM, so 127.0.0.1 there isn't
reachable from your actual browser, and webbrowser.open() raises
`webbrowser.Error: could not locate runnable browser` in Colab's headless
container. Colab's own `google.colab.output` module solves this by proxying a
kernel port through to a real URL and opening it for you.

No extra dependency is needed - `google.colab` is only importable when
actually running on Colab, so it's imported lazily, inside the Colab branch.
"""

from __future__ import annotations

import sys
import webbrowser


def in_colab() -> bool:
    """True when running inside a Google Colab kernel."""
    return "google.colab" in sys.modules


def open_browser_tab(url: str, port: int, colab: bool | None = None) -> None:
    """Open `url` for the user - via Colab's port proxy if on Colab, otherwise
    the normal local webbrowser.open(). `colab=None` (the default) auto-detects;
    pass True/False to force one path.
    """
    use_colab = in_colab() if colab is None else colab
    if use_colab:
        from google.colab import output  # type: ignore[import-not-found]
        output.serve_kernel_port_as_window(port)
        return
    webbrowser.open(url)
