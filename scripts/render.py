#!/usr/bin/env python3
"""Render a Mermaid (.mmd) or SVG (.svg) file to PNG so a maker agent can look at it.

Usage:
  python scripts/render.py input.mmd output.png
  python scripts/render.py input.svg output.png

Mermaid: uses tools/node_modules/.bin/mmdc with the system Chrome if it is
installed, otherwise Chrome headless with mermaid from a CDN.
SVG: rsvg-convert if available, otherwise Chrome headless.
The PNG is auto-cropped to its content when Pillow is available.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(os.environ.get("CLAUDE_PROJECT_DIR") or pathlib.Path(__file__).resolve().parent.parent).resolve()
_MMDC_DIR = ROOT / "tools" / "node_modules" / ".bin"
MMDC = next((_MMDC_DIR / n for n in ("mmdc.cmd", "mmdc.exe", "mmdc") if (_MMDC_DIR / n).exists()), _MMDC_DIR / "mmdc")
CHROME_CANDIDATES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "chrome.exe", "msedge.exe"]
WINDOWS_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_chrome() -> str | None:
    env = os.environ.get("CHROME_PATH")
    if env and pathlib.Path(env).exists():
        return env
    for name in CHROME_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    for path in WINDOWS_CHROME_PATHS:
        if pathlib.Path(path).exists():
            return path
    return None


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def autocrop(png: pathlib.Path, margin: int = 24) -> None:
    try:
        from PIL import Image, ImageChops
    except Exception:  # noqa: BLE001
        return
    try:
        img = Image.open(png).convert("RGB")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        diff = ImageChops.difference(img, bg)
        bbox = diff.getbbox()
        if bbox:
            left = max(0, bbox[0] - margin)
            top = max(0, bbox[1] - margin)
            right = min(img.width, bbox[2] + margin)
            bottom = min(img.height, bbox[3] + margin)
            img.crop((left, top, right, bottom)).save(png)
    except Exception:  # noqa: BLE001
        pass


def chrome_screenshot(chrome: str, url: str, out: pathlib.Path, width: int, height: int, budget_ms: int = 6000) -> subprocess.CompletedProcess:
    """Chrome resolves --screenshot against its own cwd, so the path must be absolute."""
    out.parent.mkdir(parents=True, exist_ok=True)
    return run([
        chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
        "--force-device-scale-factor=2", f"--window-size={width},{height}",
        f"--virtual-time-budget={budget_ms}", f"--screenshot={out.resolve()}", url,
    ])


def svg_size(svg_text: str) -> tuple[int, int]:
    def attr(name: str) -> float | None:
        m = re.search(rf'<svg[^>]*\s{name}="([\d.]+)(px)?"', svg_text)
        return float(m.group(1)) if m else None
    w, h = attr("width"), attr("height")
    if not (w and h):
        m = re.search(r'viewBox="\s*[\d.-]+\s+[\d.-]+\s+([\d.]+)\s+([\d.]+)', svg_text)
        if m:
            w, h = float(m.group(1)), float(m.group(2))
    return int(w or 1200) + 40, int(h or 800) + 40


def render_mermaid(src: pathlib.Path, out: pathlib.Path, chrome: str | None) -> str:
    if MMDC.exists() and chrome:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "puppeteer.json"
            cfg.write_text(json.dumps({"executablePath": chrome, "args": ["--no-sandbox"]}), "utf-8")
            res = run([str(MMDC), "-i", str(src), "-o", str(out), "-p", str(cfg), "-s", "2", "-b", "white"],
                      timeout=180)
        if res.returncode == 0 and out.exists():
            return "mmdc"
        err = (res.stderr or res.stdout).strip().splitlines()[-25:]
        raise RuntimeError("mmdc failed:\n" + "\n".join(err))
    if not chrome:
        raise RuntimeError("No renderer: install Chrome (google-chrome) or run npm install in tools/.")
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<script src='https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js'></script>"
        "<style>body{margin:24px;background:#fff;font-family:sans-serif}</style></head><body>"
        "<pre class='mermaid'>" + src.read_text("utf-8").replace("<", "&lt;") + "</pre>"
        "<script>mermaid.initialize({startOnLoad:true,theme:'default'});</script></body></html>"
    )
    with tempfile.TemporaryDirectory() as tmp:
        page = pathlib.Path(tmp) / "diagram.html"
        page.write_text(html, "utf-8")
        res = chrome_screenshot(chrome, page.as_uri(), out, 1600, 1200, budget_ms=10000)
    if res.returncode != 0 or not out.exists():
        raise RuntimeError("Chrome screenshot failed:\n" + (res.stderr or res.stdout)[-1500:])
    autocrop(out)
    return "chrome+cdn"


def render_svg(src: pathlib.Path, out: pathlib.Path, chrome: str | None) -> str:
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        res = run([rsvg, "-z", "2", "-b", "white", str(src), "-o", str(out)])
        if res.returncode == 0 and out.exists():
            return "rsvg-convert"
    if not chrome:
        raise RuntimeError("No renderer: install rsvg-convert (librsvg2-bin) or Chrome.")
    width, height = svg_size(src.read_text("utf-8", "replace"))
    html = ("<!doctype html><html><head><meta charset='utf-8'><style>body{margin:0;background:#fff}img{display:block;margin:16px}</style>"
            f"</head><body><img src='{src.resolve().as_uri()}'></body></html>")
    with tempfile.TemporaryDirectory() as tmp:
        page = pathlib.Path(tmp) / "svg.html"
        page.write_text(html, "utf-8")
        res = chrome_screenshot(chrome, page.as_uri(), out, width + 32, height + 32)
    if res.returncode != 0 or not out.exists():
        raise RuntimeError("Chrome screenshot failed:\n" + (res.stderr or res.stdout)[-1500:])
    autocrop(out)
    return "chrome"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, out = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    if not src.exists():
        print(f"error: {src} does not exist")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    try:
        if src.suffix.lower() in (".mmd", ".mermaid"):
            how = render_mermaid(src, out, chrome)
        elif src.suffix.lower() == ".svg":
            how = render_svg(src, out, chrome)
        else:
            print("error: input must be .mmd or .svg")
            return 1
    except Exception as exc:  # noqa: BLE001
        print(f"RENDER FAILED ({src.name}): {exc}")
        return 1
    size = ""
    try:
        from PIL import Image
        with Image.open(out) as img:
            size = f" {img.width}x{img.height}px"
    except Exception:  # noqa: BLE001
        pass
    print(f"Rendered {src.name} -> {out} via {how}{size}. Now LOOK at it with the Read tool.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
