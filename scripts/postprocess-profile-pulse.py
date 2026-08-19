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


path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pulse.svg")
svg = path.read_text()

if 'viewBox="0 0 830 260"' not in svg:
    fail("expected 830x260 Wide+ SVG")

# Profile-only composition: keep the account heading at the global top-left,
# but turn the metrics into a genuinely narrow, symmetric monitor rail.
svg = replace_once(svg, 'x="26" y="32"', 'x="22" y="30"', "header")

rail_positions = [
    ('x="26" y="72"', 'x="77" y="64" text-anchor="middle"', "heart-rate label"),
    ('x="26" y="98"', 'x="32" y="89"', "heart icon"),
    ('x="48" y="98"', 'x="56" y="89"', "heart-rate value"),
    ('x="26" y="120"', 'x="77" y="108" text-anchor="middle"', "merges label"),
    ('x="26" y="146"', 'x="77" y="133" text-anchor="middle"', "merges value"),
    ('x="26" y="168"', 'x="77" y="152" text-anchor="middle"', "reviews label"),
    ('x="26" y="194"', 'x="77" y="177" text-anchor="middle"', "reviews value"),
    ('x="26" y="216"', 'x="77" y="196" text-anchor="middle"', "streak label"),
    ('x="26" y="242"', 'x="77" y="221" text-anchor="middle"', "streak value"),
]
for old, new, label in rail_positions:
    svg = replace_once(svg, old, new, label)

# Reclaim more width for the ECG and vertically fill the monitor field.
# Baseline remains mathematically level; only its fixed y position changes.
svg = replace_once(
    svg,
    'x="200" y="48" width="614" height="160"',
    'x="150" y="42" width="664" height="184"',
    "ECG grid",
)
svg = replace_once(
    svg,
    'x1="190" y1="48" x2="190" y2="244"',
    'x1="142" y1="42" x2="142" y2="226"',
    "rail divider",
)
svg = replace_once(
    svg,
    'x1="210" y1="128" x2="804" y2="128"',
    'x1="158" y1="150" x2="808" y2="150"',
    "level baseline",
)

# The whole ECG must remain legible at rest. Motion is an accent travelling on
# one primary trace, not two bright fragments floating over a nearly invisible line.
svg = replace_once(
    svg,
    '<feGaussianBlur stdDeviation="2.6" result="b"/>',
    '<feGaussianBlur stdDeviation="1.8" result="b"/>',
    "ECG glow blur",
)
svg, base_count = re.subn(
    r'(fill="none" stroke="[^"]+" stroke-width=")1\.7(" opacity=")0\.20(")',
    r'\g<1>1.8\g<2>0.34\g<3>',
    svg,
    count=1,
)
if base_count != 1:
    fail(f"expected one resting ECG stroke, found {base_count}")

svg, trail_count = re.subn(
    r'(class="gp-trail"[\s\S]*?stroke="[^"]+" stroke-width=")5\.2(" stroke-linecap="round"\s+stroke-dasharray=")250 750(" opacity=")0\.11(")',
    r'\g<1>4.2\g<2>170 830\g<3>0.08\g<4>',
    svg,
    count=1,
)
if trail_count != 1:
    fail(f"expected one ECG trail style target, found {trail_count}")

svg, sweep_count = re.subn(
    r'(class="gp-sweep"[\s\S]*?stroke="[^"]+" stroke-width=")2\.6(" stroke-linecap="round"\s+stroke-dasharray=")92 908(")',
    r'\g<1>2.7\g<2>170 830\g<3>',
    svg,
    count=1,
)
if sweep_count != 1:
    fail(f"expected one ECG sweep style target, found {sweep_count}")

# Read the activity amplitudes from the renderer, but rebuild the geometry as an
# actual monitor-style P-QRS-T rhythm. The largest activity peak gets a dominant
# R wave; mid-level activity is deliberately compressed; S stays shallow.
source_qrs_re = re.compile(
    r'l2 3 l4 -([0-9]+(?:\.[0-9]+)?) l4 [0-9]+(?:\.[0-9]+)? l2 -11'
)
trace_re = re.compile(
    r'(<path(?: class="gp-(?:trail|sweep)")? d=")(M210 128[^"]+)("[^>]*/>)'
)

TARGET_X0 = 158.0
TARGET_X1 = 808.0
BASELINE = 150.0


def build_monitor_path(amplitudes: list[float]) -> str:
    if not amplitudes:
        fail("ECG contained no activity amplitudes")

    peak = max(amplitudes)
    if peak <= 0:
        peak = 1.0

    slot = (TARGET_X1 - TARGET_X0) / len(amplitudes)
    # P(7) + PR(3) + Q(2) + R-up(7.5) + R/S-down(10.5)
    # + recovery(2.5) + ST(3.5) + T(10) = 46px. Remaining width is split
    # symmetrically before and after each beat, so no large dead zones remain.
    morphology_width = 46.0
    idle = slot - morphology_width
    if idle < 1.0:
        fail(f"ECG too dense for monitor morphology: slot={slot:.3f}")
    lead = idle / 2.0
    tail = idle - lead

    parts = [f"M{fmt(TARGET_X0)} {fmt(BASELINE)}"]
    for amplitude in amplitudes:
        normalized = max(0.0, min(1.0, amplitude / peak))
        # Convex mapping separates the true dominant R peaks from ordinary
        # activity instead of turning every busy day into a tall triangle.
        rise = 9.0 + 67.0 * (normalized ** 1.7)
        t_control = 5.5 + 3.0 * normalized

        parts.extend(
            [
                f"h{fmt(lead)}",
                "q3.5 -2.7 7 0",          # P wave
                "h3",                     # PR segment
                "l2 2.4",                 # small Q notch
                f"l7.5 -{fmt(rise + 2.4)}",  # broad sloped R ascent
                f"l10.5 {fmt(rise + 4.8)}",  # slower descent to shallow S
                "l2.5 -4.8",              # exact recovery to baseline
                "h3.5",                   # ST segment
                f"q5 -{fmt(t_control)} 10 0", # visible but subordinate T wave
                f"h{fmt(tail)}",
            ]
        )

    # Snap the final baseline to the exact right edge despite decimal rounding.
    parts.append(f"H{fmt(TARGET_X1)}")
    return " ".join(parts)


trace_count = 0
amplitude_sets: list[list[float]] = []


def reshape_trace(match: re.Match[str]) -> str:
    global trace_count
    source_d = match.group(2)
    amplitudes = [float(value) for value in source_qrs_re.findall(source_d)]
    if len(amplitudes) < 6:
        fail(f"expected at least six ECG beats, found {len(amplitudes)}")
    amplitude_sets.append(amplitudes)
    trace_count += 1
    return match.group(1) + build_monitor_path(amplitudes) + match.group(3)


svg = trace_re.sub(reshape_trace, svg)
if trace_count != 3:
    fail(f"expected base/trail/sweep ECG paths, found {trace_count}")
if not all(values == amplitude_sets[0] for values in amplitude_sets[1:]):
    fail("ECG layers disagree on source activity amplitudes")

# State chrome stays pinned to the outer card edge.
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
    'x="808" y="238" text-anchor="end"',
    "bottom-right status",
)

path.write_text(svg)
print(
    "Profile Pulse postprocess verified: centered 142px vitals rail; "
    f"monitor ECG x={fmt(TARGET_X0)}..{fmt(TARGET_X1)}; "
    f"{len(amplitude_sets[0])} P-QRS-T beats; level baseline y={fmt(BASELINE)}"
)
