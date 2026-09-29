#!/usr/bin/env python3
"""Shared helpers for the learning system scripts.

Standard library only, so the hooks work on any machine with python3.
Paths come from learn.config.json at the repo root (or $CLAUDE_PROJECT_DIR).

What lives here:
  config / paths / clock      config(), dir_path(), now(), today() (LEARN_NOW overrides the clock)
  json persistence            read_json() (missing -> default, corrupt -> CorruptStateError),
                              write_json() (atomic), backup_file() (byte-for-byte, bounded)
  locking + journal           Store: lock, load state+deck, migrate, validate, commit both files
                              through a recoverable journal; op ids make replays no-ops
  schemas + migration         migrate_state(), migrate_deck(), validate_plan(), validate_node_prep()
  lesson-session detection    lesson_session() for the hooks
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import tempfile
import time

ROOT = pathlib.Path(
    os.environ.get("CLAUDE_PROJECT_DIR") or pathlib.Path(__file__).resolve().parent.parent
).resolve()
CONFIG_PATH = ROOT / "learn.config.json"

DEFAULTS = {
    "notesDir": "notes",
    "vizDir": "notes/viz",
    "reviewsDir": "notes/reviews",
    "exercisesDir": "exercises",
    "stateDir": "state",
    "resourcesDir": "resources",
    "timezone": "",
    "checkpointMinutes": 12,
    "reviewMinutes": 10,
    "reviewCostMinutes": {"short": 2.5, "mcq": 1.0, "code": 12.0},
    "lockStaleSeconds": 60,
    "backupsKeep": 10,
}

STATE_VERSION = 2
DECK_VERSION = 2
MAX_APPLIED_OPS = 500

COVERAGE = ("pending", "covered")
READINESS = ("unknown", "needs_repair", "provisional", "ready")
RETENTION = ("unassessed", "demonstrated", "needs_review")
LEGACY_STATUS = ("pending", "done", "shaky")
TOPIC_STATUS = ("probing", "planning", "teaching", "paused", "stopped", "finished")
ATTEMPT_KINDS = ("initial", "practice", "review", "repair", "exit")
ASSISTANCE = ("none", "clarify", "nudge", "substep", "worked", "corrected")
INDEPENDENT_ASSISTANCE = ("none", "clarify")
RESULTS = ("pass", "partial", "fail", "unknown")
CHECK_TYPES = ("short", "mcq", "code")
CLAIM_KINDS = ("definition", "assumption", "guarantee", "simplification")
SOURCE_ROLES = ("primary", "supplementary")

_config_cache: dict | None = None


class LearnError(Exception):
    """A user-facing error: the CLI prints it and exits 1."""


class CorruptStateError(LearnError):
    """An existing file could not be parsed. Mutations are blocked; the file is untouched."""


class ConflictError(LearnError):
    """Someone else wrote the file between our read and our write."""


class LockError(LearnError):
    """Could not acquire the state lock in time."""


class ValidationError(LearnError):
    """A plan, card, prep file or update did not pass its schema check."""


# --- config and paths -----------------------------------------------------------

def config() -> dict:
    """Merged configuration (defaults + learn.config.json)."""
    global _config_cache
    if _config_cache is None:
        data = json.loads(json.dumps(DEFAULTS))
        if CONFIG_PATH.exists():
            try:
                loaded = json.loads(CONFIG_PATH.read_text("utf-8"))
                for k, v in loaded.items():
                    if k.startswith("_"):
                        continue
                    if isinstance(v, dict) and isinstance(data.get(k), dict):
                        data[k].update(v)
                    else:
                        data[k] = v
            except Exception as exc:  # noqa: BLE001
                print(f"warning: could not parse {CONFIG_PATH}: {exc}", file=sys.stderr)
        _config_cache = data
    return _config_cache


def resolve(p: str | os.PathLike) -> pathlib.Path:
    """Expand ~ and $VARS; make relative paths relative to the repo root."""
    text = os.path.expandvars(os.path.expanduser(str(p)))
    path = pathlib.Path(text)
    return path if path.is_absolute() else (ROOT / path)


def dir_path(key: str, create: bool = False) -> pathlib.Path:
    path = resolve(config()[key])
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def prep_dir(slug: str, create: bool = False) -> pathlib.Path:
    path = dir_path("stateDir") / "prep" / slug
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def source_digest_path(slug: str, source_id: str) -> pathlib.Path:
    return prep_dir(slug) / "sources" / f"{source_id}.json"


def file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


_PDF_PAGE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")


def pdf_page_count(path: pathlib.Path) -> int | None:
    """Best-effort page count without a PDF library (uncompressed page objects only)."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(b"%PDF"):
        return None
    n = len(_PDF_PAGE.findall(data))
    return n or None


def split_source_ref(ref: str) -> tuple[str, str]:
    """'notes:p12-14' -> ('notes', 'p12-14'); a plain id has no locator."""
    sid, _, loc = str(ref).partition(":")
    return sid, loc


def backups_dir(create: bool = False) -> pathlib.Path:
    path = dir_path("stateDir") / "backups"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


# --- clock ----------------------------------------------------------------------

def tz():
    name = config().get("timezone")
    if name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:  # noqa: BLE001
            pass
    return _dt.datetime.now().astimezone().tzinfo


def now() -> _dt.datetime:
    """Current time in the configured zone. LEARN_NOW=<iso datetime> overrides it (tests)."""
    override = os.environ.get("LEARN_NOW")
    if override:
        parsed = parse_ts(override)
        if parsed is None:
            raise LearnError(f"LEARN_NOW is not an ISO datetime: {override!r}")
        return parsed
    return _dt.datetime.now(tz())


def today() -> str:
    return now().date().isoformat()


def ts() -> str:
    """ISO timestamp with offset, second precision."""
    return now().replace(microsecond=0).isoformat()


def parse_ts(value: str | None) -> _dt.datetime | None:
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz())
    return parsed.astimezone(tz())


def fmt_local(value: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    parsed = parse_ts(value)
    return parsed.strftime(fmt) if parsed else (value or "")


def date_add(date_iso: str, days: int) -> str:
    return (_dt.date.fromisoformat(date_iso) + _dt.timedelta(days=days)).isoformat()


def days_between(a_iso: str, b_iso: str) -> int:
    return (_dt.date.fromisoformat(b_iso) - _dt.date.fromisoformat(a_iso)).days


# --- json files -------------------------------------------------------------------

def read_json(path, default):
    """Missing file -> default. Unreadable or corrupt file -> CorruptStateError.

    The two cases used to be conflated; a corrupt file must never be silently
    replaced by a fresh default, because the next write would destroy it.
    """
    path = pathlib.Path(path)
    try:
        raw = path.read_text("utf-8")
    except FileNotFoundError:
        return default
    except OSError as exc:
        raise CorruptStateError(f"{path} is unreadable: {exc}. Fix permissions, or restore with: python3 scripts/state.py restore --list") from exc
    try:
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise CorruptStateError(
            f"{path} is not valid JSON ({exc}). The file is left untouched. "
            f"Inspect it, or restore a backup: python3 scripts/state.py restore --list"
        ) from exc


def read_json_lenient(path, default):
    """For hooks and read-only views: never raises, logs instead."""
    try:
        return read_json(path, default)
    except LearnError as exc:
        hook_log(f"read_json_lenient: {exc}")
        return default


def write_json(path, data) -> None:
    """Atomic write so a crash mid-write never corrupts the file."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_text(path, text: str) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(text)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "topic"


def rel(path) -> str:
    try:
        return str(pathlib.Path(path).resolve().relative_to(ROOT))
    except Exception:  # noqa: BLE001
        return str(path)


def new_id(prefix: str, existing=()) -> str:
    import random
    import string

    existing = set(existing)
    while True:
        cand = prefix + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        if cand not in existing:
            return cand


# --- backups ------------------------------------------------------------------------

def backup_file(path, label: str = "") -> pathlib.Path | None:
    """Copy `path` byte-for-byte into stateDir/backups, keeping the newest N per file."""
    path = pathlib.Path(path)
    if not path.exists():
        return None
    folder = backups_dir(create=True)
    stamp = now().strftime("%Y%m%d-%H%M%S")
    suffix = f".{label}" if label else ""
    target = folder / f"{path.name}.{stamp}{suffix}.bak"
    n = 1
    while target.exists():
        n += 1
        target = folder / f"{path.name}.{stamp}{suffix}-{n}.bak"
    shutil.copy2(path, target)
    keep = int(config().get("backupsKeep", 10))
    siblings = sorted(folder.glob(f"{path.name}.*.bak"), key=lambda p: p.stat().st_mtime)
    for old in siblings[:-keep] if keep > 0 else []:
        try:
            old.unlink()
        except OSError:
            pass
    return target


# --- lock ---------------------------------------------------------------------------

class Lock:
    """A directory lock (mkdir is atomic on every filesystem we care about).

    A hook or command holds it from read to write so two writers cannot silently
    overwrite each other. A lock older than lockStaleSeconds is treated as
    abandoned (crashed process) and broken, with a diagnostic in hooks.log.
    """

    def __init__(self, name: str = "state", timeout: float = 5.0):
        self.path = dir_path("stateDir", create=True) / f".{name}.lock"
        self.timeout = timeout
        self.held = False

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        stale = float(config().get("lockStaleSeconds", 60))
        while True:
            try:
                os.mkdir(self.path)
                (self.path / "owner").write_text(f"{os.getpid()} {time.time()}\n", "utf-8")
                self.held = True
                return self
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > stale:
                    hook_log(f"lock: breaking stale lock {self.path} (age {int(age)}s)")
                    shutil.rmtree(self.path, ignore_errors=True)
                    continue
                if time.monotonic() > deadline:
                    raise LockError(
                        f"state is locked by another process ({self.path}, {int(age)}s old). "
                        f"Retry in a moment; if no learning command is running, remove that directory."
                    )
                time.sleep(0.05)

    def __exit__(self, *exc):
        if self.held:
            shutil.rmtree(self.path, ignore_errors=True)
            self.held = False
        return False


# --- state + deck paths and defaults ------------------------------------------------------

STATE_DEFAULT = {"version": STATE_VERSION, "rev": 0, "active_topic": None, "log_target": None, "applied_ops": [], "topics": {}}
DECK_DEFAULT = {"version": DECK_VERSION, "rev": 0, "applied_ops": [], "cards": []}


def state_path() -> pathlib.Path:
    return dir_path("stateDir") / "state.json"


def deck_path() -> pathlib.Path:
    return dir_path("stateDir") / "deck.json"


def journal_path() -> pathlib.Path:
    return dir_path("stateDir") / ".journal.json"


# --- migrations ---------------------------------------------------------------------------

def _empty_node_fields(node: dict, legacy: str) -> None:
    node.setdefault("depends", [])
    node.setdefault("why", "")
    node.setdefault("check", "")
    node.setdefault("summary", "")
    node.setdefault("required", True)
    if legacy == "done":
        node.setdefault("coverage", "covered")
        node.setdefault("readiness", "unknown")  # covered before evidence was recorded: check just in time
    elif legacy == "shaky":
        node.setdefault("coverage", "covered")
        node.setdefault("readiness", "needs_repair")
    else:
        node.setdefault("coverage", "pending")
        node.setdefault("readiness", "unknown")
    node.setdefault("retention", "unassessed")
    node.setdefault("prepared", False)


def migrate_state(state: dict) -> tuple[dict, list[str]]:
    """Bring a state dict to STATE_VERSION. Idempotent: running it on a migrated
    state changes nothing and reports no steps."""
    steps: list[str] = []
    if not isinstance(state, dict):
        raise CorruptStateError("state.json does not contain an object")
    version = int(state.get("version", 1) or 1)
    if version > STATE_VERSION:
        raise CorruptStateError(f"state.json is version {version}; this code understands up to {STATE_VERSION}")
    for key, value in STATE_DEFAULT.items():
        if key not in state:
            state[key] = json.loads(json.dumps(value))
            if key not in ("version",):
                steps.append(f"added {key}")
    if version < 2:
        for slug, topic in state.get("topics", {}).items():
            topic.setdefault("attempts", [])
            topic.setdefault("pending", None)
            topic.setdefault("prep", {})
            topic.setdefault("corrections", [])
            plan = topic.setdefault("plan", {"approved": False, "mermaid": "", "nodes": []})
            for node in plan.get("nodes", []):
                legacy = node.get("status", "pending")
                node["legacy_status"] = legacy
                _empty_node_fields(node, legacy)
                if legacy == "done" and node.get("done_at"):
                    node.setdefault("covered_at", node["done_at"])
        state["version"] = 2
        steps.append("v1 -> v2: nodes gained coverage/readiness/retention (legacy done -> covered + unknown evidence)")
    else:
        for topic in state.get("topics", {}).values():
            topic.setdefault("attempts", [])
            topic.setdefault("pending", None)
            topic.setdefault("prep", {})
            topic.setdefault("corrections", [])
            for node in topic.get("plan", {}).get("nodes", []):
                _empty_node_fields(node, node.get("status", "pending"))
    state["version"] = STATE_VERSION
    return state, steps


def _split_points(points) -> list[str]:
    out: list[str] = []
    for p in points or []:
        for part in str(p).split("|"):
            part = part.strip()
            if part:
                out.append(part)
    return out


def migrate_deck(deck: dict) -> tuple[dict, list[str]]:
    steps: list[str] = []
    if not isinstance(deck, dict):
        raise CorruptStateError("deck.json does not contain an object")
    version = int(deck.get("version", 1) or 1)
    if version > DECK_VERSION:
        raise CorruptStateError(f"deck.json is version {version}; this code understands up to {DECK_VERSION}")
    for key, value in DECK_DEFAULT.items():
        if key not in deck:
            deck[key] = json.loads(json.dumps(value))
    if version < 2:
        split = 0
        for card in deck.get("cards", []):
            # legacy irregularity: a prose `points` string next to key_points -> explanation
            if "points" in card:
                text = card.pop("points")
                if isinstance(text, str) and text.strip() and not card.get("explanation"):
                    card["explanation"] = text.strip()
            before = list(card.get("key_points", []))
            card["key_points"] = _split_points(before)
            if card["key_points"] != before:
                split += 1
            card.setdefault("rubric_version", 1)
            card.setdefault("key_history", [])
            card.setdefault("check", "")
            card.setdefault("kind", "concept")
            card.setdefault("variants", [])
            card.setdefault("asked", [])
            card.setdefault("explanation", "")
            created = card.get("created", "")
            for entry in card.get("history", []):
                entry.setdefault("kind", "initial" if entry.get("date") == created else "review")
                entry.setdefault("valid", True)
                entry.setdefault("rubric_version", 1)
            last_ok = [h["date"] for h in card.get("history", []) if int(h.get("q", 0)) >= 3]
            card.setdefault("last_graduated", max(last_ok) if last_ok else None)
        deck["version"] = 2
        steps.append(f"v1 -> v2: cards gained rubric_version/key_history/kind/variants; {split} '|' key_point lists split")
    else:
        for card in deck.get("cards", []):
            card.setdefault("rubric_version", 1)
            card.setdefault("key_history", [])
            card.setdefault("check", "")
            card.setdefault("kind", "concept")
            card.setdefault("variants", [])
            card.setdefault("asked", [])
            card.setdefault("explanation", "")
            card.setdefault("last_graduated", None)
            for entry in card.get("history", []):
                entry.setdefault("kind", "review")
                entry.setdefault("valid", True)
                entry.setdefault("rubric_version", 1)
    deck["version"] = DECK_VERSION
    return deck, steps


# --- validation ------------------------------------------------------------------------------

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")


def validate_plan(nodes: list[dict]) -> None:
    """Unique ids, known dependencies, no self-dependency, no cycles, valid statuses."""
    if not isinstance(nodes, list):
        raise ValidationError("plan.nodes must be a list")
    ids: list[str] = []
    for n in nodes:
        if not isinstance(n, dict) or "id" not in n or "label" not in n:
            raise ValidationError("every node needs 'id' and 'label'")
        nid = str(n["id"])
        if not _ID_RE.match(nid):
            raise ValidationError(f"node id {nid!r} must be a short identifier (letters, digits, - or _)")
        if nid in ids:
            raise ValidationError(f"duplicate node id {nid!r}")
        ids.append(nid)
    idset = set(ids)
    for n in nodes:
        nid = str(n["id"])
        deps = n.get("depends", [])
        if not isinstance(deps, list):
            raise ValidationError(f"node {nid}: depends must be a list")
        for d in deps:
            if str(d) == nid:
                raise ValidationError(f"node {nid} depends on itself")
            if str(d) not in idset:
                raise ValidationError(f"node {nid} depends on unknown node {d!r}")
        if len(set(map(str, deps))) != len(deps):
            raise ValidationError(f"node {nid}: duplicate dependency")
        for field, allowed in (("status", LEGACY_STATUS), ("coverage", COVERAGE), ("readiness", READINESS), ("retention", RETENTION)):
            if field in n and n[field] not in allowed:
                raise ValidationError(f"node {nid}: {field} must be one of {allowed}, not {n[field]!r}")
        if "required" in n and not isinstance(n["required"], bool):
            raise ValidationError(f"node {nid}: required must be true or false")
    # cycle check (Kahn)
    indeg = {i: 0 for i in ids}
    out: dict[str, list[str]] = {i: [] for i in ids}
    for n in nodes:
        for d in n.get("depends", []):
            out[str(d)].append(str(n["id"]))
            indeg[str(n["id"])] += 1
    queue = [i for i in ids if indeg[i] == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for nxt in out[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if seen != len(ids):
        stuck = sorted(i for i in ids if indeg[i] > 0)
        raise ValidationError(f"plan has a dependency cycle involving {stuck}")


def validate_variant(v: dict, ctype: str, where: str) -> None:
    if not isinstance(v, dict):
        raise ValidationError(f"{where}: variant must be an object")
    if not v.get("id"):
        raise ValidationError(f"{where}: variant needs an id")
    if not str(v.get("question", "")).strip():
        raise ValidationError(f"{where}/{v['id']}: question is empty")
    if ctype == "mcq":
        opts = v.get("options") or []
        if len(opts) < 2:
            raise ValidationError(f"{where}/{v['id']}: mcq needs at least 2 options")
        if v.get("answer") not in opts:
            raise ValidationError(f"{where}/{v['id']}: mcq answer must equal one option exactly")
        if len(set(opts)) != len(opts):
            raise ValidationError(f"{where}/{v['id']}: duplicate options")
    elif ctype == "short":
        if not str(v.get("answer", "")).strip():
            raise ValidationError(f"{where}/{v['id']}: short answer needs a committed model answer")
        if not (v.get("required") or v.get("key_points")):
            raise ValidationError(f"{where}/{v['id']}: short answer needs at least one required point")
    elif ctype == "code":
        if not str(v.get("answer", "")).strip():
            raise ValidationError(f"{where}/{v['id']}: code check needs 'answer' (what a correct approach must contain)")
    v.setdefault("rubric_version", 1)
    v.setdefault("required", [])
    v.setdefault("accepted", [])
    v.setdefault("disqualifying", [])
    v.setdefault("options", [])


def validate_check(c: dict, where: str) -> None:
    if not isinstance(c, dict) or not c.get("id"):
        raise ValidationError(f"{where}: every check needs an id")
    if c.get("type") not in CHECK_TYPES:
        raise ValidationError(f"{where}/{c['id']}: type must be one of {CHECK_TYPES}")
    variants = c.get("variants") or []
    if not variants:
        raise ValidationError(f"{where}/{c['id']}: needs at least one variant")
    seen = set()
    for v in variants:
        validate_variant(v, c["type"], f"{where}/{c['id']}")
        if v["id"] in seen:
            raise ValidationError(f"{where}/{c['id']}: duplicate variant id {v['id']}")
        seen.add(v["id"])
    c.setdefault("role", "normal")
    if c["role"] not in ("normal", "fresh", "transfer", "exit"):
        raise ValidationError(f"{where}/{c['id']}: role must be normal, fresh, transfer or exit")
    c.setdefault("load_bearing", c["type"] != "mcq")
    c.setdefault("review", c["type"] != "mcq")
    c.setdefault("kind", "concept")
    c.setdefault("hints", [])
    if not isinstance(c["hints"], list):
        raise ValidationError(f"{where}/{c['id']}: hints must be a list")
    c.setdefault("exercise", "")


def validate_node_prep(prep: dict) -> None:
    if not isinstance(prep, dict) or not prep.get("id"):
        raise ValidationError("node prep needs an id")
    where = f"prep {prep['id']}"
    if not str(prep.get("objective", "")).strip():
        raise ValidationError(f"{where}: objective is required (what the learner will be able to do)")
    for claim in prep.get("claims", []) or []:
        if not isinstance(claim, dict) or not claim.get("text"):
            raise ValidationError(f"{where}: every claim needs text")
        if claim.get("kind") not in CLAIM_KINDS:
            raise ValidationError(f"{where}: claim {claim.get('id', '?')} kind must be one of {CLAIM_KINDS}")
    for m in prep.get("misconceptions", []) or []:
        if not isinstance(m, dict) or not m.get("text"):
            raise ValidationError(f"{where}: every misconception needs text")
    checks = prep.get("checks") or []
    if not checks:
        raise ValidationError(f"{where}: at least one check is required")
    seen = set()
    for c in checks:
        validate_check(c, where)
        if c["id"] in seen:
            raise ValidationError(f"{where}: duplicate check id {c['id']}")
        seen.add(c["id"])
    prep.setdefault("version", 1)
    prep.setdefault("status", "draft")
    if prep["status"] not in ("draft", "ready"):
        raise ValidationError(f"{where}: status must be draft or ready")
    prep.setdefault("outline", [])
    prep.setdefault("motivation", "")
    prep.setdefault("prerequisites", [])
    prep.setdefault("claims", [])
    prep.setdefault("misconceptions", [])
    prep.setdefault("sources", [])
    prep.setdefault("verified", None)


def validate_topic_prep(prep: dict) -> None:
    if not isinstance(prep, dict):
        raise ValidationError("topic prep must be an object")
    prep.setdefault("capability", "")
    prep.setdefault("environment", {})
    prep.setdefault("chunks", [])
    prep.setdefault("exit_criteria", [])
    prep.setdefault("sources", [])
    ids = set()
    for s in prep["sources"]:
        if not isinstance(s, dict) or not s.get("id") or not (s.get("url") or s.get("path")):
            raise ValidationError("every source needs id and url (or path, for a local document)")
        if s.get("kind") == "document" and s.get("role", "supplementary") not in SOURCE_ROLES:
            raise ValidationError(f"source {s['id']}: role must be one of {SOURCE_ROLES}")
        if s["id"] in ids:
            raise ValidationError(f"duplicate source id {s['id']}")
        ids.add(s["id"])
    for ch in prep["chunks"]:
        if not isinstance(ch, dict) or not ch.get("id") or not isinstance(ch.get("nodes"), list):
            raise ValidationError("every chunk needs id and a nodes list")
    seen = set()
    for x in prep["exit_criteria"]:
        if not isinstance(x, dict) or not x.get("id") or not x.get("text"):
            raise ValidationError("every exit criterion needs id and text")
        if x["id"] in seen:
            raise ValidationError(f"duplicate exit criterion id {x['id']}")
        seen.add(x["id"])
        for c in x.get("checks", []) or []:
            validate_check(c, f"exit {x['id']}")


def validate_source_digest(d: dict) -> None:
    """The document-reader's digest of one local document (see docs/SYSTEM.md)."""
    if not isinstance(d, dict) or not str(d.get("summary", "")).strip():
        raise ValidationError("digest needs a summary")
    for key in ("objectives", "sections", "prerequisites_outside", "conflicts", "node_map"):
        d.setdefault(key, [])
        if not isinstance(d[key], list):
            raise ValidationError(f"digest {key} must be a list")
    seen = set()
    for sec in d["sections"]:
        if not isinstance(sec, dict) or not sec.get("id") or not sec.get("title"):
            raise ValidationError("every digest section needs id and title")
        if sec["id"] in seen:
            raise ValidationError(f"duplicate digest section id {sec['id']}")
        seen.add(sec["id"])
    for c in d["conflicts"]:
        if not isinstance(c, dict) or not c.get("claim") or not c.get("issue"):
            raise ValidationError("every conflict needs claim and issue")
    for m in d["node_map"]:
        if not isinstance(m, dict) or not m.get("node"):
            raise ValidationError("every node_map entry needs node")


def validate_card(card: dict) -> None:
    for field in ("id", "topic", "type", "question", "answer"):
        if field not in card:
            raise ValidationError(f"card missing {field}")
    if card["type"] not in CHECK_TYPES:
        raise ValidationError(f"card {card['id']}: type must be one of {CHECK_TYPES}")
    if card["type"] == "mcq" and card.get("options") and card["answer"] not in card["options"]:
        raise ValidationError(f"card {card['id']}: mcq answer must equal one option exactly")
    for v in card.get("variants", []) or []:
        validate_variant(v, card["type"], f"card {card['id']}")


def validate_attempt(a: dict) -> None:
    for field in ("id", "ts", "node", "kind", "result"):
        if field not in a:
            raise ValidationError(f"attempt missing {field}")
    if a["kind"] not in ATTEMPT_KINDS:
        raise ValidationError(f"attempt {a['id']}: kind must be one of {ATTEMPT_KINDS}")
    if a["result"] not in RESULTS:
        raise ValidationError(f"attempt {a['id']}: result must be one of {RESULTS}")
    if a.get("assistance", "none") not in ASSISTANCE:
        raise ValidationError(f"attempt {a['id']}: assistance must be one of {ASSISTANCE}")
    q = a.get("quality")
    if q is not None and not (isinstance(q, int) and 0 <= q <= 5):
        raise ValidationError(f"attempt {a['id']}: quality must be 0-5")


def validate_pending(p: dict | None) -> None:
    if p is None:
        return
    for field in ("id", "type", "topic", "node", "check", "variant", "rubric_version", "stage"):
        if field not in p:
            raise ValidationError(f"pending interaction missing {field}")
    if p["stage"] not in ("awaiting", "recorded", "completed"):
        raise ValidationError("pending.stage must be awaiting, recorded or completed")
    if p["type"] not in CHECK_TYPES:
        raise ValidationError(f"pending.type must be one of {CHECK_TYPES}")


def validate_state(state: dict) -> None:
    if state.get("version") != STATE_VERSION:
        raise ValidationError(f"state version {state.get('version')} != {STATE_VERSION}")
    for slug, topic in state.get("topics", {}).items():
        if topic.get("status") not in TOPIC_STATUS:
            raise ValidationError(f"topic {slug}: status {topic.get('status')!r} invalid")
        validate_plan(topic.get("plan", {}).get("nodes", []))
        validate_pending(topic.get("pending"))
        for a in topic.get("attempts", []):
            validate_attempt(a)


def validate_deck(deck: dict) -> None:
    if deck.get("version") != DECK_VERSION:
        raise ValidationError(f"deck version {deck.get('version')} != {DECK_VERSION}")
    seen = set()
    for card in deck.get("cards", []):
        validate_card(card)
        if card["id"] in seen:
            raise ValidationError(f"duplicate card id {card['id']}")
        seen.add(card["id"])


# --- the store: lock, load, migrate, commit through a journal --------------------------------------

def recover_journal(quiet: bool = False) -> bool:
    """Finish an interrupted multi-file commit. Safe to call any time: the journal
    holds the complete content of every file the operation writes, so re-applying
    it is idempotent. Returns True if something was recovered."""
    jp = journal_path()
    if not jp.exists():
        return False
    try:
        journal = json.loads(jp.read_text("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CorruptStateError(f"{jp} is unreadable ({exc}); inspect it, then delete it to continue") from exc
    for path, data in journal.get("writes", {}).items():
        write_json(path, data)
    jp.unlink()
    hook_log(f"journal: recovered op {journal.get('op')} ({len(journal.get('writes', {}))} file(s))")
    if not quiet:
        print(f"note: recovered interrupted operation {journal.get('op')}", file=sys.stderr)
    return True


def _load_raw(path, default) -> dict:
    data = read_json(path, None)
    if data is None:
        return json.loads(json.dumps(default))
    return data


class Store:
    """Read-modify-write of state.json and deck.json.

    with Store(write=True) as st:
        ... mutate st.state / st.deck ...
        st.commit(op_id="...")

    Read-only use (write=False) takes no lock and never writes, but still migrates
    in memory so callers see one schema. Migration of the files on disk happens on
    the first write, after byte-for-byte backups.
    """

    def __init__(self, write: bool = False, lock_timeout: float = 5.0):
        self.write = write
        self.lock = Lock(timeout=lock_timeout) if write else None
        self.state: dict = {}
        self.deck: dict = {}
        self._state_rev = 0
        self._deck_rev = 0
        self._deck_loaded = False
        self.migration_steps: list[str] = []
        self.committed = False

    def __enter__(self):
        if self.lock:
            self.lock.__enter__()
            recover_journal(quiet=True)
        try:
            self._load()
        except BaseException:
            if self.lock:
                self.lock.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.lock:
            self.lock.__exit__(exc_type, exc, tb)
        return False

    def _load(self):
        raw_state = _load_raw(state_path(), STATE_DEFAULT)
        self._state_rev = int(raw_state.get("rev", 0) or 0)
        self.state, steps = migrate_state(raw_state)
        self.migration_steps = [f"state: {s}" for s in steps]
        raw_deck = _load_raw(deck_path(), DECK_DEFAULT)
        self._deck_rev = int(raw_deck.get("rev", 0) or 0)
        self.deck, dsteps = migrate_deck(raw_deck)
        self.migration_steps += [f"deck: {s}" for s in dsteps]

    def already_applied(self, op_id: str | None) -> bool:
        if not op_id:
            return False
        return op_id in self.state.get("applied_ops", []) or op_id in self.deck.get("applied_ops", [])

    def commit(self, op_id: str | None = None, touch_deck: bool | None = None) -> None:
        """Validate, then write state (and deck if it changed or touch_deck) through the journal."""
        if not self.write:
            raise LearnError("Store opened read-only")
        validate_state(self.state)
        validate_deck(self.deck)
        # conflict check: the file must still carry the rev we loaded
        on_disk = read_json(state_path(), None)
        if on_disk is not None and int(on_disk.get("rev", 0) or 0) != self._state_rev:
            raise ConflictError(
                f"state.json changed underneath this command (rev {on_disk.get('rev')} on disk, {self._state_rev} loaded). "
                f"Nothing was written. Re-run the command."
            )
        deck_on_disk = read_json(deck_path(), None)
        if deck_on_disk is not None and int(deck_on_disk.get("rev", 0) or 0) != self._deck_rev:
            raise ConflictError(
                f"deck.json changed underneath this command (rev {deck_on_disk.get('rev')} on disk, {self._deck_rev} loaded). "
                f"Nothing was written. Re-run the command."
            )
        if self.migration_steps:
            for p in (state_path(), deck_path()):
                backup_file(p, label="premigration")
        if op_id:
            for holder in (self.state, self.deck):
                ops = holder.setdefault("applied_ops", [])
                if op_id not in ops:
                    ops.append(op_id)
                if len(ops) > MAX_APPLIED_OPS:
                    del ops[:-MAX_APPLIED_OPS]
        self.state["rev"] = self._state_rev + 1
        self.deck["rev"] = self._deck_rev + 1
        writes = {str(state_path()): self.state, str(deck_path()): self.deck}
        journal = {"op": op_id or "", "ts": ts(), "writes": writes}
        write_json(journal_path(), journal)
        for path, data in writes.items():
            write_json(path, data)
        journal_path().unlink()
        self._state_rev = self.state["rev"]
        self._deck_rev = self.deck["rev"]
        self.committed = True


def load_state() -> dict:
    """Read-only, migrated-in-memory state (hooks, show). Raises CorruptStateError on a bad file."""
    recover_journal(quiet=True)
    state, _ = migrate_state(_load_raw(state_path(), STATE_DEFAULT))
    return state


def load_deck() -> dict:
    recover_journal(quiet=True)
    deck, _ = migrate_deck(_load_raw(deck_path(), DECK_DEFAULT))
    return deck


def save_state(state: dict) -> None:
    """Compatibility shim: single-file write with lock + rev check."""
    with Store(write=True) as st:
        st.state = state
        st.commit()


# --- lesson-session detection ------------------------------------------------

LESSON_SKILLS = {"teach", "review"}
_STATE_CMD = re.compile(r"scripts/state\.py\s+(start|resume|log-target|ask|record)\b")
_SLASH_CMD = re.compile(r"<command-name>/(teach|review)\b")


def lesson_flag_path(session_id: str) -> pathlib.Path:
    return dir_path("stateDir") / ".cursors" / f"{session_id}.lesson"


_HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")
_QUOTED = re.compile(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"")


def _invoked_text(command: str) -> str:
    """The parts of a shell command that are actually executed: heredoc bodies and
    quoted strings removed. Writing a file or a commit message that merely mentions
    `state.py ask` must not turn a build session into a lesson."""
    out: list[str] = []
    delim = None
    for line in command.splitlines():
        if delim is not None:
            if line.strip() == delim:
                delim = None
            continue
        m = _HEREDOC.search(line)
        if m:
            delim = m.group(1)
        out.append(_QUOTED.sub("''", line))
    return "\n".join(out)


def _entry_marks_lesson(entry: dict) -> bool:
    if entry.get("isSidechain"):
        return False
    message = entry.get("message") or {}
    content = message.get("content")
    if entry.get("type") == "user":
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
        else:
            text = ""
        return bool(_SLASH_CMD.search(text))
    if entry.get("type") == "assistant" and isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            inp = block.get("input") or {}
            if name == "Skill" and str(inp.get("skill", "")).split(":")[-1] in LESSON_SKILLS:
                return True
            if name == "Bash" and _STATE_CMD.search(_invoked_text(str(inp.get("command", "")))):
                return True
    return False


def lesson_session(transcript_path, session_id: str) -> dict | None:
    """Is this Claude Code session a lesson or review session?

    A session counts from the moment /teach or /review was invoked (typed as a
    slash command or loaded through the Skill tool), or a Bash call ran
    state.py start / resume / log-target / ask / record. Ordinary coding sessions
    in this repo never qualify, so the hooks leave them alone. The answer is
    cached in a flag file together with the byte offset where the lesson began.
    """
    if not session_id:
        return None
    flag = lesson_flag_path(session_id)
    cached = read_json_lenient(flag, None)
    if isinstance(cached, dict):
        return cached
    if not transcript_path:
        return None
    transcript = pathlib.Path(transcript_path)
    if not transcript.exists():
        return None
    offset = 0
    with open(transcript, "rb") as handle:
        for raw in handle:
            line_offset = offset
            offset += len(raw)
            if b"command-name" not in raw and b'"Skill"' not in raw and b"state.py" not in raw:
                continue
            try:
                entry = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            if _entry_marks_lesson(entry):
                data = {"offset": line_offset, "found": ts()}
                write_json(flag, data)
                return data
    return None


# Lesson work in progress: a state command a lesson turn runs (not `checkpoint`, which the
# Stop hook itself asks for and must not keep a finished lesson alive).
_ACTIVITY_CMD = re.compile(r"scripts/state\.py\s+(start|resume|log-target|ask|record|hint|pending|answer|prep-show|source-show|next-node)\b")
LESSON_IDLE_PROMPTS = 2


def _is_prompt(entry: dict) -> bool:
    """A message the learner typed (not a tool result, skill body, hook feedback or summary)."""
    if entry.get("type") != "user" or entry.get("isSidechain") or entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict)]
        return any(b.get("type") == "text" for b in blocks) and not any(b.get("type") == "tool_result" for b in blocks)
    return False


def _entry_is_lesson_activity(entry: dict) -> bool:
    if entry.get("isSidechain"):
        return False
    if entry.get("type") == "user":
        return _entry_marks_lesson(entry)
    content = (entry.get("message") or {}).get("content")
    if entry.get("type") == "assistant" and isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            inp = block.get("input") or {}
            if block.get("name") == "Skill" and str(inp.get("skill", "")).split(":")[-1] in LESSON_SKILLS:
                return True
            if block.get("name") == "Bash" and _ACTIVITY_CMD.search(_invoked_text(str(inp.get("command", "")))):
                return True
    return False


def prompts_since_lesson_activity(transcript_path, offset: int = 0) -> int | None:
    """How many learner prompts ago the last lesson activity happened (0 = in the current
    turn). A session that moved on from the lesson to other work (committing, editing the
    system) stops counting as a live lesson after LESSON_IDLE_PROMPTS prompts, so the
    checkpoint hook leaves it alone. None when the transcript cannot be read."""
    if not transcript_path:
        return None
    transcript = pathlib.Path(transcript_path)
    if not transcript.exists():
        return None
    count = None
    with open(transcript, "rb") as handle:
        handle.seek(max(0, int(offset or 0)))
        for raw in handle:
            if b'"user"' not in raw and b"state.py" not in raw and b'"Skill"' not in raw:
                continue
            try:
                entry = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            if count is not None and _is_prompt(entry):
                count += 1
            if _entry_is_lesson_activity(entry):
                count = 0
    return count


def hook_log(message: str) -> None:
    """Best-effort diagnostics for hooks (never raises)."""
    try:
        log_dir = dir_path("stateDir") / ".log"
        log_dir.mkdir(parents=True, exist_ok=True)
        append_text(log_dir / "hooks.log", f"{ts()} {message}\n")
    except Exception:  # noqa: BLE001
        pass


def cli_main(fn):
    """Run a command function; print LearnError messages cleanly and exit 1."""
    try:
        return fn()
    except LearnError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
