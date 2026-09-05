#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


def fail(message: str) -> None:
    raise SystemExit(f"pulse vitals alignment: {message}")


path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pulse.svg")
svg = path.read_text()

if "HEART RATE" not in svg:
    fail("expected bottom vitals row")

# Keep the current four columns, center each value under its label, and add real
# vertical breathing room between the small uppercase label row and the large
# value row. The divider remains at y=207; labels move to y=219 and values to
# y=250, leaving a visible gap without crowding the card bottom.
label_replacements = (
    ('x="36" y="222"', 'x="36" y="219"', "heart-rate label"),
    ('x="219" y="222"', 'x="219" y="219"', "metric-2 label"),
    ('x="415" y="222"', 'x="415" y="219"', "metric-3 label"),
    ('x="612" y="222"', 'x="612" y="219"', "streak/type label"),
)
for old, new, name in label_replacements:
    count = svg.count(old)
    if count != 1:
        fail(f"expected one {name} target, found {count}")
    svg = svg.replace(old, new, 1)

heart_old = 'class="gp-heart" x="22" y="222"'
heart_new = 'class="gp-heart" x="22" y="219"'
if svg.count(heart_old) != 1:
    fail(f"expected one heart accent target, found {svg.count(heart_old)}")
svg = svg.replace(heart_old, heart_new, 1)

value_replacements = (
    ('x="22" y="246"', 'x="71" y="250" text-anchor="middle"', "heart-rate value"),
    ('x="219" y="246"', 'x="258" y="250" text-anchor="middle"', "merges/open-pr value"),
    ('x="415" y="246"', 'x="457" y="250" text-anchor="middle"', "reviews/open-issues value"),
    ('x="612" y="246"', 'x="657" y="250" text-anchor="middle"', "streak/type value"),
)
for old, new, name in value_replacements:
    count = svg.count(old)
    if count != 1:
        fail(f"expected one {name} target, found {count}")
    svg = svg.replace(old, new, 1)

if svg.count('y="250" text-anchor="middle"') != 4:
    fail("expected four centered bottom-row values")
if svg.count('y="219"') < 5:
    fail("expected aligned label row and heart accent at y=219")

path.write_text(svg)
print(
    "Pulse vitals alignment verified: four values centered with vertical breathing room"
)
