#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


def fail(message: str) -> None:
    raise SystemExit(f"pulse vitals alignment: {message}")


path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pulse.svg")
svg = path.read_text()

# True flatlines have no bottom vitals row, so there is nothing to align.
if "HEART RATE" not in svg:
    print("Pulse vitals alignment skipped: no active vitals row")
    raise SystemExit(0)

# Keep the existing labels fixed and center each value beneath the visual center
# of its corresponding label. The centers are derived from the rendered mono
# label widths in the current four-column bottom strip.
expected_labels = (
    'x="36" y="222"',
    'x="219" y="222"',
    'x="415" y="222"',
    'x="612" y="222"',
)
for label in expected_labels:
    if svg.count(label) != 1:
        fail(f"expected one label anchor {label}, found {svg.count(label)}")

replacements = (
    ('x="22" y="246"', 'x="71" y="246" text-anchor="middle"', "heart-rate value"),
    ('x="219" y="246"', 'x="258" y="246" text-anchor="middle"', "merges/open-pr value"),
    ('x="415" y="246"', 'x="457" y="246" text-anchor="middle"', "reviews/open-issues value"),
    ('x="612" y="246"', 'x="657" y="246" text-anchor="middle"', "streak/type value"),
)
for old, new, name in replacements:
    count = svg.count(old)
    if count != 1:
        fail(f"expected one {name} target, found {count}")
    svg = svg.replace(old, new, 1)

if svg.count('y="246" text-anchor="middle"') != 4:
    fail("expected four centered bottom-row values")

path.write_text(svg)
print("Pulse vitals alignment verified: four bottom-row values centered under labels")
