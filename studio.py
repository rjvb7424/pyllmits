"""
studio.py
=========

A local browser "Studio" for the Crafter experiment harness. Instead of running
an experiment immediately, `python studio.py` (or `python main.py --studio`)
opens a UI where you can:

  * browse / load / create config files (in configs/)
  * edit every setting (trials, turns, models, objective, prompt, ...) as a form
  * build the world by painting tiles on a grid (water, trees, stone, table,
    player start, zombies, ...)
  * launch an experiment with Play / Pause / Resume / Stop, and watch it live
  * view the result graphs for any run

It is a small stdlib http.server (no extra dependencies) that serves a
single-page app and a JSON API. The experiment runs in a background thread and
is driven through experiment.RunControl.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import sys
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import ruamel.yaml
from dotenv import set_key, unset_key

import colab_support
from assets import ASSETS_DIR

LOG = logging.getLogger("crafter_experiment.studio")

ROOT = Path.cwd()
CONFIGS_DIR = ROOT / "configs"
RUNS_DIR = ROOT / "runs"
PAPERFOLD_RUNS_DIR = ROOT / "paperfold_runs"
PAPERFOLD_DIRECTIONS = ("north", "south", "east", "west")
ENV_PATH = ROOT / ".env"

# The API keys the welcome screen can collect, in display order. Each one maps
# 1:1 to the env var name a model backend actually reads (see
# models/openai_api.py DEFAULT_KEY_ENV, models/gemini_api.py DEFAULT_KEY_ENV,
# models/huggingface_api.py HF_KEY_ENV) so pasting a key here and running an
# experiment immediately works, with no restart needed.
API_KEY_FIELDS = [
    {"env": "OPENAI_API_KEY", "label": "OpenAI", "placeholder": "sk-...",
     "help_url": "https://platform.openai.com/api-keys",
     "dashboard_url": "https://platform.openai.com/usage"},
    {"env": "GEMINI_API_KEY", "label": "Gemini", "placeholder": "AIza...",
     "help_url": "https://aistudio.google.com/apikey",
     "dashboard_url": "https://aistudio.google.com/app/billing"},
    {"env": "HF_TOKEN", "label": "Hugging Face", "placeholder": "hf_...",
     "help_url": "https://huggingface.co/settings/tokens",
     "dashboard_url": "https://huggingface.co/settings/billing"},
]


# =============================================================================
#  Console capture - mirrors the real terminal (stdout + every log line, from
#  the Studio itself and from experiment runs) into the Run tab's terminal
#  panel. Two independent taps feed the same ring buffer: a logging.Handler
#  on the root logger (import-order-independent - basicConfig may run before
#  or after this module is imported, e.g. via main.py --studio) and a stdout
#  tee (for the handful of plain print() calls, e.g. this file's banner).
# =============================================================================
class ConsoleLog:
    MAX_LINES = 4000

    def __init__(self):
        self._lines = deque(maxlen=self.MAX_LINES)
        self._seq = 0
        self._lock = threading.Lock()

    def append(self, stream: str, text: str):
        if not text:
            return
        with self._lock:
            self._seq += 1
            self._lines.append({"seq": self._seq, "stream": stream, "text": text})

    def since(self, seq: int, limit: int = 500) -> tuple[list[dict], int]:
        with self._lock:
            lines = [l for l in self._lines if l["seq"] > seq]
            next_seq = self._seq
        if len(lines) > limit:
            lines = lines[-limit:]
        return lines, next_seq


CONSOLE = ConsoleLog()


class _TeeStdout:
    """Passes writes through to the real stdout untouched, and also splits
    them on newlines into CONSOLE so the web UI sees exactly what a terminal
    running this process would show."""

    def __init__(self, real):
        self._real = real
        self._buf = ""

    def write(self, s):
        self._real.write(s)
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            CONSOLE.append("stdout", line)
        return len(s)

    def flush(self):
        self._real.flush()

    def isatty(self):
        return getattr(self._real, "isatty", lambda: False)()


class _ConsoleLogHandler(logging.Handler):
    def emit(self, record):
        try:
            CONSOLE.append("stderr" if record.levelno >= logging.WARNING else "log",
                            self.format(record))
        except Exception:
            pass


def _install_console_capture():
    if not isinstance(sys.stdout, _TeeStdout):
        sys.stdout = _TeeStdout(sys.stdout)
    handler = _ConsoleLogHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S"))
    logging.getLogger().addHandler(handler)

# The experiment name IS the config's file name (and its run folder name) -
# so it has to be safe to use as one. No path separators, dots, or spaces.
EXPERIMENT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# Palette: what you can paint on the world grid. Each maps to a world-config
# feature/entity key (or the base terrain / player start). "kind" tells the
# frontend how to serialize it. Colours are for the grid UI.
PALETTE = [
    {"id": "grass",    "label": "Grass",    "kind": "base",   "color": "#4a9d4a"},
    {"id": "water",    "label": "Water",    "kind": "feature", "key": "water",   "color": "#3b74c4"},
    {"id": "trees",    "label": "Tree",     "kind": "feature", "key": "trees",   "color": "#1f6b2e"},
    {"id": "stone",    "label": "Stone",    "kind": "feature", "key": "stone",   "color": "#8a8a8a"},
    {"id": "coal",     "label": "Coal",     "kind": "feature", "key": "coal",    "color": "#2b2b2b"},
    {"id": "iron",     "label": "Iron",     "kind": "feature", "key": "iron",    "color": "#b98a5a"},
    {"id": "sand",     "label": "Sand",     "kind": "feature", "key": "sand",    "color": "#d9c98a"},
    {"id": "lava",     "label": "Lava",     "kind": "feature", "key": "lava",    "color": "#d1502a"},
    {"id": "table",    "label": "Table",    "kind": "feature", "key": "table",   "color": "#7a4a1e"},
    {"id": "furnace",  "label": "Furnace",  "kind": "feature", "key": "furnace", "color": "#555555"},
    {"id": "player",   "label": "Player",   "kind": "player",  "color": "#f2d94e"},
    {"id": "cow",      "label": "Cow",      "kind": "entity",  "key": "cow",     "color": "#e8c0a0"},
    {"id": "zombie",   "label": "Zombie",   "kind": "entity",  "key": "zombie",  "color": "#6db56d"},
    {"id": "skeleton", "label": "Skeleton", "kind": "entity",  "key": "skeleton","color": "#e0e0e0"},
]

OBJECTIVE_TARGETS = [
    "collect_wood", "collect_stone", "collect_coal", "collect_iron",
    "collect_diamond", "place_table", "make_wood_pickaxe", "make_stone_pickaxe",
    "eat_cow", "collect_drink", "defeat_zombie",
]
BACKENDS = ["openai", "huggingface-api", "huggingface", "gemini"]

# Curated model ids offered as a dropdown per backend (you can still type a
# custom id). These are common, currently-hosted options - not exhaustive.
MODEL_PRESETS = {
    "openai": ["gpt-4o-mini", "gpt-4o", "o4-mini", "o3-2025-04-16", "gpt-5.5-2026-04-23",
               "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5-nano-2025-08-07", "gpt-5.4-mini-2026-03-17"],
    "huggingface-api": [
        "Qwen/Qwen3-235B-A22B-Instruct-2507", "openai/gpt-oss-120b",
        "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1", 
        "deepseek-ai/DeepSeek-V4-Pro", "deepseek-ai/DeepSeek-V4-Flash",
        "meta-llama/Llama-3.3-70B-Instruct", "microsoft/phi-4",
    ],
    "huggingface": ["microsoft/phi-4", "Qwen/Qwen2.5-7B-Instruct",
                    "meta-llama/Llama-3.2-3B-Instruct"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", 
               "gemini-3.5-flash", "gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-3.1-flash-lite"],
}


# =============================================================================
#  YAML helpers
# =============================================================================
def _yaml():
    y = ruamel.yaml.YAML()
    y.default_flow_style = False
    y.width = 4096
    return y


def load_yaml(path: Path) -> dict:
    y = ruamel.yaml.YAML(typ="safe", pure=True)
    return y.load(path.read_text()) or {}


def dump_yaml(data: dict) -> str:
    buf = io.StringIO()
    _yaml().dump(data, buf)
    return buf.getvalue()


# =============================================================================
#  Server state (a single active run at a time)
# =============================================================================
class Studio:
    LIVE_PORT = 8000  # the existing live_viewer page; embedded in the Run tab

    def __init__(self):
        self.control = None      # experiment.RunControl while running
        self.thread = None
        self.runner = None       # current ExperimentRunner (holds the live viewer)
        self.config_path = None
        self.live_url = None
        self.run_name = None

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start_run(self, config_path: str) -> dict:
        if self.is_running():
            return {"ok": False, "error": "A run is already in progress."}
        from config import load_config
        from experiment import ExperimentRunner, RunControl

        cfg = load_config(config_path)
        self.control = RunControl()
        self.config_path = config_path
        self.run_name = cfg.experiment.name

        # Build the runner on this thread so its live viewer binds and we can
        # hand the URL to the browser to embed. The trials run in a worker.
        self.runner = ExperimentRunner(
            cfg, live=True, live_port=self.LIVE_PORT, open_browser=False,
            control=self.control,
        )
        self.live_url = self.runner.live_url

        def _worker():
            try:
                self.runner.run()
            except Exception as exc:  # surface errors to the UI
                LOG.exception("run failed")
                self.control.update(state="error", error=str(exc))

        self.thread = threading.Thread(target=_worker, daemon=True)
        self.control.update(state="running")
        self.thread.start()
        return {"ok": True, "live_url": self.live_url}

    def stop_run(self):
        if self.control:
            self.control.stop()

    def status(self) -> dict:
        if self.control is None:
            return {"state": "idle"}
        s = dict(self.control.status)
        s["running"] = self.is_running()
        s["live_url"] = self.live_url
        s["run_name"] = self.run_name
        return s


STUDIO = Studio()


# =============================================================================
#  Server state - paper folding (a second, independent experiment; deliberately
#  its own singleton rather than a field on Studio, so a Crafter run and a
#  paper-folding run can proceed at the same time with no shared lock)
# =============================================================================
class PaperfoldRun:
    def __init__(self):
        self.control = None      # run_control.RunControl while running
        self.thread = None
        self.run_name = None

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    @staticmethod
    def _validate_setup(name: str, models: list, direction_mode: str, direction_labels: dict | None):
        """Shared by start_run and save_setup - both send/validate the exact
        same shape, so a saved setup and a launched run can never disagree
        about what's valid. Returns (specs, direction_mode, direction_labels,
        error_dict_or_None).
        """
        name = (name or "").strip()
        if not EXPERIMENT_NAME_RE.match(name):
            return None, None, None, {"ok": False, "error":
                     "Run name can only contain letters, numbers, underscores and hyphens."}
        if not models:
            return None, None, None, {"ok": False, "error": "Pick at least one model."}

        direction_mode = (direction_mode or "real").strip().lower()
        if direction_mode not in ("real", "fixed", "random"):
            return None, None, None, {"ok": False, "error": "direction_mode must be 'real', 'fixed', or 'random'."}
        if direction_mode == "fixed":
            labels = {d: str((direction_labels or {}).get(d, "")).strip() for d in PAPERFOLD_DIRECTIONS}
            if not all(labels.values()):
                return None, None, None, {"ok": False, "error":
                         "Fill in a placeholder name for all four directions, or switch to Real/Random."}
            lowered = [v.lower() for v in labels.values()]
            if len(set(lowered)) < 4:
                return None, None, None, {"ok": False, "error": "Direction placeholder names must all be different."}
            if any(v in PAPERFOLD_DIRECTIONS for v in lowered):
                return None, None, None, {"ok": False, "error": "Placeholder names can't be the real direction words."}
            direction_labels = labels
        else:
            direction_labels = None

        from config import ModelSpec
        try:
            specs = [ModelSpec.from_dict(dict(m)) for m in models]
        except Exception as exc:
            return None, None, None, {"ok": False, "error": f"Invalid model list: {exc}"}

        return specs, direction_mode, direction_labels, None

    def start_run(self, name: str, num_trials, num_folds, models: list,
                   direction_mode: str = "real", direction_labels: dict | None = None) -> dict:
        if self.is_running():
            return {"ok": False, "error": "A paper-folding run is already in progress."}
        specs, direction_mode, direction_labels, err = self._validate_setup(
            name, models, direction_mode, direction_labels)
        if err:
            return err
        name = (name or "").strip()

        from run_control import RunControl

        self.control = RunControl()
        self.run_name = name

        # Unlike Studio.start_run(), the runner (and its results.json load,
        # which can raise on a num_folds mismatch) is built INSIDE the worker
        # thread, not synchronously here - there's no live-view URL that has
        # to be handed back immediately, so there's no reason to risk a
        # SystemExit-style escape from the request-handling thread. Any
        # failure - including at construction - is caught below and always
        # surfaces through the polled status.
        def _worker():
            try:
                from paperfold.runner import PaperfoldRunner
                runner = PaperfoldRunner(
                    name, num_trials, num_folds, specs, PAPERFOLD_RUNS_DIR,
                    direction_mode=direction_mode, direction_labels=direction_labels,
                    control=self.control,
                )
                runner.run()
            except Exception as exc:
                LOG.exception("paperfold run failed")
                self.control.update(state="error", error=str(exc))

        self.thread = threading.Thread(target=_worker, daemon=True)
        self.control.update(state="running")
        self.thread.start()
        return {"ok": True}

    def save_setup(self, name: str, num_trials, num_folds, models: list,
                    direction_mode: str = "real", direction_labels: dict | None = None) -> dict:
        """Write a run's configuration to results.json without running
        anything - no model is built, no API is called. Lets a setup (name,
        trials, folds, direction mode, model list) be saved and come back
        exactly as left, and - since PaperfoldRunner now records every
        configured model up front rather than lazily as it's reached - means
        the full model list survives even if a later run crashes partway
        through, instead of the unreached models silently vanishing from the
        "resume this run" list.
        """
        specs, direction_mode, direction_labels, err = self._validate_setup(
            name, models, direction_mode, direction_labels)
        if err:
            return err
        name = (name or "").strip()
        if self.is_running() and self.run_name == name:
            return {"ok": False, "error": "That run is currently in progress - stop it first."}

        try:
            from paperfold.runner import PaperfoldRunner
            runner = PaperfoldRunner(
                name, num_trials, num_folds, specs, PAPERFOLD_RUNS_DIR,
                direction_mode=direction_mode, direction_labels=direction_labels,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        runner.save()
        return {"ok": True}

    def stop_run(self):
        if self.control:
            self.control.stop()

    def status(self) -> dict:
        if self.control is None:
            return {"state": "idle"}
        s = dict(self.control.status)
        s["running"] = self.is_running()
        s["run_name"] = self.run_name
        return s


PAPERFOLD = PaperfoldRun()


# =============================================================================
#  HTTP handler
# =============================================================================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    # -- helpers --------------------------------------------------------------
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        if not n:
            return {}
        return json.loads(self.rfile.read(n) or b"{}")

    # -- GET ------------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path
        try:
            if p == "/" or p == "/index.html":
                return self._send(200, INDEX_HTML, "text/html")
            if p == "/api/meta":
                return self._send(200, {
                    "palette": PALETTE, "objectives": OBJECTIVE_TARGETS,
                    "backends": BACKENDS, "model_presets": MODEL_PRESETS,
                })
            if p == "/api/configs":
                return self._send(200, {"configs": self._list_configs()})
            if p == "/api/config":
                path = Path(q["path"][0])
                return self._send(200, {"data": load_yaml(path), "path": str(path)})
            if p == "/api/runs":
                return self._send(200, {"runs": self._list_runs()})
            if p == "/api/plot":
                fp = RUNS_DIR / q["run"][0] / "plots" / q["file"][0]
                if fp.exists():
                    return self._send(200, fp.read_bytes(), "image/png")
                return self._send(404, {"error": "not found"})
            if p == "/api/video":
                fp = RUNS_DIR / q["run"][0] / "videos" / q["file"][0]
                if fp.exists():
                    return self._send(200, fp.read_bytes(), "video/mp4")
                return self._send(404, {"error": "not found"})
            if p == "/api/demo_video":
                fp = ASSETS_DIR / "demo.mp4"
                if fp.exists():
                    return self._send(200, fp.read_bytes(), "video/mp4")
                return self._send(404, {"error": "not found"})
            if p == "/api/logo.png":
                fp = ASSETS_DIR / "logo.png"
                if fp.exists():
                    return self._send(200, fp.read_bytes(), "image/png")
                return self._send(404, {"error": "not found"})
            if p == "/api/run/status":
                return self._send(200, STUDIO.status())
            if p == "/api/run/frame.png":
                png = STUDIO.control.frame_png if STUDIO.control else None
                if png:
                    return self._send(200, png, "image/png")
                return self._send(404, b"", "image/png")
            if p == "/api/console":
                since = int(q.get("since", ["0"])[0])
                lines, next_seq = CONSOLE.since(since)
                return self._send(200, {"lines": lines, "next": next_seq})
            if p == "/api/env/status":
                return self._send(200, {"fields": self._env_status()})
            if p == "/api/paperfold/runs":
                return self._send(200, {"runs": self._list_paperfold_runs()})
            if p == "/api/paperfold/run/status":
                return self._send(200, PAPERFOLD.status())
            if p == "/api/paperfold/plot":
                run_dir = self._paperfold_run_dir(q["run"][0])
                fp = (run_dir / "plots" / q["file"][0]) if run_dir else None
                if fp and fp.exists():
                    return self._send(200, fp.read_bytes(), "image/png")
                return self._send(404, {"error": "not found"})
            return self._send(404, {"error": "unknown route"})
        except Exception as exc:
            LOG.exception("GET %s failed", p)
            return self._send(500, {"error": str(exc)})

    # -- POST -----------------------------------------------------------------
    def do_POST(self):
        p = urlparse(self.path).path
        try:
            if p == "/api/config/save":
                status, result = self._save_config(self._body())
                return self._send(status, result)
            if p == "/api/config/delete":
                b = self._body()
                path = Path(b["path"]).resolve()
                if path.suffix != ".yaml" or path.parent != CONFIGS_DIR.resolve():
                    return self._send(400, {"ok": False, "error": "refusing to delete outside configs/"})
                if not path.exists():
                    return self._send(404, {"ok": False, "error": "not found"})
                deleted_run_dir = self._delete_run_dir_for_config(path)
                path.unlink()
                return self._send(200, {"ok": True, "path": str(path), "deleted_run_dir": deleted_run_dir})
            if p == "/api/config/duplicate":
                b = self._body()
                src = Path(b["path"])
                data = load_yaml(src)
                # give the copy a fresh name so it gets its own run folder
                new_name = (data.get("experiment", {}).get("name", src.stem)) + "_copy"
                data.setdefault("experiment", {})["name"] = new_name
                dst = src.with_name(src.stem + "_copy.yaml")
                n = 2
                while dst.exists():
                    dst = src.with_name(f"{src.stem}_copy{n}.yaml"); n += 1
                dst.write_text(dump_yaml(data))
                return self._send(200, {"ok": True, "path": str(dst)})
            if p == "/api/analyze":
                return self._send(200, self._regen_graphs(self._body()["run"]))
            if p == "/api/run/start":
                return self._send(200, STUDIO.start_run(self._body()["path"]))
            if p == "/api/run/pause":
                if STUDIO.control: STUDIO.control.pause()
                return self._send(200, {"ok": True})
            if p == "/api/run/resume":
                if STUDIO.control: STUDIO.control.resume()
                return self._send(200, {"ok": True})
            if p == "/api/run/stop":
                STUDIO.stop_run()
                return self._send(200, {"ok": True})
            if p == "/api/run/delete":
                status, result = self._delete_run(self._body().get("run", ""))
                return self._send(status, result)
            if p == "/api/run/download_plots":
                status, result = self._download_plots(self._body().get("run", ""))
                return self._send(status, result)
            if p == "/api/env/save":
                return self._send(200, self._save_env(self._body()))
            if p == "/api/env/remove":
                return self._send(200, self._remove_env(self._body()))
            if p == "/api/paperfold/run/start":
                b = self._body()
                return self._send(200, PAPERFOLD.start_run(
                    b.get("name", ""), b.get("num_trials", 30),
                    b.get("num_folds", 3), b.get("models", []),
                    b.get("direction_mode", "real"), b.get("direction_labels")))
            if p == "/api/paperfold/setup/save":
                b = self._body()
                return self._send(200, PAPERFOLD.save_setup(
                    b.get("name", ""), b.get("num_trials", 30),
                    b.get("num_folds", 3), b.get("models", []),
                    b.get("direction_mode", "real"), b.get("direction_labels")))
            if p == "/api/paperfold/run/pause":
                if PAPERFOLD.control: PAPERFOLD.control.pause()
                return self._send(200, {"ok": True})
            if p == "/api/paperfold/run/resume":
                if PAPERFOLD.control: PAPERFOLD.control.resume()
                return self._send(200, {"ok": True})
            if p == "/api/paperfold/run/stop":
                PAPERFOLD.stop_run()
                return self._send(200, {"ok": True})
            if p == "/api/paperfold/run/delete":
                status, result = self._delete_paperfold_run(self._body().get("run", ""))
                return self._send(status, result)
            if p == "/api/paperfold/analyze":
                return self._send(200, self._regen_paperfold_graphs(self._body()["run"]))
            return self._send(404, {"error": "unknown route"})
        except Exception as exc:
            LOG.exception("POST %s failed", p)
            return self._send(500, {"error": str(exc)})

    # -- data helpers ---------------------------------------------------------
    def _regen_graphs(self, run_name):
        """Rebuild all plots for a run from its results.json (no model calls).

        Every plot here is scoped to this one run's results.json, so an
        experiment only ever shows its own models, never another experiment's.
        """
        import json
        import analyze_results as ar
        rp = RUNS_DIR / run_name / "results.json"
        if not rp.exists():
            return {"ok": False, "error": "no results.json for this run"}
        results = json.loads(rp.read_text())
        rows = ar.summarise(results)
        name = ar.get_experiment_name(results, rp)
        plots = RUNS_DIR / run_name / "plots"
        plots.mkdir(parents=True, exist_ok=True)
        ar.plot_success_rate(rows, plots / ar.plot_filename("success_rate", run_name), name)
        ar.plot_think_time(rows, plots / ar.plot_filename("think_time", run_name), name)
        ar.plot_success_matrix(rows, plots / ar.plot_filename("success_matrix", run_name), name)
        ar.plot_turns_to_solve(results, plots / ar.plot_filename("turns_to_solve", run_name), name)
        ar.plot_turns_to_fail(results, plots / ar.plot_filename("turns_to_fail", run_name), name)
        ar.plot_tokens_to_solve(results, plots / ar.plot_filename("tokens_to_solve", run_name), name)
        ar.plot_tokens_to_fail(results, plots / ar.plot_filename("tokens_to_fail", run_name), name)
        # No longer generated, or superseded by the name-scoped filenames above
        # (e.g. a bare "success_rate.png" from before plots were named after
        # their experiment) - remove any stale copies so they don't linger.
        for stale_name in ("param_count_vs_accuracy.png", "accuracy_by_family.png",
                           "success_rate_confidence_intervals.png",
                           "turns_to_success.png", "token_usage.png",
                           *(f"{kind}.png" for kind in ar.PLOT_KINDS)):
            stale = plots / stale_name
            if stale.exists():
                stale.unlink()
        return {"ok": True, "plots": [f.name for f in sorted(plots.glob("*.png"))]}

    def _run_dir_for_config(self, exp: dict) -> Path | None:
        """Where this config's run data (results.json/plots/videos) would live."""
        name = exp.get("name")
        if not name:
            return None
        output_dir = Path(exp.get("output_dir", "runs"))
        if not output_dir.is_absolute():
            output_dir = ROOT / output_dir
        return output_dir / name

    def _delete_run_dir_for_config(self, config_path: Path) -> str | None:
        """Remove a deleted config's run folder (results/plots/videos) so its
        graphs don't linger in the Studio after the config is gone.

        Only ever deletes inside this project's own tree - if a config's
        output_dir was pointed somewhere unexpected, this refuses rather than
        risking an rmtree outside the repo.
        """
        try:
            exp = load_yaml(config_path).get("experiment", {})
        except Exception:
            return None
        run_dir = self._run_dir_for_config(exp)
        if run_dir is None:
            return None
        run_dir = run_dir.resolve()
        if not run_dir.exists() or ROOT.resolve() not in run_dir.parents:
            return None
        shutil.rmtree(run_dir)
        return str(run_dir)

    def _find_config_path(self, name: str) -> Path | None:
        """The existing config file for this experiment name, if any (configs/ only)."""
        candidate = CONFIGS_DIR / f"{name}.yaml"
        return candidate if candidate.exists() else None

    def _rename_run_dir_for_config(self, old_exp: dict, new_exp: dict) -> str | None:
        """Move an existing run folder to match a renamed experiment, so its
        results/videos/plots stay attached instead of being orphaned under the
        old name. Returns an error message if the rename can't happen safely,
        else None.
        """
        old_run_dir = self._run_dir_for_config(old_exp)
        new_run_dir = self._run_dir_for_config(new_exp)
        if old_run_dir is None or not old_run_dir.exists() or old_run_dir == new_run_dir:
            return None
        if new_run_dir is None:
            return None
        if new_run_dir.exists():
            return f"Can't rename: run data already exists at {new_run_dir}."
        new_run_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_run_dir), str(new_run_dir))
        return None

    def _save_config(self, body: dict) -> tuple[int, dict]:
        """Save (or rename) a config.

        The experiment name IS the file name - there's no separate save path
        the user can set independently - so this validates the name and, if
        it changed from what was loaded, renames the .yaml (and its run
        folder, if one exists) to match rather than leaving a stale copy
        behind under the old name.
        """
        data = body.get("data") or {}
        exp = data.get("experiment") or {}
        name = (exp.get("name") or "").strip()
        if not name:
            return 400, {"ok": False, "error": "Experiment name can't be empty."}
        if not EXPERIMENT_NAME_RE.match(name):
            return 400, {"ok": False, "error":
                         "Experiment name can only contain letters, numbers, underscores and hyphens."}

        old_path = Path(body["old_path"]).resolve() if body.get("old_path") else None
        existing = self._find_config_path(name)
        if existing is not None and existing.resolve() != old_path:
            return 400, {"ok": False, "error": f"A config named '{name}' already exists."}

        directory = old_path.parent if old_path is not None else CONFIGS_DIR
        new_path = directory / f"{name}.yaml"

        if old_path is not None and old_path.exists() and old_path.resolve() != new_path.resolve():
            try:
                old_exp = load_yaml(old_path).get("experiment", {})
            except Exception:
                old_exp = {}
            rename_error = self._rename_run_dir_for_config(old_exp, exp)
            if rename_error:
                return 400, {"ok": False, "error": rename_error}
            old_path.unlink()

        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text(dump_yaml(data))
        return 200, {"ok": True, "path": str(new_path)}

    def _trials_done(self, exp: dict) -> int:
        """How many trials of this experiment already have results, per results.json.

        A model's trial count only increments once that trial's result is
        appended (see experiment.py), so a model with fewer recorded trials
        than the others is still mid-run; use the minimum across models as
        the experiment's overall completed-trial count.
        """
        run_dir = self._run_dir_for_config(exp)
        if run_dir is None:
            return 0
        results_path = run_dir / "results.json"
        if not results_path.exists():
            return 0
        try:
            results = json.loads(results_path.read_text())
        except Exception:
            return 0
        models = results.get("models", {})
        if not models:
            return 0
        return min(len(m.get("trials", [])) for m in models.values())

    def _list_configs(self):
        # Only ever configs/*.yaml - the Studio's list must line up 1:1 with
        # that folder's actual contents, never include files from elsewhere
        # (e.g. the project root's default config.yaml used by the CLI).
        out = []
        if CONFIGS_DIR.exists():
            for f in sorted(CONFIGS_DIR.glob("*.yaml")):
                try:
                    data = load_yaml(f)
                    exp = data.get("experiment", {})
                    trials_done = self._trials_done(exp)
                    total_trials = exp.get("num_trials")
                    # If num_trials was lowered in the config after trials were
                    # already recorded (e.g. 8 -> 4), results.json still holds
                    # all 8 - show 8/8, not the nonsensical 8/4.
                    if total_trials is not None and trials_done > total_trials:
                        total_trials = trials_done
                    out.append({
                        "path": str(f),
                        "name": exp.get("name", f.stem),
                        "trials": total_trials,
                        "trials_done": trials_done,
                        "turns": exp.get("max_turns"),
                        "size": data.get("world", {}).get("size"),
                        "objective": data.get("objective", {}).get("target"),
                        "models": [m.get("name") for m in data.get("models", [])],
                    })
                except Exception:
                    out.append({"path": str(f), "name": f.stem, "error": True})
        return out

    def _list_runs(self):
        out = []
        if RUNS_DIR.exists():
            for d in sorted(RUNS_DIR.iterdir()):
                if not (d / "results.json").exists():
                    continue
                plots = d / "plots"
                files = [f.name for f in sorted(plots.glob("*.png"))] if plots.exists() else []
                videos = d / "videos"
                clips = [f.name for f in sorted(videos.glob("*.mp4"))] if videos.exists() else []
                out.append({"name": d.name, "plots": files, "videos": clips})
        return out

    def _run_dir(self, run_name: str) -> Path | None:
        """Resolve run_name to its folder under runs/, refusing anything that
        would escape it (path separators, "..", etc)."""
        if not run_name:
            return None
        run_dir = (RUNS_DIR / run_name).resolve()
        if run_dir.parent != RUNS_DIR.resolve():
            return None
        return run_dir

    def _delete_run(self, run_name: str) -> tuple[int, dict]:
        """Delete a run's whole folder (results.json/plots/videos) directly.

        Configs already cascade-delete their run folder (see
        _delete_run_dir_for_config), but a run can still be orphaned - e.g.
        one deleted before that existed, or whose config was removed outside
        the Studio - and there's otherwise no way to clean it up from the UI.
        """
        run_dir = self._run_dir(run_name)
        if run_dir is None:
            return 400, {"ok": False, "error": "invalid run name"}
        if not run_dir.exists():
            return 404, {"ok": False, "error": "not found"}
        if STUDIO.is_running() and STUDIO.run_name == run_name:
            return 400, {"ok": False, "error": "that experiment is currently running - stop it first"}
        shutil.rmtree(run_dir)
        return 200, {"ok": True, "path": str(run_dir)}

    def _download_plots(self, run_name: str) -> tuple[int, dict]:
        """Copy a run's plot PNGs into a fresh folder under the user's
        Downloads, and report its path back.

        The Studio server and the browser are the same machine for this local
        tool, so "download all" doesn't need to go through the browser's
        download machinery (a zip, or one file-picker permission per click)
        at all - the backend can just place a real folder of PNGs directly
        where a download would have landed.
        """
        run_dir = self._run_dir(run_name)
        if run_dir is None:
            return 400, {"ok": False, "error": "invalid run name"}
        plots = run_dir / "plots"
        files = sorted(plots.glob("*.png")) if plots.exists() else []
        if not files:
            return 404, {"ok": False, "error": "no plots for this run"}
        downloads = Path.home() / "Downloads"
        downloads.mkdir(exist_ok=True)
        dest = downloads / f"{run_name}_graphs"
        n = 2
        while dest.exists():
            dest = downloads / f"{run_name}_graphs_{n}"
            n += 1
        dest.mkdir(parents=True)
        for f in files:
            shutil.copy2(f, dest / f.name)
        return 200, {"ok": True, "path": str(dest), "count": len(files)}

    # -- paper folding ----------------------------------------------------------
    def _paperfold_run_dir(self, run_name: str) -> Path | None:
        """Resolve run_name to its folder under paperfold_runs/, refusing
        anything that would escape it (path separators, "..", etc) - same
        guard as _run_dir(), used here too since /api/paperfold/plot builds a
        filesystem path straight from a query parameter."""
        if not run_name:
            return None
        run_dir = (PAPERFOLD_RUNS_DIR / run_name).resolve()
        if run_dir.parent != PAPERFOLD_RUNS_DIR.resolve():
            return None
        return run_dir

    def _list_paperfold_runs(self):
        out = []
        if PAPERFOLD_RUNS_DIR.exists():
            for d in sorted(PAPERFOLD_RUNS_DIR.iterdir()):
                rp = d / "results.json"
                if not rp.exists():
                    continue
                try:
                    results = json.loads(rp.read_text())
                except Exception:
                    continue
                plots = d / "plots"
                files = [f.name for f in sorted(plots.glob("*.png"))] if plots.exists() else []
                models = results.get("models", {})
                out.append({
                    "name": d.name,
                    "plots": files,
                    "num_trials": results.get("num_trials"),
                    "num_folds": results.get("num_folds"),
                    "direction_mode": results.get("direction_mode", "real"),
                    # Only present (and only meaningful) for direction_mode
                    # "fixed" - "random" mode has no single mapping to report,
                    # a fresh one was drawn every trial.
                    "direction_labels": (results.get("config_fingerprint") or {}).get("direction_labels"),
                    # Only name/backend survive in results.json - per-model
                    # tuning options (max_tokens, temperature, ...) were never
                    # persisted, so a "resume this run" prefill can restore
                    # the model list but not those extra settings.
                    "models": [{"name": n, "backend": r.get("backend")} for n, r in models.items()],
                })
        return out

    def _delete_paperfold_run(self, run_name: str) -> tuple[int, dict]:
        """Delete a paper-folding run's whole folder (results.json/plots)."""
        run_dir = self._paperfold_run_dir(run_name)
        if run_dir is None:
            return 400, {"ok": False, "error": "invalid run name"}
        if not run_dir.exists():
            return 404, {"ok": False, "error": "not found"}
        if PAPERFOLD.is_running() and PAPERFOLD.run_name == run_name:
            return 400, {"ok": False, "error": "that run is currently in progress - stop it first"}
        shutil.rmtree(run_dir)
        return 200, {"ok": True, "path": str(run_dir)}

    def _regen_paperfold_graphs(self, run_name):
        """Rebuild all plots for a paper-folding run from its results.json (no
        model calls). Mirrors _regen_graphs()'s shape for the Crafter side."""
        import paperfold.analyze_results as ar
        run_dir = self._paperfold_run_dir(run_name)
        rp = run_dir / "results.json" if run_dir else None
        if not rp or not rp.exists():
            return {"ok": False, "error": "no results.json for this run"}
        results = json.loads(rp.read_text())
        rows = ar.filter_scored(ar.flatten(results))
        plots = run_dir / "plots"
        plots.mkdir(parents=True, exist_ok=True)
        if not rows:
            return {"ok": True, "plots": [], "warning": "No scored trials yet."}
        for kind, fn in (
            ("letter_distribution", ar.plot_letter_distribution),
            ("accuracy_by_model", ar.plot_accuracy_by_model),
            ("accuracy_vs_cost", ar.plot_accuracy_vs_cost),
            ("elapsed_time_by_model", ar.plot_elapsed_time_by_model),
        ):
            fn(rows, plots / ar.plot_filename(kind, run_name), run_name)
        return {"ok": True, "plots": [f.name for f in sorted(plots.glob("*.png"))]}

    # -- API keys / .env -------------------------------------------------------
    def _env_status(self):
        """Whether each known key is already set, plus a masked hint (last 4
        chars) - never the value itself, so it's safe to send to the browser.
        Checks os.environ first (covers keys set outside .env, e.g. the real
        shell env) and falls back to the .env file on disk.
        """
        from dotenv import dotenv_values
        on_disk = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
        out = []
        for f in API_KEY_FIELDS:
            value = os.environ.get(f["env"]) or on_disk.get(f["env"]) or ""
            out.append({
                "env": f["env"], "label": f["label"], "placeholder": f["placeholder"],
                "help_url": f["help_url"], "dashboard_url": f["dashboard_url"], "set": bool(value),
                "hint": ("••••" + value[-4:]) if len(value) >= 4 else "",
            })
        return out

    def _save_env(self, body: dict) -> dict:
        """Upsert the submitted keys into .env (creating it if needed) and into
        this process's environment, so a run started right after Continue
        immediately sees them - no restart required.

        Blank/whitespace-only values are ignored (leaves any existing key
        alone) rather than clearing it, since the field is left blank in the
        UI precisely when a key is already configured.
        """
        known = {f["env"] for f in API_KEY_FIELDS}
        saved = []
        ENV_PATH.touch(exist_ok=True)
        for key, value in body.items():
            if key not in known:
                continue
            value = (value or "").strip()
            if not value:
                continue
            set_key(str(ENV_PATH), key, value, quote_mode="always")
            os.environ[key] = value
            saved.append(key)
        return {"ok": True, "saved": saved}

    def _remove_env(self, body: dict) -> dict:
        """Delete one key from .env and from this process's environment."""
        key = body.get("env", "")
        known = {f["env"] for f in API_KEY_FIELDS}
        if key not in known:
            return {"ok": False, "error": "unknown key"}
        if ENV_PATH.exists():
            unset_key(str(ENV_PATH), key)
        os.environ.pop(key, None)
        return {"ok": True}


# =============================================================================
#  Entry point
# =============================================================================
def serve(port: int = 8010, open_browser: bool = True, colab: bool | None = None):
    """`colab=None` (the default) auto-detects Google Colab and, when found,
    prints the UI's real Colab proxy URL instead of a local one (127.0.0.1
    isn't reachable from your browser there) and skips the auto-open, since
    opening a new tab isn't reliable from a Colab kernel. Pass True/False to
    force one path regardless of environment.
    """
    _install_console_capture()
    CONFIGS_DIR.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url, is_colab = colab_support.resolve_url(port, colab)
    print("=" * 60)
    print(f"  Crafter Studio: {url}")
    print("=" * 60)
    if open_browser and not is_colab:
        threading.Timer(0.6, colab_support.open_browser_tab, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStudio stopped.")


# The single-page app (HTML/CSS/JS) is defined in studio_ui.py to keep this file
# focused on the server. It's imported lazily so a syntax error there can't stop
# the server from importing.
from studio_ui import INDEX_HTML  # noqa: E402


if __name__ == "__main__":
    import logging as _l
    _l.basicConfig(level=_l.INFO, format="%(asctime)s  %(levelname)s  %(message)s",
                   datefmt="%H:%M:%S")
    serve()
