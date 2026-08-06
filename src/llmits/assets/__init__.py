"""assets - static files bundled with the package (Studio logo, welcome-screen
demo clip), so they're available wherever pyllmits is installed - not just
when running from a checkout of this repo (see studio.py's ASSETS_DIR use).
"""

from pathlib import Path

ASSETS_DIR = Path(__file__).parent
