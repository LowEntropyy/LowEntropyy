#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_script="$script_dir/render-pulse.sh"
postprocessor="$script_dir/postprocess-pulse.py"
flatline_postprocessor="$script_dir/postprocess-flatline.py"
vitals_alignment="$script_dir/align-pulse-vitals.py"
target="/tmp/render-pulse-unified.sh"

# The profile card is expected to include authenticated/private contribution
# data. Never silently fall back to the per-repository GITHUB_TOKEN in user mode,
# because that can produce a plausible but materially incomplete profile pulse.
if [[ "${MODE:-}" == "user" && -z "${DATA_TOKEN:-}" ]]; then
  echo "DATA_TOKEN is required for user-mode Profile Pulse" >&2
  exit 2
fi

python3 - "$source_script" "$target" "$postprocessor" "$flatline_postprocessor" "$vitals_alignment" <<'PY'
from pathlib import Path
import shlex
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
postprocessor = shlex.quote(sys.argv[3])
flatline_postprocessor = shlex.quote(sys.argv[4])
vitals_alignment = shlex.quote(sys.argv[5])
text = source.read_text()

# Keep the same four-column vitals contract for flatlined cards. The upstream
# renderer normally suppresses stats when alive=false and prints an em dash for
# BPM; our card should instead remain structurally stable and show truthful 0 BPM.
source_edits = (
    (
        '  const statsText = !alive || options.hide.has("stats")\n    ? ""',
        '  const statsText = options.hide.has("stats")\n    ? ""',
        'flatline stats visibility',
    ),
    (
        'font-size="18" fill="${theme.trace}">♥</text>',
        'font-size="18" fill="${alive ? theme.trace : theme.danger}">♥</text>',
        'flatline heart color',
    ),
    (
        'font-weight="700" fill="${theme.trace}">${bpmText}<tspan',
        'font-weight="700" fill="${alive ? theme.trace : theme.danger}">${pulse.bpm}<tspan',
        'flatline bpm value',
    ),
)
for old, new, label in source_edits:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'expected one {label} target, found {count}')
    text = text.replace(old, new, 1)

needle = 'test -s /tmp/pulse.svg\n'
if text.count(needle) != 1:
    raise SystemExit('expected one pulse SVG verification hook')
command = (
    'if grep -qi "flatlined" /tmp/pulse.svg; then\n'
    f'  python3 {flatline_postprocessor} /tmp/pulse.svg "$MODE"\n'
    'else\n'
    f'  python3 {postprocessor} /tmp/pulse.svg "$MODE"\n'
    'fi\n'
    f'python3 {vitals_alignment} /tmp/pulse.svg\n'
)
text = text.replace(needle, needle + command, 1)
target.write_text(text)
PY

bash "$target"
