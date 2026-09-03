#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_script="$script_dir/render-pulse.sh"
postprocessor="$script_dir/postprocess-pulse.py"
flatline_postprocessor="$script_dir/postprocess-flatline.py"
target="/tmp/render-pulse-unified.sh"

# The profile card is expected to include authenticated/private contribution
# data. Never silently fall back to the per-repository GITHUB_TOKEN in user mode,
# because that can produce a plausible but materially incomplete profile pulse.
if [[ "${MODE:-}" == "user" && -z "${DATA_TOKEN:-}" ]]; then
  echo "DATA_TOKEN is required for user-mode Profile Pulse" >&2
  exit 2
fi

python3 - "$source_script" "$target" "$postprocessor" "$flatline_postprocessor" <<'PY'
from pathlib import Path
import shlex
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
postprocessor = shlex.quote(sys.argv[3])
flatline_postprocessor = shlex.quote(sys.argv[4])
text = source.read_text()
needle = 'test -s /tmp/pulse.svg\n'
if text.count(needle) != 1:
    raise SystemExit('expected one pulse SVG verification hook')
command = (
    'if grep -qi "flatlined" /tmp/pulse.svg; then\n'
    f'  python3 {flatline_postprocessor} /tmp/pulse.svg "$MODE"\n'
    'else\n'
    f'  python3 {postprocessor} /tmp/pulse.svg "$MODE"\n'
    'fi\n'
)
text = text.replace(needle, needle + command, 1)
target.write_text(text)
PY

bash "$target"
