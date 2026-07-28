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
import re
import shutil
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import ruamel.yaml

LOG = logging.getLogger("crafter_experiment.studio")

ROOT = Path.cwd()
CONFIGS_DIR = ROOT / "configs"
RUNS_DIR = ROOT / "runs"

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
    "openai": ["gpt-4o-mini", "gpt-4o", "o4-mini", "o3-2025-04-16",
               "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
    "huggingface-api": [
        "Qwen/Qwen3-235B-A22B-Instruct-2507", "openai/gpt-oss-120b",
        "deepseek-ai/DeepSeek-V3.2", "deepseek-ai/DeepSeek-R1",
        "meta-llama/Llama-3.3-70B-Instruct", "microsoft/phi-4",
    ],
    "huggingface": ["microsoft/phi-4", "Qwen/Qwen2.5-7B-Instruct",
                    "meta-llama/Llama-3.2-3B-Instruct"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
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
            if p == "/api/run/status":
                return self._send(200, STUDIO.status())
            if p == "/api/run/frame.png":
                png = STUDIO.control.frame_png if STUDIO.control else None
                if png:
                    return self._send(200, png, "image/png")
                return self._send(404, b"", "image/png")
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
            return self._send(404, {"error": "unknown route"})
        except Exception as exc:
            LOG.exception("POST %s failed", p)
            return self._send(500, {"error": str(exc)})

    # -- data helpers ---------------------------------------------------------
    def _regen_graphs(self, run_name):
        """Rebuild all plots for a run from its results.json (no model calls).

        Every plot here - both analyze_results.py's and analyze_scaling.py's -
        is scoped to this one run's results.json, so an experiment only ever
        shows its own models, never another experiment's.
        """
        import json
        import analyze_results as ar
        import analyze_scaling as asc
        rp = RUNS_DIR / run_name / "results.json"
        if not rp.exists():
            return {"ok": False, "error": "no results.json for this run"}
        results = json.loads(rp.read_text())
        rows = ar.summarise(results)
        scaling_rows = asc.collect_model_rows(results)
        name = ar.get_experiment_name(results, rp)
        plots = RUNS_DIR / run_name / "plots"
        plots.mkdir(parents=True, exist_ok=True)
        ar.plot_success_rate(rows, plots / "success_rate.png", name)
        ar.plot_turns_to_success(rows, plots / "turns_to_success.png", name)
        ar.plot_think_time(rows, plots / "think_time.png", name)
        ar.plot_success_matrix(rows, plots / "success_matrix.png", name)
        ar.plot_tokens_vs_turns(results, plots / "token_usage.png", name)
        asc.plot_param_count_vs_accuracy(scaling_rows, plots / "param_count_vs_accuracy.png", name)
        asc.plot_accuracy_by_family(results, plots / "accuracy_by_family.png", name)
        asc.plot_success_rate_confidence_intervals(
            results, plots / "success_rate_confidence_intervals.png", name
        )
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

    def _delete_run(self, run_name: str) -> tuple[int, dict]:
        """Delete a run's whole folder (results.json/plots/videos) directly.

        Configs already cascade-delete their run folder (see
        _delete_run_dir_for_config), but a run can still be orphaned - e.g.
        one deleted before that existed, or whose config was removed outside
        the Studio - and there's otherwise no way to clean it up from the UI.
        """
        if not run_name:
            return 400, {"ok": False, "error": "no run given"}
        run_dir = (RUNS_DIR / run_name).resolve()
        if run_dir.parent != RUNS_DIR.resolve():
            return 400, {"ok": False, "error": "invalid run name"}
        if not run_dir.exists():
            return 404, {"ok": False, "error": "not found"}
        if STUDIO.is_running() and STUDIO.run_name == run_name:
            return 400, {"ok": False, "error": "that experiment is currently running - stop it first"}
        shutil.rmtree(run_dir)
        return 200, {"ok": True, "path": str(run_dir)}


# =============================================================================
#  Entry point
# =============================================================================
def serve(port: int = 8010, open_browser: bool = True):
    CONFIGS_DIR.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print("=" * 60)
    print(f"  Crafter Studio: {url}")
    print("=" * 60)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
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
