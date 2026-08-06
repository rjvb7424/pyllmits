"""colab_support.py
====================

Best-effort Google Colab support for the two local web servers this project
runs (the Studio UI in studio.py, the live view in live_viewer.py).

Both servers bind to 127.0.0.1. On Colab that's not reachable from your
actual browser (the kernel runs on a remote VM) - Colab proxies a kernel port
through to a real URL instead. We compute that URL directly via
`google.colab.kernel.proxyPort` rather than using
`google.colab.output.serve_kernel_port_as_window`: that helper tries to
`window.open()` a popup, which modern browsers block by default (Colab's own
runtime prints a deprecation warning about this), and its printed fallback
link is bare `localhost`, which isn't reachable either - so you end up with
two links on screen and neither works. Printing the one real proxy URL and
leaving it to be clicked sidesteps both problems.

No extra dependency is needed - `google.colab` is only importable when
actually running on Colab, so it's imported lazily, inside the Colab branch.
"""

from __future__ import annotations

import sys
import webbrowser


def in_colab() -> bool:
    """True when running inside a Google Colab kernel."""
    return "google.colab" in sys.modules


def running_under_kernel() -> bool:
    """True when running inside a Jupyter/Colab notebook kernel (as opposed to
    a plain `python script.py` shell invocation).

    Matters for argparse: a notebook kernel is launched as e.g.
    `colab_kernel_launcher.py -f /path/to/connection-file.json`, so a bare
    `import main; main.main()` inside a notebook cell sees that `-f ...` in
    sys.argv - not anything the user typed - and argparse rejects it as an
    unrecognized argument.
    """
    return "ipykernel" in sys.modules


def resolve_url(port: int, colab: bool | None = None) -> tuple[str, bool]:
    """The URL to show the user for `port`: Colab's real proxy URL when
    running on Colab, otherwise plain localhost. `colab=None` auto-detects;
    pass True/False to force one path. Returns (url, is_colab).
    """
    use_colab = in_colab() if colab is None else colab
    if use_colab:
        from google.colab.output import eval_js  # type: ignore[import-not-found]
        url = eval_js(f"google.colab.kernel.proxyPort({port})")
        return url, True
    return f"http://127.0.0.1:{port}", False


def open_browser_tab(url: str) -> None:
    """Open `url` in a local browser tab. Only call this off-Colab - see the
    module docstring for why Colab gets a printed link instead of an attempted
    popup.
    """
    webbrowser.open(url)
