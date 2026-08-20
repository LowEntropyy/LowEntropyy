#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import os
import re
import sys


def fail(message: str) -> None:
    raise SystemExit(f"pulse postprocess: {message}")


def fmt(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        fail(f"expected one {label} target, found {count}")
    return text.replace(old, new, 1)


TARGET_X0 = 22.0
TARGET_X1 = 808.0
BASELINE = 126.0
MORPHOLOGY_WIDTH = 50.0


def morphology_parts(rise: float, t_control: float) -> list[str]:
    return [
        "q3 -5.5 6 0",
        "h2",
        "l2 4",
        f"l12 -{fmt(rise + 4.0)}",
        f"l14 {fmt(rise + 6.0)}",
        "l3 -6",
        "h3",
        f"q4 -{fmt(t_control)} 8 0",
    ]


def rise_for(amplitude: float, peak: float, dominant: bool) -> tuple[float, float]:
    normalized = max(0.0, min(1.0, amplitude / (peak or 1.0)))
    rise = 72.0 if dominant else min(46.0, 10.0 + 62.0 * (normalized ** 2.4))
    t_control = 12.0 + 5.0 * normalized
    return rise, t_control


def build_user_path(amplitudes: list[float]) -> str:
    if not amplitudes:
        return f"M{fmt(TARGET_X0)} {fmt(BASELINE)} H{fmt(TARGET_X1)}"

    peak = max(amplitudes) or 1.0
    dominant_index = amplitudes.index(max(amplitudes))
    slot = (TARGET_X1 - TARGET_X0) / len(amplitudes)
    idle = slot - MORPHOLOGY_WIDTH
    if idle < 1.0:
        fail(f"user ECG too dense for monitor morphology: slot={slot:.3f}")

    lead = idle / 2.0
    tail = idle - lead
    parts = [f"M{fmt(TARGET_X0)} {fmt(BASELINE)}"]
    for index, amplitude in enumerate(amplitudes):
        rise, t_control = rise_for(amplitude, peak, index == dominant_index)
        parts.append(f"h{fmt(lead)}")
        parts.extend(morphology_parts(rise, t_control))
        parts.append(f"h{fmt(tail)}")
    parts.append(f"H{fmt(TARGET_X1)}")
    return " ".join(parts)


# Raw Wide+ repo traces contain one day slot per beat-window day. An inactive
# slot is one h<seg>; an active slot is h<lead> + P/QRS/T + h<tail>.
REPO_DAY_RE = re.compile(
    r'(?:'
    r'h(?P<lead>[0-9]+(?:\.[0-9]+)?)\s+'
    r'q3\s+-?[0-9]+(?:\.[0-9]+)?\s+6\s+0\s+'
    r'l2\s+3\s+l4\s+-(?P<amp>[0-9]+(?:\.[0-9]+)?)\s+'
    r'l4\s+[0-9]+(?:\.[0-9]+)?\s+l2\s+-11\s+'
    r'q3\s+-?[0-9]+(?:\.[0-9]+)?\s+6\s+0\s+'
    r'h(?P<tail>[0-9]+(?:\.[0-9]+)?)'
    r'|h(?P<idle>[0-9]+(?:\.[0-9]+)?)'
    r')'
)


def parse_repo_days(source_d: str) -> list[tuple[str, float, float, float]]:
    if re.fullmatch(r'M210 128\s+H804', source_d.strip()):
        return []
    prefix = re.match(r'M210 128\s*', source_d)
    if not prefix:
        fail("repo ECG source did not start at M210 128")
    body = source_d[prefix.end():].strip()
    records: list[tuple[str, float, float, float]] = []
    cursor = 0
    for match in REPO_DAY_RE.finditer(body):
        if body[cursor:match.start()].strip():
            fail(f"unparsed repo ECG fragment: {body[cursor:match.start()].strip()[:80]}")
        if match.group("amp") is not None:
            records.append(
                (
                    "active",
                    float(match.group("amp")),
                    float(match.group("lead")),
                    float(match.group("tail")),
                )
            )
        else:
            records.append(("idle", 0.0, float(match.group("idle")), 0.0))
        cursor = match.end()
    if body[cursor:].strip():
        fail(f"unparsed repo ECG tail: {body[cursor:].strip()[:80]}")
    if not records:
        fail("repo ECG contained no day slots")
    return records


def build_repo_path(source_d: str) -> tuple[str, int]:
    records = parse_repo_days(source_d)
    if not records:
        return f"M{fmt(TARGET_X0)} {fmt(BASELINE)} H{fmt(TARGET_X1)}", 0

    amplitudes = [record[1] for record in records if record[0] == "active"]
    if not amplitudes:
        return f"M{fmt(TARGET_X0)} {fmt(BASELINE)} H{fmt(TARGET_X1)}", 0
    peak = max(amplitudes) or 1.0
    dominant_amplitude_index = amplitudes.index(max(amplitudes))
    active_index = 0
    slot = (TARGET_X1 - TARGET_X0) / len(records)
    idle_budget = slot - MORPHOLOGY_WIDTH
    if idle_budget < 1.0:
        fail(f"repo ECG too dense for monitor morphology: slot={slot:.3f}")

    parts = [f"M{fmt(TARGET_X0)} {fmt(BASELINE)}"]
    for kind, amplitude, source_lead, source_tail in records:
        if kind == "idle":
            parts.append(f"h{fmt(slot)}")
            continue

        source_idle = source_lead + source_tail
        ratio = source_lead / source_idle if source_idle > 0 else 0.5
        lead = idle_budget * max(0.0, min(1.0, ratio))
        tail = idle_budget - lead
        rise, t_control = rise_for(
            amplitude,
            peak,
            active_index == dominant_amplitude_index,
        )
        active_index += 1
        parts.append(f"h{fmt(lead)}")
        parts.extend(morphology_parts(rise, t_control))
        parts.append(f"h{fmt(tail)}")

    parts.append(f"H{fmt(TARGET_X1)}")
    return " ".join(parts), len(amplitudes)


path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pulse.svg")
mode = (sys.argv[2] if len(sys.argv) > 2 else os.environ.get("MODE", "")).strip().lower()
if mode not in {"user", "repo"}:
    fail(f"unsupported mode: {mode!r}")

svg = path.read_text()
if 'viewBox="0 0 830 260"' not in svg:
    fail("expected 830x260 Wide+ SVG")

# Profile does not repeat the account name inside the card; repo cards retain the
# repository name at the global top-left.
if mode == "user":
    svg, header_count = re.subn(
        r'\s*<text x="26" y="32"[\s\S]*?</text>\n',
        '\n',
        svg,
        count=1,
    )
    if header_count != 1:
        fail(f"expected one in-card account heading, found {header_count}")

bpm_match = re.search(r'<title[^>]*>.*?—\s*([0-9]+)\s*bpm', svg)
if not bpm_match:
    fail("BPM not found in SVG title")
bpm = max(0.0, float(bpm_match.group(1)))
heart_duration = max(0.62, min(1.65, 120.0 / max(1.0, bpm)))

has_stats = "HEART RATE" in svg
if has_stats:
    heart_re = re.compile(
        r'<text class="gp-heart" x="26" y="98"(?P<attrs>[\s\S]*?)font-size="18"(?P<tail>[\s\S]*?)>♥</text>'
    )
    if not heart_re.search(svg):
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

    strip_positions = [
        ('x="26" y="72"', 'x="36" y="222"', "heart-rate label"),
        ('x="48" y="98"', 'x="22" y="246"', "heart-rate value"),
        ('x="26" y="120"', 'x="219" y="222"', "metric-2 label"),
        ('x="26" y="146"', 'x="219" y="246"', "metric-2 value"),
        ('x="26" y="168"', 'x="415" y="222"', "metric-3 label"),
        ('x="26" y="194"', 'x="415" y="246"', "metric-3 value"),
        ('x="26" y="216"', 'x="612" y="222"', "streak label"),
        ('x="26" y="242"', 'x="612" y="246"', "streak value"),
    ]
    for old, new, label in strip_positions:
        svg = replace_once(svg, old, new, label)
elif bpm != 0:
    fail("non-flatline pulse unexpectedly lacked vitals")

# Heart speed is one shared mapping for Profile and repo cards.
svg, heart_css_count = re.subn(
    r'(\.gp-heart\{animation:gp-thump )[0-9.]+(s ease-in-out infinite;transform-origin:center;transform-box:fill-box\})',
    lambda m: m.group(1) + fmt(heart_duration) + m.group(2),
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

# Shared card geometry.
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

source_qrs_re = re.compile(
    r'l2 3 l4 -([0-9]+(?:\.[0-9]+)?) l4 [0-9]+(?:\.[0-9]+)? l2 -11'
)
trace_re = re.compile(
    r'(<path(?: class="gp-(?:trail|sweep)")? d=")(M210 128[^"]+)("[^>]*/>)'
)
trace_count = 0
source_sets: list[list[float]] = []
repo_active_counts: list[int] = []


def reshape_trace(match: re.Match[str]) -> str:
    global trace_count
    source_d = match.group(2)
    if mode == "user":
        amplitudes = [float(value) for value in source_qrs_re.findall(source_d)]
        new_d = build_user_path(amplitudes)
        source_sets.append(amplitudes)
    else:
        new_d, active_count = build_repo_path(source_d)
        amplitudes = [float(value) for value in source_qrs_re.findall(source_d)]
        source_sets.append(amplitudes)
        repo_active_counts.append(active_count)
    trace_count += 1
    return match.group(1) + new_d + match.group(3)


svg = trace_re.sub(reshape_trace, svg)
if trace_count != 3:
    fail(f"expected base/trail/sweep ECG paths, found {trace_count}")
if not all(values == source_sets[0] for values in source_sets[1:]):
    fail("ECG layers disagree on source activity amplitudes")
if mode == "repo" and len(set(repo_active_counts)) != 1:
    fail("repo ECG layers disagree on active-day count")

# State chrome shared across card types.
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

# Final invariants: no legacy rail geometry and no matrix-stretched ECG.
for forbidden in (
    'x="200" y="48" width="614"',
    'x1="190" y1="48" x2="190" y2="244"',
    'transform="matrix(',
):
    if forbidden in svg:
        fail(f"legacy pulse geometry survived: {forbidden}")
if has_stats:
    if svg.count('♥') != 1 or svg.count('class="gp-heart"') != 1:
        fail("expected exactly one compact heartbeat accent")
    if 'font-size="11.5"' not in svg or 'x="22" y="222"' not in svg:
        fail("compact heartbeat accent geometry missing")

path.write_text(svg)
extra = (
    f" active_days={repo_active_counts[0]}" if mode == "repo" and repo_active_counts else ""
)
print(
    f"Pulse postprocess verified: mode={mode}; full-width ECG + bottom vitals; "
    f"bpm={bpm:g}; heart={fmt(heart_duration)}s; amplitudes={len(source_sets[0])}{extra}"
)
