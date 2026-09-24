#!/usr/bin/env python3
"""Stop hook: mirror the lesson into the Obsidian note.

Reads the Claude Code transcript (JSONL) from the position reached last time
and appends reading-relevant content to the current log target:
  - the learner's prompts            -> [!quote] YOU · HH:MM
  - the teacher's prose              -> [!abstract] TEACHER
  - AskUserQuestion questions        -> [!question] callout with the options
  - the learner's chosen answers     -> [!example] Answer

Tool calls, tool output and thinking are skipped. Nothing is logged unless
state.log_target is set (a lesson or review is active), so ordinary coding
sessions in this repo never touch the vault. Never blocks the session: any
error is written to state/.log/hooks.log and the hook exits 0.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import learnlib as L

SKIP_PREFIXES = ("<command-name>", "<command-message>", "<local-command-stdout>", "<system-reminder>", "<ide_", "<task-notification>")


def clean_user_text(text: str) -> str:
    text = re.sub(r"<system-reminder>[\s\S]*?</system-reminder>", "", text)
    text = re.sub(r"<pasted_content[^>]*>[\s\S]*?</pasted_content[^>]*>", "[pasted content]", text)
    text = text.strip()
    if not text or text.startswith(SKIP_PREFIXES) or re.match(r"^<[a-z_-]+[ >]", text):
        return ""
    return text


def blocks_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def local_hhmm(iso: str | None) -> str:
    parsed = L.parse_ts(iso)
    return parsed.strftime("%H:%M") if parsed else ""


def callout(kind: str, title: str, body: str) -> str:
    lines = [f"> [!{kind}] {title}"]
    for line in body.splitlines() or [""]:
        lines.append(f"> {line}" if line else ">")
    return "\n".join(lines)


def format_question(block: dict) -> str:
    inp = block.get("input") or {}
    out = []
    for q in inp.get("questions", []) or []:
        header = q.get("header") or "Question"
        body = [q.get("question", "").strip()]
        opts = q.get("options") or []
        if opts:
            body.append("")
            for i, opt in enumerate(opts, 1):
                label = opt.get("label", "")
                desc = opt.get("description")
                body.append(f"{i}. {label}" + (f" — {desc}" if desc else ""))
        if q.get("multiSelect"):
            body.append("")
            body.append("_(select all that apply)_")
        out.append(callout("question", header, "\n".join(body)))
    return "\n\n".join(out)


def process(transcript: pathlib.Path, cursor_path: pathlib.Path, target: pathlib.Path) -> int:
    cursor = L.read_json(cursor_path, {"offset": 0, "pending": {}})
    offset = int(cursor.get("offset", 0))
    pending = dict(cursor.get("pending", {}))
    size = transcript.stat().st_size
    if offset > size:
        offset = 0
    chunks: list[str] = []
    with open(transcript, "rb") as handle:
        handle.seek(offset)
        data = handle.read()
    if not data.endswith(b"\n"):
        # last line may be partial; keep it for next time
        last_nl = data.rfind(b"\n")
        data = data[: last_nl + 1] if last_nl >= 0 else b""
    new_offset = offset + len(data)
    for raw in data.decode("utf-8", "replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        if entry.get("isSidechain") or entry.get("isMeta"):
            continue
        kind = entry.get("type")
        message = entry.get("message") or {}
        content = message.get("content")
        stamp = local_hhmm(entry.get("timestamp"))
        if kind == "user":
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                        answer = blocks_text(block.get("content")).strip()
                        pending.pop(block.get("tool_use_id"), None)
                        if answer:
                            chunks.append(callout("example", f"Answer · {stamp}", answer))
            text = clean_user_text(blocks_text(content))
            if text:
                chunks.append(f"> [!quote] YOU · {stamp}\n\n{text}")
        elif kind == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text:
                        chunks.append(f"> [!abstract] TEACHER\n\n{text}")
                elif block.get("type") == "tool_use" and block.get("name") == "AskUserQuestion":
                    formatted = format_question(block)
                    if formatted:
                        chunks.append(formatted)
                        pending[block.get("id", "")] = True
    if chunks:
        L.append_text(target, "\n\n" + "\n\n".join(chunks) + "\n")
    L.write_json(cursor_path, {"offset": new_offset, "pending": pending})
    return len(chunks)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        payload = {}
    try:
        state = L.load_state()
        target = state.get("log_target")
        if not target:
            return
        transcript_path = payload.get("transcript_path")
        if not transcript_path or not pathlib.Path(transcript_path).exists():
            return
        session_id = payload.get("session_id") or pathlib.Path(transcript_path).stem
        cursor_path = L.dir_path("stateDir") / ".cursors" / f"{session_id}.json"
        written = process(pathlib.Path(transcript_path), cursor_path, L.resolve(target))
        if written:
            L.hook_log(f"session_log: appended {written} block(s) to {L.rel(target)}")
    except Exception as exc:  # noqa: BLE001
        L.hook_log(f"session_log error: {exc!r}")


if __name__ == "__main__":
    main()
