#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${CALLER_REPO:?CALLER_REPO is required}"
: "${MODE:?MODE is required}"
: "${SUBJECT:?SUBJECT is required}"
: "${LABEL:?LABEL is required}"

# DATA_TOKEN is optional. Repo callers can keep using their repository-scoped
# GITHUB_TOKEN for both data and publishing. The Profile caller may supply a
# separate user-scoped read token so private contribution counts are included,
# while GH_TOKEN remains the only credential used to publish pulse-assets.
DATA_TOKEN="${DATA_TOKEN:-$GH_TOKEN}"
DAYS="${DAYS:-14}"
EVENT_SCHEDULE="${EVENT_SCHEDULE:-}"

phase="auto"
target=""
case "$EVENT_SCHEDULE" in
  "55 6 * * *")  phase="paper"; target="07:00" ;;
  "3 7 * * *"|"13 7 * * *") phase="paper" ;;
  "25 18 * * *") phase="nord"; target="18:30" ;;
  "33 18 * * *"|"43 18 * * *") phase="nord" ;;
  "25 22 * * *") phase="cyber"; target="22:30" ;;
  "33 22 * * *"|"43 22 * * *") phase="cyber" ;;
esac

rm -rf /tmp/github-pulse /tmp/caller /tmp/pulse.svg
git clone --quiet --filter=blob:none https://github.com/pouyashahrdami/github-pulse.git /tmp/github-pulse
git -C /tmp/github-pulse checkout --quiet dbc543e0690a68c8be41fc4bc37a2bbd8bacab0b

# Upstream pinned commit's ECG QRS complex has a +3px net Y displacement per
# active beat (`+3 - a + (a + 8) - 8 = +3`), so a busy 14-day window visibly
# drifts downward. Apply one bounded local patch after checkout so each beat
# returns to the same baseline (`... - 11 = 0`). Fail loudly if upstream text
# no longer matches instead of silently patching the wrong code.
python3 - <<'PY'
from pathlib import Path
path = Path('/tmp/github-pulse/lib/card.ts')
text = path.read_text()
old = 'l2 -8`; // QRS complex'
new = 'l2 -11`; // QRS complex'
count = text.count(old)
if count != 1:
    raise SystemExit(f'expected exactly one ECG baseline patch target, found {count}')
path.write_text(text.replace(old, new, 1))
PY

# Prime the small TypeScript runner before a scheduled boundary so the actual
# SVG render can begin immediately after the target time.
npx --yes tsx --version >/dev/null

if [[ -n "$target" ]]; then
  now_epoch="$(date +%s)"
  today="$(TZ=Asia/Kuala_Lumpur date +%F)"
  target_epoch="$(TZ=Asia/Kuala_Lumpur date -d "$today $target" +%s)"
  delay=$((target_epoch - now_epoch))
  if (( delay > 0 && delay <= 600 )); then
    echo "Prewarmed; waiting ${delay}s for $target Asia/Kuala_Lumpur."
    sleep "$delay"
  fi
fi

if [[ "$phase" == "auto" ]]; then
  now="$(TZ=Asia/Kuala_Lumpur date +%H%M)"
  hour="${now:0:2}"
  minute="${now:2:2}"
  total=$((10#$hour * 60 + 10#$minute))
  if (( total >= 420 && total < 1110 )); then
    phase="paper"
  elif (( total >= 1110 && total < 1350 )); then
    phase="nord"
  else
    phase="cyber"
  fi
fi

echo "Resolved theme=$phase at $(TZ=Asia/Kuala_Lumpur date +%H:%M:%S)."

# github-pulse uses GITHUB_TOKEN only for GitHub API reads during rendering.
export GITHUB_TOKEN="$DATA_TOKEN"
export INPUT_OUT="/tmp/pulse.svg"
export INPUT_THEME="$phase"
export INPUT_SIZE="wide"
export INPUT_DAYS="$DAYS"
export INPUT_PARAMS="w=full&tz=8&label=$LABEL"

if [[ "$MODE" == "repo" ]]; then
  export INPUT_REPO="$SUBJECT"
elif [[ "$MODE" == "user" ]]; then
  export INPUT_USERNAME="$SUBJECT"
else
  echo "Unsupported mode: $MODE" >&2
  exit 2
fi

npx --yes tsx /tmp/github-pulse/scripts/generate.ts
test -s /tmp/pulse.svg

# Publishing deliberately uses the caller repository's own GITHUB_TOKEN, never
# the optional Profile data token.
git clone --quiet --filter=blob:none "https://x-access-token:${GH_TOKEN}@github.com/${CALLER_REPO}.git" /tmp/caller
cd /tmp/caller

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

if git ls-remote --exit-code --heads origin pulse-assets >/dev/null 2>&1; then
  git fetch --quiet origin pulse-assets:pulse-assets
  git switch --quiet pulse-assets
else
  git switch --quiet --orphan pulse-assets
  git rm -rf . >/dev/null 2>&1 || true
fi

cp /tmp/pulse.svg pulse.svg
git add pulse.svg

if git diff --cached --quiet; then
  echo "Pulse unchanged."
  exit 0
fi

git commit --quiet -m "chore: refresh dynamic GitHub Pulse"
git push --quiet origin HEAD:pulse-assets
echo "Published $CALLER_REPO pulse-assets/pulse.svg"
