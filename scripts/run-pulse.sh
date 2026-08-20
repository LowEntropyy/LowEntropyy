#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source_script="$script_dir/render-pulse.sh"
postprocessor="$script_dir/postprocess-pulse.py"
target="/tmp/render-pulse-unified.sh"

python3 - "$source_script" "$target" "$postprocessor" <<'PY'
from pathlib import Path
import shlex
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
postprocessor = sys.argv[3]
text = source.read_text()
needle = 'test -s /tmp/pulse.svg\n'
if text.count(needle) != 1:
    raise SystemExit('expected one pulse SVG verification hook')
command = f'python3 {shlex.quote(postprocessor)} /tmp/pulse.svg "$MODE"\n'
text = text.replace(needle, needle + command, 1)
target.write_text(text)
PY

bash "$target"
