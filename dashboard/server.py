#!/usr/bin/env python3
"""Local presentation dashboard. Python standard library only.

python3 dashboard/server.py                 # isolated real-engine demo
python3 dashboard/server.py --project PATH  # also observe another checkout
python3 dashboard/server.py --enable-live-controls  # opt-in project mutations
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import demo_data as D

SOURCE_FILES = {
    "state": "scripts/state.py", "scheduler": "scripts/srs.py", "store": "scripts/learnlib.py",
    "hook": "scripts/hook_session_start.py", "exercise": "scripts/exercise.py",
    "teach": ".claude/skills/teach/SKILL.md", "review": ".claude/skills/review/SKILL.md",
    "system": "docs/SYSTEM.md", "reader": ".claude/agents/document-reader.md",
    "researcher": ".claude/agents/researcher.md", "logging": "scripts/session_log.py",
}
class DashboardError(Exception):
    pass


def atomic_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def differences(before, after):
    """A display diff, not duplicated progression or scheduling logic."""
    out = []
    def emit(path, a, b):
        if a != b:
            out.append({"path": path, "before": a, "after": b})
    emit("state.rev", before.get("rev", 0), after.get("rev", 0))
    emit("lesson.status", (before.get("topic") or {}).get("status"), (after.get("topic") or {}).get("status"))
    emit("pending.stage", (before.get("pending") or {}).get("stage"), (after.get("pending") or {}).get("stage"))
    emit("pending.id", (before.get("pending") or {}).get("id"), (after.get("pending") or {}).get("id"))
    bn = {n["id"]: n for n in (before.get("topic") or {}).get("plan", {}).get("nodes", [])}
    for n in (after.get("topic") or {}).get("plan", {}).get("nodes", []):
        for field in ("coverage", "readiness", "retention"):
            emit(f"{n['id']}.{field}", bn.get(n["id"], {}).get(field), n.get(field))
    bc = {c["id"]: c for c in before.get("cards", [])}
    for c in after.get("cards", []):
        for field in ("interval", "due", "reps", "lapses"):
            emit(f"card[{c.get('node') or c['id']}].{field}", bc.get(c["id"], {}).get(field), c.get(field))
    emit("eligible nodes", before.get("eligibility", {}).get("eligible", []), after.get("eligibility", {}).get("eligible", []))
    emit("demo date", before.get("date"), after.get("date"))
    return out


class Engine:
    def __init__(self, project: Path, data: Path, live_controls=False):
        self.project = project.resolve()
        self.data = data.resolve()
        if not (self.project / "scripts/state.py").is_file() or not (self.project / "scripts/srs.py").is_file():
            raise DashboardError(f"Not a LearningforLunch project: {self.project}")
        if self.data == self.project or self.data == Path(self.data.anchor):
            raise DashboardError("Choose a separate dashboard data directory, not the project root.")
        self.data.mkdir(parents=True, exist_ok=True)
        self.demo = self.data / "demo"
        self.meta_path = self.data / "presentation.json"
        self.audit_path = self.data / "commands.jsonl"
        self.lock = threading.RLock()
        self.live_controls = live_controls
        self.token = secrets.token_urlsafe(32)
        self.events = []
        if self.audit_path.exists():
            try:
                self.events = [json.loads(line) for line in self.audit_path.read_text("utf-8").splitlines()[-160:]]
            except (ValueError, OSError):
                self.events = []
        self.meta = {}
        if self.meta_path.exists() and (self.demo / ".dashboard-demo").exists():
            self.meta = json.loads(self.meta_path.read_text("utf-8"))
        else:
            self.reset()

    def save_meta(self):
        atomic_json(self.meta_path, self.meta)

    def env(self, mode):
        root = self.demo if mode == "demo" else self.project
        env = os.environ.copy()
        env.update({"CLAUDE_PROJECT_DIR": str(root), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"})
        env.pop("LEARN_NOW", None)
        if mode == "demo":
            env["LEARN_NOW"] = self.meta["clock"]
        return root, env

    def invoke(self, mode, request):
        root, env = self.env(mode)
        try:
            process = subprocess.run([sys.executable, "-S", str(HERE / "bridge.py")],
                                     input=json.dumps(request, ensure_ascii=False),
                                     text=True, encoding="utf-8", errors="replace", capture_output=True,
                                     cwd=root, env=env, timeout=25)
        except subprocess.TimeoutExpired as exc:
            raise DashboardError("The engine command timed out. Refresh to inspect its saved state before retrying.") from exc
        if process.returncode:
            raise DashboardError((process.stderr.strip() or process.stdout.strip() or "Engine command failed")[-7000:])
        return process.stdout.strip()

    def read(self, mode, topic=None):
        return json.loads(self.invoke(mode, {"kind": "snapshot", "topic": topic}))

    def event(self, event):
        event["id"] = secrets.token_hex(5)
        event["at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        self.events.append(event)
        self.events = self.events[-160:]
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def run(self, mode, module, args=None, stdin=None, *, expected_rev=None):
        before = self.read(mode)
        t = time.monotonic()
        command = f"python scripts/{'hook_session_start' if module == 'hook' else module}.py " + " ".join(str(a) for a in (args or []))
        event = {"mode": mode, "command": command.strip(), "input": stdin, "changes": [], "ok": False}
        try:
            output = self.invoke(mode, {"kind": "command", "module": module, "args": args or [],
                                        "stdin": stdin, "expected_rev": expected_rev})
            after = self.read(mode)
            event.update({"output": output, "ok": True, "changes": differences(before, after),
                          "engine_date": after["date"], "rev": after["rev"]})
        except DashboardError as exc:
            event["output"] = str(exc)
            raise
        finally:
            event["duration_ms"] = round((time.monotonic() - t) * 1000)
            self.event(event)
        return output

    def reset(self):
        with self.lock:
            if self.demo.exists():
                if not (self.demo / ".dashboard-demo").is_file():
                    raise DashboardError(f"Refusing to remove an unmarked directory: {self.demo}")
                shutil.rmtree(self.demo)
            self.demo.mkdir(parents=True)
            (self.demo / ".dashboard-demo").write_text("Disposable dashboard workspace. No learner records copied.\n", "utf-8")
            shutil.copytree(self.project / "scripts", self.demo / "scripts",
                            ignore=shutil.ignore_patterns("__pycache__", "tests", "*.pyc"))
            atomic_json(self.demo / "learn.config.json", {
                "notesDir": "notes", "vizDir": "notes/viz", "reviewsDir": "notes/reviews",
                "exercisesDir": "exercises", "resourcesDir": "resources", "stateDir": "state",
                "timezone": "Europe/Oslo", "reviewMinutes": 10})
            (self.demo / "LEARNER.md").write_text("# Presentation learner\nFictional learner; prepared demo responses. No personal profile copied.\n", "utf-8")
            try:
                from zoneinfo import ZoneInfo
                current = dt.datetime.now(ZoneInfo("Europe/Oslo"))
            except Exception:
                current = dt.datetime.now().astimezone()
            self.meta = {"clock": current.replace(hour=12, minute=0, second=0, microsecond=0).isoformat(),
                         "tour_index": 0, "tour_custom": False, "last_beat": None,
                         "source_project": str(self.project)}
            self.events = [e for e in self.events if e.get("mode") != "demo"]
            self.audit_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in self.events), "utf-8")
            self.save_meta()
            self.run("demo", "state", ["start", D.TITLE, "--slug", D.SLUG, "--goal", D.GOAL])
            self.run("demo", "state", ["plan-set"], D.PLAN)
            self.run("demo", "state", ["prep-topic"], D.TOPIC_PREP)
            for nid, material in D.PREP.items():
                self.run("demo", "state", ["prep-node", nid], material)
            self.run("demo", "state", ["plan-approve"])

    def snapshot(self, mode, topic=None):
        with self.lock:
            s = self.read(mode, topic)
            s.update({"mode": mode, "can_write": mode == "demo" or self.live_controls,
                      "project_root": str(self.project), "events": [e for e in self.events if e.get("mode") == mode][-45:],
                      "tour": {"steps": D.TOUR, **self.meta} if mode == "demo" else None,
                      "source_files": SOURCE_FILES, "live_controls": self.live_controls})
            return s

    def ask(self, node, kind="initial", exit_id=None):
        args = ["ask", node, "--kind", kind]
        if exit_id:
            args += ["--exit", exit_id]
        self.run("demo", "state", args)

    def answer(self, response):
        self.run("demo", "state", ["answer", response])

    def assess(self, result="pass", **extra):
        snapshot = self.read("demo")
        required = (snapshot["pending"] or {}).get("key", {}).get("required", [])
        value = {"op": "dashboard-" + secrets.token_hex(8), "result": result, "quality": 4 if result == "pass" else 1,
                 "required_met": required if result == "pass" else [],
                 "required_missed": [] if result == "pass" else required,
                 "note": "Scripted presentation assessment; not an AI-generated grade."}
        value.update(extra)
        self.run("demo", "state", ["record"], value)

    def complete_node(self, node):
        self.ask(node)
        self.answer(self.read("demo")["pending"]["key"]["answer"])
        self.assess()

    def advance_clock(self, days):
        before = self.read("demo")
        clock = dt.datetime.fromisoformat(self.meta["clock"]) + dt.timedelta(days=days)
        self.meta["clock"] = clock.isoformat()
        self.save_meta()
        after = self.read("demo")
        self.event({"mode": "demo", "command": f"Dashboard: set LEARN_NOW to {self.meta['clock']}",
                    "output": "Only the demo subprocess clock changes. The operating-system clock and live project are unchanged.",
                    "input": None, "ok": True, "changes": differences(before, after), "engine_date": after["date"]})

    def grade_card(self, node, quality):
        cards = self.read("demo")["cards"]
        card = next(c for c in cards if c.get("node") == node)
        self.run("demo", "srs", ["grade", card["id"], str(quality), "--kind", "review", "--note", "Scripted presentation review", "--op", secrets.token_hex(10)])

    def next_beat(self):
        i = self.meta["tour_index"]
        if self.meta.get("tour_custom"):
            raise DashboardError("Manual controls changed the lesson. Reset the demo to restart the guided sequence.")
        if i >= len(D.TOUR):
            raise DashboardError("The guided demonstration is complete. Explore the evidence or reset to replay.")
        if i == 0:
            self.ask("parts")
        elif i == 1:
            self.answer(D.PREP["parts"]["checks"][0]["variants"][0]["answer"])
        elif i == 2:
            self.assess()
        elif i == 3:
            self.ask("equivalent")
        elif i == 4:
            self.answer("Two quarters is bigger because two is larger than one.")
            self.assess("fail", misconception="bigger-numbers")
        elif i == 5:
            self.complete_node("numberline")
        elif i == 6:
            self.ask("equivalent", "repair")
            self.run("demo", "state", ["hint", "--level", "nudge"])
        elif i == 7:
            self.run("demo", "hook", [], {"source": "startup"})
        elif i == 8:
            self.answer(self.read("demo")["pending"]["key"]["answer"])
            self.assess()
        elif i == 9:
            self.complete_node("add")
        elif i == 10:
            self.ask("add", "exit", "transfer")
            self.answer(self.read("demo")["pending"]["key"]["answer"])
            self.assess()
            self.run("demo", "state", ["finish", "--summary", "Presentation sample completed with an independent exit check; retention is assessed separately."])
        elif i == 11:
            self.advance_clock(1)
            self.grade_card("parts", 4)
        elif i == 12:
            self.advance_clock(6)
            self.grade_card("parts", 4)
        elif i == 13:
            self.grade_card("equivalent", 1)
        self.meta["last_beat"] = i
        self.meta["tour_index"] = i + 1
        self.save_meta()

    def action(self, mode, data):
        with self.lock:
            name = data.get("action")
            if mode not in ("demo", "live"):
                raise DashboardError("Unknown mode")
            if name in ("reset", "tour-next", "advance-clock", "recover") and mode != "demo":
                raise DashboardError("Reset, recovery demonstration and simulated time are available only in the isolated demo.")
            if mode == "live" and not self.live_controls:
                raise DashboardError("Live project is read-only. Use --enable-live-controls only when you intend to write to your real lesson.")
            if name == "reset":
                self.reset()
            elif name == "tour-next":
                try:
                    self.next_beat()
                except DashboardError:
                    self.meta["tour_custom"] = True
                    self.save_meta()
                    raise
            else:
                s = self.read(mode)
                expected = data.get("expected_rev")
                if expected is None or int(expected) != s["rev"]:
                    raise DashboardError("The lesson changed. Refresh before using this control.")
                if name in ("ask", "answer", "hint", "record") and not s["active_topic"]:
                    raise DashboardError("There is no active topic. Start or resume it in Claude Code, or reset the demo.")
                if mode == "demo":
                    self.meta["tour_custom"] = True
                    self.save_meta()
                if name == "ask":
                    node = str(data.get("node", ""))
                    nodes = {n["id"] for n in (s.get("topic") or {}).get("plan", {}).get("nodes", [])}
                    if node not in nodes:
                        raise DashboardError("Select an existing lesson node.")
                    if node in {b["id"] for b in s["eligibility"]["blocked"]}:
                        raise DashboardError("This node has an unmet prerequisite. Select an eligible node or repair its prerequisite first.")
                    kind = data.get("kind", "initial")
                    if kind not in ("initial", "practice", "repair", "review"):
                        raise DashboardError("Unsupported attempt kind")
                    self.run(mode, "state", ["ask", node, "--kind", kind], expected_rev=expected)
                elif name == "answer":
                    response = str(data.get("response", "")).strip()
                    if not response or len(response) > 2000:
                        raise DashboardError("Enter an answer of 1 to 2,000 characters.")
                    self.run(mode, "state", ["answer", response], expected_rev=expected)
                elif name == "hint":
                    self.run(mode, "state", ["hint"], expected_rev=expected)
                elif name == "record":
                    p = s.get("pending") or {}
                    if p.get("stage") != "recorded":
                        raise DashboardError("Save the learner's answer before supplying an assessment.")
                    result = data.get("result")
                    if result not in ("pass", "partial", "fail", "unknown"):
                        raise DashboardError("Choose a supported assessment.")
                    quality = int(data.get("quality", 4))
                    if not 0 <= quality <= 5:
                        raise DashboardError("Quality must be between 0 and 5.")
                    required = p.get("key", {}).get("required", [])
                    met = data.get("required_met", [])
                    if not isinstance(met, list) or any(x not in required for x in met):
                        raise DashboardError("Required points must match the prepared rubric.")
                    assessment = {"op": "dashboard-" + secrets.token_hex(12), "result": result, "quality": quality,
                                  "required_met": met, "required_missed": [x for x in required if x not in met],
                                  "note": "Presenter-supplied assessment from the local dashboard; no AI grading was run."}
                    self.run(mode, "state", ["record"], assessment, expected_rev=expected)
                elif name == "grade-review":
                    cid = str(data.get("card", ""))
                    if cid not in {c["id"] for c in s["cards"]}:
                        raise DashboardError("Unknown card")
                    quality = int(data.get("quality", 4))
                    if not 0 <= quality <= 5:
                        raise DashboardError("Quality must be between 0 and 5.")
                    kind = data.get("kind", "review")
                    if kind not in ("review", "practice", "repair"):
                        raise DashboardError("Unsupported review kind")
                    args = ["grade", cid, str(quality), "--kind", kind, "--note", "Presenter-supplied review", "--op", secrets.token_hex(12)]
                    if data.get("assisted"):
                        args.append("--assisted")
                    self.run(mode, "srs", args, expected_rev=expected)
                elif name == "advance-clock":
                    days = int(data.get("days", 1))
                    if not 1 <= days <= 365:
                        raise DashboardError("Advance the demo clock by 1 to 365 days.")
                    self.advance_clock(days)
                elif name == "recover":
                    self.run("demo", "hook", [], {"source": "startup"})
                else:
                    raise DashboardError("Unknown action")
            return self.snapshot(mode)


class Handler(BaseHTTPRequestHandler):
    server_version = "LearningObservatory/1.0"
    @property
    def engine(self):
        return self.server.engine

    def log_message(self, fmt, *args):
        if not self.path.startswith("/api/snapshot"):
            print(f"[{self.log_date_time_string()}] {fmt % args}")

    def trusted_host(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def send_data(self, status, body, content_type="application/json; charset=utf-8", headers=None):
        if not isinstance(body, bytes):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def json(self, status, obj):
        self.send_data(status, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        if not self.trusted_host():
            return self.json(403, {"error": "Untrusted Host header"})
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        mode = q.get("mode", ["demo"])[0]
        if mode not in ("demo", "live"):
            return self.json(400, {"error": "Unknown mode"})
        try:
            if url.path == "/api/bootstrap":
                self.json(200, {"token": self.engine.token, "project": str(self.engine.project),
                                "live_controls": self.engine.live_controls, "version": "1.0"})
            elif url.path == "/api/snapshot":
                self.json(200, self.engine.snapshot(mode, q.get("topic", [None])[0]))
            elif url.path == "/api/source":
                key = q.get("file", ["state"])[0]
                if key not in SOURCE_FILES:
                    raise DashboardError("Source file is not on the public source allowlist.")
                rel = SOURCE_FILES[key]
                root = self.engine.demo if mode == "demo" and rel.startswith("scripts/") else self.engine.project
                target = (root / rel).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    raise DashboardError("Source file is unavailable in this project.")
                text = target.read_text("utf-8")
                self.json(200, {"path": rel, "text": text, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
            elif url.path == "/api/export":
                snapshot = self.engine.snapshot(mode)
                self.send_data(200, json.dumps(snapshot, ensure_ascii=False, indent=2),
                               headers={"Content-Disposition": f'attachment; filename="learning-observatory-{mode}.json"'})
            elif url.path in ("/", "/index.html", "/app.js", "/style.css"):
                file = HERE / "static" / ("index.html" if url.path == "/" else url.path.lstrip("/"))
                mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[file.suffix]
                self.send_data(200, file.read_bytes(), mime + "; charset=utf-8")
            elif url.path == "/favicon.ico":
                self.send_data(204, b"", "image/x-icon")
            else:
                self.json(404, {"error": "Not found"})
        except (DashboardError, ValueError, OSError) as exc:
            self.json(409, {"error": str(exc)})

    def do_POST(self):
        if not self.trusted_host():
            return self.json(403, {"error": "Untrusted Host header"})
        origin = self.headers.get("Origin")
        allowed = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if origin and origin not in allowed:
            return self.json(403, {"error": "Cross-origin requests are not permitted"})
        if not secrets.compare_digest(self.headers.get("X-Dashboard-Token", ""), self.engine.token):
            return self.json(403, {"error": "Missing or invalid request token. Reload the dashboard."})
        if self.path != "/api/action":
            return self.json(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0 or length > 131072:
                return self.json(413, {"error": "Request is empty or too large"})
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self.json(415, {"error": "Expected application/json"})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise DashboardError("Expected an object")
            self.json(200, self.engine.action(data.get("mode", "demo"), data))
        except (DashboardError, ValueError, TypeError, KeyError, OSError) as exc:
            self.json(409, {"error": str(exc)})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", type=Path, default=HERE.parent, help="LearningforLunch checkout to observe and use as the source of engine scripts")
    parser.add_argument("--data-dir", type=Path, help="Isolated dashboard data location (default: PROJECT/.dashboard-local)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--enable-live-controls", action="store_true", help="Allow explicit browser ask/answer/hint/record/review writes to the real project")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required by the existing project.")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
        engine = Engine(args.project, args.data_dir or args.project / ".dashboard-local", args.enable_live_controls)
        server.engine = engine
    except (DashboardError, OSError, ValueError) as exc:
        print(f"Could not start: {exc}\nFor an occupied port, try --port 8766.", file=sys.stderr)
        return 1
    url = f"http://localhost:{server.server_port}"
    print(f"\nLearning for Lunch — Learning Observatory\n{url}\nProject: {engine.project}\nDemo:    {engine.demo}", flush=True)
    print("Live controls: " + ("ENABLED — actions can change your real learning records." if args.enable_live_controls else "read-only (default)."), flush=True)
    print("The demo runs your Python engine. No model/API is invoked. Ctrl+C stops the server.\n", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nDashboard stopped. Saved demo state is preserved.")
    finally:
        server.server_close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
