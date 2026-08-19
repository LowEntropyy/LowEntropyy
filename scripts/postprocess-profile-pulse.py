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

# GitHub already provides the Profile README shell above the card. Keep the card
# itself focused on one full-width ECG plus a compact bottom vitals strip.
svg, header_count = re.subn(
    r'\s*<text x="26" y="32"[\s\S]*?</text>\n',
    '\n',
    svg,
    count=1,
)
if header_count != 1:
    fail(f"expected one in-card account heading, found {header_count}")

# Keep exactly one small heartbeat accent inside the HEART RATE module. Reuse
# the renderer's theme-aware fill and animation hook, but shrink and relocate it
# so it never becomes a second visual center or disturbs the four-column strip.
heart_re = re.compile(
    r'<text class="gp-heart" x="26" y="98"(?P<attrs>[\s\S]*?)font-size="18"(?P<tail>[\s\S]*?)>♥</text>'
)
heart_match = heart_re.search(svg)
if not heart_match:
    fail("expected one renderer heart glyph")
svg, heart_count = heart_re.subn(
    lambda m: (
        '<text class="gp-heart" x="22" y="222"'
        + m.group('attrs')
        + 'font-size="11.5"'
        + m.group('tail')
        + '>♥</text>'
    ),
    svg,
    count=1,
)
if heart_count != 1:
    fail(f"expected one renderer heart glyph, found {heart_count}")

# Slow the accent to a calm UI thump instead of matching a literal 180 bpm.
# The displayed BPM remains data; the icon animation is only a subtle sign of life.
svg, heart_css_count = re.subn(
    r'(\.gp-heart\{animation:gp-thump )[0-9.]+(s ease-in-out infinite;transform-origin:center;transform-box:fill-box\})',
    r'\g<1>1.35\g<2>',
    svg,
    count=1,
)
if heart_css_count != 1:
    fail(f"expected one gp-heart CSS rule, found {heart_css_count}")
svg, thump_css_count = re.subn(
    r'@keyframes gp-thump\{0%,100%\{transform:scale\(1\)\}15%\{transform:scale\(1\.32\)\}30%\{transform:scale\(1\)\}\}',
    '@keyframes gp-thump{0%,100%{transform:scale(1)}20%{transform:scale(1.12)}40%{transform:scale(1)}}',
    svg,
    count=1,
)
if thump_css_count != 1:
    fail(f"expected one gp-thump keyframe, found {thump_css_count}")

# Four equal bottom modules. ECG owns the main field; metrics become one quiet
# supporting strip. Only HEART RATE shifts 14px right on its label row to make
# room for the small heartbeat icon; its value axis remains aligned at x=22.
strip_positions = [
    ('x="26" y="72"', 'x="36" y="222"', "heart-rate label"),
    ('x="48" y="98"', 'x="22" y="246"', "heart-rate value"),
    ('x="26" y="120"', 'x="219" y="222"', "merges label"),
    ('x="26" y="146"', 'x="219" y="246"', "merges value"),
    ('x="26" y="168"', 'x="415" y="222"', "reviews label"),
    ('x="26" y="194"', 'x="415" y="246"', "reviews value"),
    ('x="26" y="216"', 'x="612" y="222"', "streak label"),
    ('x="26" y="242"', 'x="612" y="246"', "streak value"),
]
for old, new, label in strip_positions:
    svg = replace_once(svg, old, new, label)

# Full-width ECG field. The old left-rail divider becomes a horizontal separator
# above the bottom strip. Baseline remains mathematically level.
svg = replace_once(
    svg,
    'x="200" y="48" width="614" height="160"',
    'x="22" y="42" width="786" height="148"',
    "ECG grid",
)
svg = replace_once(
    svg,
    'x1="190" y1="48" x2="190" y2="244"',
    'x1="22" y1="207" x2="808" y2="207"',
    "bottom strip divider",
)
svg = replace_once(
    svg,
    'x1="210" y1="128" x2="804" y2="128"',
    'x1="22" y1="126" x2="808" y2="126"',
    "level baseline",
)

# Keep the full ECG clearly present at rest. The animated segment is only a
# travelling emphasis on the same trace, never a second competing track.
svg = replace_once(
    svg,
    '<feGaussianBlur stdDeviation="2.6" result="b"/>',
    '<feGaussianBlur stdDeviation="1.7" result="b"/>',
    "ECG glow blur",
)
svg, base_count = re.subn(
    r'(fill="none" stroke="[^"]+" stroke-width=")1\.7(" opacity=")0\.20(")',
    r'\g<1>1.8\g<2>0.40\g<3>',
    svg,
    count=1,
)
if base_count != 1:
    fail(f"expected one resting ECG stroke, found {base_count}")

svg, trail_count = re.subn(
    r'(class="gp-trail"[\s\S]*?stroke="[^"]+" stroke-width=")5\.2(" stroke-linecap="round"\s+stroke-dasharray=")250 750(" opacity=")0\.11(")',
    r'\g<1>4.0\g<2>170 830\g<3>0.07\g<4>',
    svg,
    count=1,
)
if trail_count != 1:
    fail(f"expected one ECG trail style target, found {trail_count}")

svg, sweep_count = re.subn(
    r'(class="gp-sweep"[\s\S]*?stroke="[^"]+" stroke-width=")2\.6(" stroke-linecap="round"\s+stroke-dasharray=")92 908(")',
    r'\g<1>2.6\g<2>170 830\g<3>',
    svg,
    count=1,
)
if sweep_count != 1:
    fail(f"expected one ECG sweep style target, found {sweep_count}")

# Read activity amplitudes from the renderer and rebuild them as a P-QRS-T
# monitor rhythm. Data controls R-wave strength; one dominant peak is preserved
# while busy periods are prevented from becoming a forest of equal triangles.
source_qrs_re = re.compile(
    r'l2 3 l4 -([0-9]+(?:\.[0-9]+)?) l4 [0-9]+(?:\.[0-9]+)? l2 -11'
)
trace_re = re.compile(
    r'(<path(?: class="gp-(?:trail|sweep)")? d=")(M210 128[^"]+)("[^>]*/>)'
)

TARGET_X0 = 22.0
TARGET_X1 = 808.0
BASELINE = 126.0


def build_monitor_path(amplitudes: list[float]) -> str:
    if not amplitudes:
        fail("ECG contained no activity amplitudes")

    peak = max(amplitudes)
    if peak <= 0:
        peak = 1.0
    dominant_index = amplitudes.index(max(amplitudes))

    slot = (TARGET_X1 - TARGET_X0) / len(amplitudes)
    morphology_width = 50.0
    idle = slot - morphology_width
    if idle < 1.0:
        fail(f"ECG too dense for monitor morphology: slot={slot:.3f}")
    lead = idle / 2.0
    tail = idle - lead

    parts = [f"M{fmt(TARGET_X0)} {fmt(BASELINE)}"]
    for index, amplitude in enumerate(amplitudes):
        normalized = max(0.0, min(1.0, amplitude / peak))

        if index == dominant_index:
            rise = 72.0
        else:
            rise = min(46.0, 10.0 + 62.0 * (normalized ** 2.4))

        t_control = 12.0 + 5.0 * normalized

        parts.extend(
            [
                f"h{fmt(lead)}",
                "q3 -5.5 6 0",
                "h2",
                "l2 4",
                f"l12 -{fmt(rise + 4.0)}",
                f"l14 {fmt(rise + 6.0)}",
                "l3 -6",
                "h3",
                f"q4 -{fmt(t_control)} 8 0",
                f"h{fmt(tail)}",
            ]
        )

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

# State chrome remains pinned to the outer card edge. `beating now` sits at the
# lower-right edge of the ECG field, above the vitals strip.
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
    'x="808" y="198" text-anchor="end"',
    "ECG lower-right status",
)

# Positive guard: exactly one compact heartbeat accent must survive, and its
# subtle thump animation must be present. This prevents both accidental removal
# and regression to the old oversized heart treatment.
if svg.count('♥') != 1:
    fail(f"expected exactly one heartbeat glyph, found {svg.count('♥')}")
if svg.count('class="gp-heart"') != 1:
    fail(f"expected exactly one gp-heart element, found {svg.count('class=\"gp-heart\"')}")
if svg.count('@keyframes gp-thump') != 1:
    fail(f"expected exactly one gp-thump keyframe, found {svg.count('@keyframes gp-thump')}")
if 'font-size="11.5"' not in svg or 'x="22" y="222"' not in svg:
    fail("compact heartbeat accent geometry missing")

path.write_text(svg)
print(
    "Profile Pulse postprocess verified: full-width ECG + four-module bottom vitals strip; "
    f"ECG x={fmt(TARGET_X0)}..{fmt(TARGET_X1)}; "
    f"{len(amplitude_sets[0])} P-QRS-T beats; level baseline y={fmt(BASELINE)}; "
    "one compact animated heartbeat accent"
)
