#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys


def fail(message: str) -> None:
    raise SystemExit(f"pulse flatline postprocess: {message}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"expected one {label} target, found {count}")
    return text.replace(old, new, 1)


path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pulse.svg")
mode = (sys.argv[2] if len(sys.argv) > 2 else "").strip().lower()
if mode not in {"user", "repo"}:
    fail(f"unsupported mode: {mode!r}")

svg = path.read_text()
if 'viewBox="0 0 830 260"' not in svg:
    fail("expected 830x260 Wide+ SVG")
if not re.search(r'<title[^>]*>[^<]*flatlined', svg, re.IGNORECASE):
    fail("flatline title not found")
if "HEART RATE" in svg:
    fail("flatline unexpectedly contained active vitals")

# Profile cards omit the account heading; repository cards keep their label.
if mode == "user":
    svg, header_count = re.subn(
        r'\s*<text x="26" y="32"[\s\S]*?</text>\n',
        '\n',
        svg,
        count=1,
    )
    if header_count != 1:
        fail(f"expected one in-card account heading, found {header_count}")

# A provider flatline is structurally different from an active card: it has one
# resting trace and no heartbeat/vitals animation. Keep that semantic state while
# applying the same final full-width monitor geometry used by active cards.
svg = replace_once(
    svg,
    'x="200" y="48" width="614" height="160"',
    'x="22" y="42" width="786" height="148"',
    "ECG grid",
)
svg = replace_once(
    svg,
    'x1="210" y1="128" x2="804" y2="128"',
    'x1="22" y1="126" x2="808" y2="126"',
    "level baseline",
)
svg = replace_once(
    svg,
    'd="M210 128 H804"',
    'd="M22 126 H808"',
    "flatline ECG path",
)
svg = replace_once(
    svg,
    '<feGaussianBlur stdDeviation="2.6" result="b"/>',
    '<feGaussianBlur stdDeviation="1.7" result="b"/>',
    "ECG glow blur",
)

# There is no bottom vitals strip in a true flatline, so remove the old vertical
# rail divider instead of converting it into an empty horizontal strip.
divider_re = re.compile(
    r'\s*<line x1="190" y1="48" x2="190" y2="244" '
    r'stroke="[^"]+" stroke-width="1" opacity="0\.55"/>\n?'
)
svg, divider_count = divider_re.subn('\n', svg, count=1)
if divider_count != 1:
    fail(f"expected one legacy divider, found {divider_count}")

# Keep state chrome aligned to the final 22..808 monitor bounds.
pill_re = re.compile(
    r'(<rect class="gp-pill-pulse" x=")([0-9.]+)(" y="18" width=")([0-9.]+)(" height="19")'
)
pill = pill_re.search(svg)
if not pill:
    fail("state pill not found")
pill_width = float(pill.group(4))
pill_x = 808.0 - pill_width
svg, pill_count = pill_re.subn(
    lambda m: m.group(1) + f"{pill_x:g}" + m.group(3) + m.group(4) + m.group(5),
    svg,
    count=1,
)
if pill_count != 1:
    fail(f"expected one state pill, found {pill_count}")

state_text_re = re.compile(r'(<text x=")([0-9.]+)(" y="31" text-anchor="middle")')
svg, state_count = state_text_re.subn(
    lambda m: m.group(1) + f"{pill_x + pill_width / 2.0:g}" + m.group(3),
    svg,
    count=1,
)
if state_count != 1:
    fail(f"expected one state label, found {state_count}")

svg = replace_once(
    svg,
    'x="804" y="238" text-anchor="end"',
    'x="808" y="198" text-anchor="end"',
    "ECG lower-right status",
)

for forbidden in (
    'x="200" y="48" width="614"',
    'x1="190" y1="48" x2="190" y2="244"',
    'x1="210" y1="128" x2="804" y2="128"',
    'd="M210 128 H804"',
):
    if forbidden in svg:
        fail(f"legacy flatline geometry survived: {forbidden}")
if svg.count('class="gp-flat"') != 1:
    fail("expected exactly one flatline trace")

path.write_text(svg)
print(f"Pulse flatline postprocess verified: mode={mode}; full-width resting ECG; bpm=0")
