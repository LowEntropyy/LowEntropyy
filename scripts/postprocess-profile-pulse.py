#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys


def fail(message: str) -> None:
    raise SystemExit(f"profile pulse postprocess: {message}")


def fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"expected one {label} target, found {count}")
    return text.replace(old, new, 1)


def horizontal_extent(d: str) -> tuple[float, float]:
    start = re.match(r"M(-?[0-9]+(?:\.[0-9]+)?)\s+-?[0-9]+(?:\.[0-9]+)?", d)
    if not start:
        fail("could not parse ECG start point")
    x0 = float(start.group(1))
    x = x0
    for value in re.findall(r"\bh(-?[0-9]+(?:\.[0-9]+)?)", d):
        x += float(value)
    for dx, _dy in re.findall(
        r"\bl(-?[0-9]+(?:\.[0-9]+)?)\s+(-?[0-9]+(?:\.[0-9]+)?)", d
    ):
        x += float(dx)
    for _cpx, _cpy, dx, _dy in re.findall(
        r"\bq(-?[0-9]+(?:\.[0-9]+)?)\s+(-?[0-9]+(?:\.[0-9]+)?)\s+"
        r"(-?[0-9]+(?:\.[0-9]+)?)\s+(-?[0-9]+(?:\.[0-9]+)?)",
        d,
    ):
        x += float(dx)
    return x0, x


path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pulse.svg")
svg = path.read_text()

if 'viewBox="0 0 830 260"' not in svg:
    fail("expected 830x260 Wide+ SVG")

# Tight, symmetric vitals rail. Four groups keep one 46px vertical cadence and
# the same 26px label-to-value rhythm; the ECG gets the reclaimed width.
rail_positions = [
    ('x="26" y="32"', 'x="22" y="30"', "header"),
    ('x="26" y="72"', 'x="22" y="65"', "heart-rate label"),
    ('x="26" y="98"', 'x="22" y="91"', "heart icon"),
    ('x="48" y="98"', 'x="44" y="91"', "heart-rate value"),
    ('x="26" y="120"', 'x="22" y="111"', "merges label"),
    ('x="26" y="146"', 'x="22" y="137"', "merges value"),
    ('x="26" y="168"', 'x="22" y="157"', "reviews label"),
    ('x="26" y="194"', 'x="22" y="183"', "reviews value"),
    ('x="26" y="216"', 'x="22" y="203"', "streak label"),
    ('x="26" y="242"', 'x="22" y="229"', "streak value"),
]
for old, new, label in rail_positions:
    svg = replace_once(svg, old, new, label)

# Reclaim the right side for one dominant ECG field. Keep the baseline exactly
# horizontal, but place it lower so the stronger R peaks occupy the field more
# evenly while the S trough remains deliberately shallow.
svg = replace_once(
    svg,
    'x="200" y="48" width="614" height="160"',
    'x="166" y="44" width="648" height="172"',
    "ECG grid",
)
svg = replace_once(
    svg,
    'x1="190" y1="48" x2="190" y2="244"',
    'x1="154" y1="44" x2="154" y2="236"',
    "rail divider",
)
svg = replace_once(
    svg,
    'x1="210" y1="128" x2="804" y2="128"',
    'x1="174" y1="146" x2="808" y2="146"',
    "level baseline",
)

# Keep the dominant trace crisp. Amplitude supplies the visual power; an overly
# wide blur around tall R peaks is what turns an ECG spike into a red column.
svg = replace_once(
    svg,
    '<feGaussianBlur stdDeviation="2.6" result="b"/>',
    '<feGaussianBlur stdDeviation="2.2" result="b"/>',
    "ECG glow blur",
)
svg = replace_once(
    svg,
    'stroke="#C4452F" stroke-width="5.2" stroke-linecap="round"\n             stroke-dasharray="250 750" opacity="0.11"',
    'stroke="#C4452F" stroke-width="4.4" stroke-linecap="round"\n             stroke-dasharray="250 750" opacity="0.09"',
    "paper trail stroke",
) if 'stroke="#C4452F" stroke-width="5.2"' in svg else svg

# The trail/sweep colors change with theme. Normalize their widths independently
# of color so Paper, Nord and Cyber keep the same ECG geometry.
svg, trail_width_count = re.subn(
    r'(class="gp-trail"[\s\S]*?stroke="[^"]+" stroke-width=")5\.2(" stroke-linecap="round"[\s\S]*?opacity=")0\.11(")',
    r'\g<1>4.4\g<2>0.09\g<3>',
    svg,
    count=1,
)
if trail_width_count == 0 and 'class="gp-trail"' in svg and 'stroke-width="4.4"' not in svg:
    fail("could not normalize ECG trail width")
svg, sweep_width_count = re.subn(
    r'(class="gp-sweep"[\s\S]*?stroke="[^"]+" stroke-width=")2\.6(" stroke-linecap="round")',
    r'\g<1>2.4\g<2>',
    svg,
    count=1,
)
if sweep_width_count != 1:
    fail(f"expected one ECG sweep width target, found {sweep_width_count}")

# Expand each QRS from 12 to 18 horizontal units. R rises/falls across 8.5 units
# per side instead of four, while S remains only five pixels below baseline.
qrs_re = re.compile(
    r'l2 3 l4 -([0-9]+(?:\.[0-9]+)?) l4 ([0-9]+(?:\.[0-9]+)?) l2 -11'
)


def reshape_qrs(match: re.Match[str]) -> str:
    amplitude = float(match.group(1))
    rise = min(70.0, amplitude * 1.12 + 4.0)
    fall = rise + 3.5  # +1.5 - rise + fall - 5 == 0: exact baseline recovery.
    return f"l0.5 1.5 l8.5 -{fmt(rise)} l8.5 {fmt(fall)} l0.5 -5"


# Remove dead horizontal space before scaling the one trace to x=174..808.
# The endpoint is calculated from the rewritten path, so future data changes do
# not depend on a hard-coded raw span. Baseline translation is exactly +18px.
trace_re = re.compile(
    r'(<path(?: class="gp-(?:trail|sweep)")? d=")(M210 128[^"]+)("[^>]*/>)'
)
trace_count = 0
qrs_counts: list[int] = []
scale_values: list[float] = []


def reshape_trace(match: re.Match[str]) -> str:
    global trace_count
    d = match.group(2)
    gap_count = d.count("h42.4")
    if gap_count != 2:
        fail(f"expected two long ECG gaps per trace, found {gap_count}")
    d = d.replace("h42.4", "h18")
    d = d.replace("h10.4", "h8.4")
    d = re.sub(r"\bh8(?=\s|$)", "h6", d)
    d, qrs_count = qrs_re.subn(reshape_qrs, d)
    if qrs_count < 6:
        fail(f"expected at least six QRS complexes, found {qrs_count}")

    raw_start, raw_end = horizontal_extent(d)
    raw_span = raw_end - raw_start
    if raw_span <= 0:
        fail(f"invalid ECG raw span: {raw_span}")
    target_start = 174.0
    target_end = 808.0
    scale_x = (target_end - target_start) / raw_span
    translate_x = target_start - scale_x * raw_start
    matrix = f"matrix({scale_x:.6f} 0 0 1 {translate_x:.3f} 18)"

    trace_count += 1
    qrs_counts.append(qrs_count)
    scale_values.append(scale_x)
    tail = match.group(3)
    return (
        match.group(1)
        + d
        + f'" transform="{matrix}" vector-effect="non-scaling-stroke"'
        + tail[1:]
    )


svg = trace_re.sub(reshape_trace, svg)
if trace_count != 3:
    fail(f"expected base/trail/sweep ECG paths, found {trace_count}")
if len(set(qrs_counts)) != 1:
    fail(f"ECG layers disagree on QRS count: {qrs_counts}")
if max(scale_values) - min(scale_values) > 1e-9:
    fail(f"ECG layers disagree on horizontal scale: {scale_values}")

# State chrome belongs to the outer right edge, not the wave field.
pill_re = re.compile(
    r'(<rect class="gp-pill-pulse" x=")([0-9.]+)(" y="18" width=")([0-9.]+)(" height="19")'
)
pill = pill_re.search(svg)
if not pill:
    fail("state pill not found")
pill_width = float(pill.group(4))
pill_x = 808.0 - pill_width
svg, count = pill_re.subn(
    lambda m: m.group(1) + fmt(pill_x) + m.group(3) + m.group(4) + m.group(5),
    svg,
    count=1,
)
if count != 1:
    fail(f"expected one state pill, found {count}")

state_text_re = re.compile(r'(<text x=")([0-9.]+)(" y="31" text-anchor="middle")')
svg, count = state_text_re.subn(
    lambda m: m.group(1) + fmt(pill_x + pill_width / 2.0) + m.group(3),
    svg,
    count=1,
)
if count != 1:
    fail(f"expected one state label, found {count}")

svg = replace_once(
    svg,
    'x="804" y="238" text-anchor="end"',
    'x="808" y="236" text-anchor="end"',
    "bottom-right status",
)

path.write_text(svg)
print(
    "Profile Pulse postprocess verified: compact 154px vitals rail; "
    f"ECG x=174..808; {qrs_counts[0]} QRS complexes; "
    f"scale={scale_values[0]:.3f}; level baseline y=146"
)
