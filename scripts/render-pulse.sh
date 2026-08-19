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

# Apply bounded correctness fixes to the pinned upstream source. All patches
# fail loudly if the expected pinned source shape changes.
python3 - <<'PY'
from pathlib import Path
import re

# 1) ECG QRS baseline: upstream has +3px net Y displacement per active beat.
card_path = Path('/tmp/github-pulse/lib/card.ts')
card = card_path.read_text()
old = 'l2 -8`; // QRS complex'
new = 'l2 -11`; // QRS complex'
count = card.count(old)
if count != 1:
    raise SystemExit(f'expected exactly one ECG baseline patch target, found {count}')
card = card.replace(old, new, 1)
if card.count(new) != 1 or old in card:
    raise SystemExit('ECG baseline patch verification failed')
card_path.write_text(card)
print('ECG baseline patch verified: QRS net Y displacement = 0')

# 2) Busy repo history: upstream requests only the first 100 recent commit
# nodes. Paginate that GraphQL history connection with endCursor so dense
# repositories keep a complete recent window without switching data sources.
github_path = Path('/tmp/github-pulse/lib/github.ts')
github = github_path.read_text()

literal_replacements = [
    (
        'query ($owner: String!, $name: String!, $since: GitTimestamp!, $sinceYear: GitTimestamp!) {',
        'query ($owner: String!, $name: String!, $since: GitTimestamp!, $sinceYear: GitTimestamp!, $cursor: String) {',
    ),
    (
        '          recent: history(first: 100, since: $since) {',
        '          recent: history(first: 100, after: $cursor, since: $since) {',
    ),
    (
        '            totalCount\n            nodes { committedDate }',
        '            totalCount\n            pageInfo { hasNextPage endCursor }\n            nodes { committedDate }',
    ),
    (
        '          recent: { totalCount: number; nodes: { committedDate: string }[] };',
        '          recent: {\n'
        '            totalCount: number;\n'
        '            pageInfo: { hasNextPage: boolean; endCursor: string | null };\n'
        '            nodes: { committedDate: string }[];\n'
        '          };',
    ),
]
for i, (old_text, new_text) in enumerate(literal_replacements, start=1):
    count = github.count(old_text)
    if count != 1:
        raise SystemExit(f'expected exactly one GraphQL pagination patch target {i}, found {count}')
    github = github.replace(old_text, new_text, 1)

function_pattern = re.compile(
    r'async function fetchRepoViaGraphQL\(\n'
    r'  owner: string,\n'
    r'  repo: string,\n'
    r'\): Promise<GithubData> \{.*?\n\}\n\ninterface RestRepoMeta',
    re.S,
)
new_function = '''async function fetchRepoViaGraphQL(
  owner: string,
  repo: string,
): Promise<GithubData> {
  const now = Date.now();
  const since = new Date(now - REPO_WINDOW_DAYS * 86_400_000).toISOString();
  const sinceYear = new Date(now - 365 * 86_400_000).toISOString();
  let cursor: string | null = null;
  let repoData: NonNullable<RepoGraphQLResponse["data"]>["repository"] = null;
  const recentDates: string[] = [];
  let recentPartial = false;

  for (let page = 1; page <= 100; page++) {
    const res = await fetch(`${API}/graphql`, {
      method: "POST",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({
        query: REPO_GRAPHQL_QUERY,
        variables: { owner, name: repo, since, sinceYear, cursor },
      }),
      next: { revalidate: REVALIDATE },
    });
    if (!res.ok) {
      throw new Error(`GitHub GraphQL ${res.status}`);
    }
    const json = (await res.json()) as RepoGraphQLResponse;
    const pageRepo = json.data?.repository;
    if (!pageRepo) {
      if (json.errors?.some((e) => e.type === "NOT_FOUND")) {
        throw new UserNotFoundError(`${owner}/${repo}`);
      }
      throw new Error(json.errors?.[0]?.message ?? "GraphQL returned no repository");
    }

    if (!repoData) repoData = pageRepo;
    const pageHistory = pageRepo.defaultBranchRef?.target;
    recentDates.push(
      ...(pageHistory?.recent.nodes.map((n) => n.committedDate) ?? []),
    );

    const pageInfo = pageHistory?.recent.pageInfo;
    if (!pageInfo?.hasNextPage) break;
    if (!pageInfo.endCursor || page === 100) {
      recentPartial = true;
      break;
    }
    cursor = pageInfo.endCursor;
  }

  const r = repoData;
  if (!r) throw new Error("GraphQL returned no repository");
  const history = r.defaultBranchRef?.target;
  return {
    login: `${owner}/${r.name}`,
    name: r.name,
    days: daysFromCommitDates(recentDates),
    totalContributions: history?.year.totalCount ?? 0,
    topLanguages: r.primaryLanguage ? [{ name: r.primaryLanguage.name, pct: 100 }] : [],
    stars: r.stargazerCount,
    followers: 0,
    prs: r.pullRequests.totalCount,
    issues: r.issues.totalCount,
    reviews: 0,
    partial: recentPartial,
  };
}

interface RestRepoMeta'''
github, replaced = function_pattern.subn(new_function, github, count=1)
if replaced != 1:
    raise SystemExit(f'expected exactly one fetchRepoViaGraphQL function, replaced {replaced}')

checks = [
    '$cursor: String',
    'history(first: 100, after: $cursor, since: $since)',
    'pageInfo { hasNextPage endCursor }',
    'let cursor: string | null = null;',
    'recentDates.push(',
    'partial: recentPartial,',
]
for check in checks:
    if check not in github:
        raise SystemExit(f'GraphQL pagination verification missing: {check}')

github_path.write_text(github)
print('Repo history pagination patch verified: GraphQL cursor paging enabled')
PY

# 3) Wide+ presentation: keep one full-width ECG and the original left-side
# data hierarchy, but use the 830x260 canvas. Extra motion stays on the same
# ECG trace (soft trail + bright sweep) with subtle grid/state breathing.
python3 - <<'PY'
from pathlib import Path

path = Path('/tmp/github-pulse/lib/card.ts')
text = path.read_text()

old_layout = '''  wide: {
    w: 830, h: 150, waveX0: 26, waveX1: 804, baseline: 74, ampMax: 30,
    bandTop: 38, bandH: 72, headerY: 26, pillY: 12, footerY: 130, statsX: 150,
  },'''
new_layout = '''  wide: {
    w: 830, h: 260, waveX0: 26, waveX1: 804, baseline: 132, ampMax: 40,
    bandTop: 54, bandH: 150, headerY: 32, pillY: 18, footerY: 238, statsX: 160,
  },'''
if text.count(old_layout) != 1:
    raise SystemExit(f'expected exactly one Wide+ layout target, found {text.count(old_layout)}')
text = text.replace(old_layout, new_layout, 1)

start = text.index('function renderCardAtSize(')
end = text.index('/**\n * Duet card:', start)
body = text[start:end]

old_anim = '''      ? `.gp-sweep{animation:gp-sweep ${round(sweepDur)}s linear infinite}
       .gp-heart{animation:gp-thump ${round(period)}s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
       .gp-dot{animation:gp-blink ${dotPeriod(pulse, options)}s ease-in-out infinite}
       @keyframes gp-sweep{from{stroke-dashoffset:1000}to{stroke-dashoffset:0}}
       @keyframes gp-thump{0%,100%{transform:scale(1)}15%{transform:scale(1.32)}30%{transform:scale(1)}}
       @keyframes gp-blink{50%{opacity:.25}}${options.wave === "bars" ? EQ_CSS(options.speed) : ""}`'''
new_anim = '''      ? `.gp-trail{animation:gp-sweep ${round(sweepDur)}s linear infinite}
       .gp-sweep{animation:gp-sweep ${round(sweepDur)}s linear infinite}
       .gp-grid-pulse{animation:gp-grid-breathe ${round(Math.max(5, sweepDur * 1.8))}s ease-in-out infinite}
       .gp-pill-pulse{animation:gp-pill-breathe 4.8s ease-in-out infinite}
       .gp-heart{animation:gp-thump ${round(period)}s ease-in-out infinite;transform-origin:center;transform-box:fill-box}
       .gp-dot{animation:gp-blink ${dotPeriod(pulse, options)}s ease-in-out infinite}
       @keyframes gp-sweep{from{stroke-dashoffset:1000}to{stroke-dashoffset:0}}
       @keyframes gp-grid-breathe{0%,100%{opacity:.72}50%{opacity:.96}}
       @keyframes gp-pill-breathe{0%,100%{opacity:.72}50%{opacity:1}}
       @keyframes gp-thump{0%,100%{transform:scale(1)}15%{transform:scale(1.32)}30%{transform:scale(1)}}
       @keyframes gp-blink{50%{opacity:.25}}${options.wave === "bars" ? EQ_CSS(options.speed) : ""}`'''
if body.count(old_anim) != 1:
    raise SystemExit(f'expected exactly one Wide+ animation target, found {body.count(old_anim)}')
body = body.replace(old_anim, new_anim, 1)

old_trace = '''      ? `<path d="${path}" fill="none" stroke="${strokeRef}" stroke-width="1.6" opacity="0.22"/>
       <path class="gp-sweep" d="${path}" pathLength="1000" fill="none"
             stroke="${strokeRef}" stroke-width="2.2" stroke-linecap="round"
             stroke-dasharray="140 860" ${glowFilter}/>`'''
new_trace = '''      ? `<path d="${path}" fill="none" stroke="${strokeRef}" stroke-width="1.6" opacity="0.18"/>
       <path class="gp-trail" d="${path}" pathLength="1000" fill="none"
             stroke="${strokeRef}" stroke-width="4.8" stroke-linecap="round"
             stroke-dasharray="240 760" opacity="0.10" ${glowFilter}/>
       <path class="gp-sweep" d="${path}" pathLength="1000" fill="none"
             stroke="${strokeRef}" stroke-width="2.4" stroke-linecap="round"
             stroke-dasharray="88 912" ${glowFilter}/>`'''
if body.count(old_trace) != 1:
    raise SystemExit(f'expected exactly one Wide+ trace target, found {body.count(old_trace)}')
body = body.replace(old_trace, new_trace, 1)

old_grid = '''      }" height="${lay.bandH}" fill="url(#gp-grid)" opacity="0.9"/>`'''
new_grid = '''      }" height="${lay.bandH}" fill="url(#gp-grid)" opacity="0.9" class="gp-grid-pulse"/>`'''
if body.count(old_grid) != 1:
    raise SystemExit(f'expected exactly one Wide+ grid target, found {body.count(old_grid)}')
body = body.replace(old_grid, new_grid, 1)

old_pill_rect = '''    : `<rect x="${round(pillX)}" y="${lay.pillY}" width="${round(pillW)}" height="19"
        rx="9.5" fill="none" stroke="${stateColor}" opacity="0.85"/>'''
new_pill_rect = '''    : `<rect class="gp-pill-pulse" x="${round(pillX)}" y="${lay.pillY}" width="${round(pillW)}" height="19"
        rx="9.5" fill="none" stroke="${stateColor}" opacity="0.85"/>'''
if body.count(old_pill_rect) != 1:
    raise SystemExit(f'expected exactly one Wide+ pill target, found {body.count(old_pill_rect)}')
body = body.replace(old_pill_rect, new_pill_rect, 1)

old_trace_slot = '''  ${options.goal ? goalMarkup(pulse, lay, theme, options.goal) : ""}
  ${trace}'''
new_trace_slot = '''  ${options.goal ? goalMarkup(pulse, lay, theme, options.goal) : ""}
  <line x1="${lay.waveX0}" y1="${lay.baseline}" x2="${lay.waveX1}" y2="${lay.baseline}"
        stroke="${theme.grid}" stroke-width="1" opacity="0.28"/>
  ${trace}'''
if body.count(old_trace_slot) != 1:
    raise SystemExit(f'expected exactly one Wide+ baseline-guide target, found {body.count(old_trace_slot)}')
body = body.replace(old_trace_slot, new_trace_slot, 1)

body = body.replace('font-size="10.5" fill="${theme.muted}">${esc(statsLeft)}</text>',
                    'font-size="11.5" fill="${theme.muted}">${esc(statsLeft)}</text>', 1)

text = text[:start] + body + text[end:]
path.write_text(text)
print('Wide+ visual patch verified: 830x260 single ECG, left stats, layered same-trace motion')
PY

grep -Fq 'l2 -11`; // QRS complex' /tmp/github-pulse/lib/card.ts
grep -Fq 'history(first: 100, after: $cursor, since: $since)' /tmp/github-pulse/lib/github.ts
grep -Fq 'partial: recentPartial,' /tmp/github-pulse/lib/github.ts
grep -Fq 'w: 830, h: 260, waveX0: 26, waveX1: 804, baseline: 132' /tmp/github-pulse/lib/card.ts
grep -Fq 'class="gp-trail"' /tmp/github-pulse/lib/card.ts

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
