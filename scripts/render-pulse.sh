#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${CALLER_REPO:?CALLER_REPO is required}"
: "${MODE:?MODE is required}"
: "${SUBJECT:?SUBJECT is required}"
: "${LABEL:?LABEL is required}"

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

python3 - <<'PY'
from pathlib import Path
import re

card_path = Path('/tmp/github-pulse/lib/card.ts')
card = card_path.read_text()

# ECG: zero net baseline displacement and a deeper S-wave valley.
old_qrs = ' l2 3 l4 ${-a} l4 ${round(a + 8)} l2 -8`; // QRS complex'
new_qrs = ' l2 6 l4 ${-a} l4 ${round(a + 22)} l2 -28`; // QRS complex'
if card.count(old_qrs) != 1:
    raise SystemExit(f'expected one ECG QRS target, found {card.count(old_qrs)}')
card = card.replace(old_qrs, new_qrs, 1)

# Wide+ canvas and larger waveform envelope.
old_layout = '''  wide: {
    w: 830, h: 150, waveX0: 26, waveX1: 804, baseline: 74, ampMax: 30,
    bandTop: 38, bandH: 72, headerY: 26, pillY: 12, footerY: 130, statsX: 150,
  },'''
new_layout = '''  wide: {
    w: 830, h: 260, waveX0: 26, waveX1: 804, baseline: 126, ampMax: 56,
    bandTop: 48, bandH: 150, headerY: 32, pillY: 18, footerY: 240, statsX: 160,
  },'''
if card.count(old_layout) != 1:
    raise SystemExit(f'expected one Wide+ layout target, found {card.count(old_layout)}')
card = card.replace(old_layout, new_layout, 1)

start = card.index('function renderCardAtSize(')
end = card.index('/**\n * Duet card:', start)
body = card[start:end]

# Multi-layer motion stays on the single ECG trace.
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
    raise SystemExit(f'expected one animation target, found {body.count(old_anim)}')
body = body.replace(old_anim, new_anim, 1)

old_trace = '''      ? `<path d="${path}" fill="none" stroke="${strokeRef}" stroke-width="1.6" opacity="0.22"/>
       <path class="gp-sweep" d="${path}" pathLength="1000" fill="none"
             stroke="${strokeRef}" stroke-width="2.2" stroke-linecap="round"
             stroke-dasharray="140 860" ${glowFilter}/>`'''
new_trace = '''      ? `<path d="${path}" fill="none" stroke="${strokeRef}" stroke-width="1.7" opacity="0.20"/>
       <path class="gp-trail" d="${path}" pathLength="1000" fill="none"
             stroke="${strokeRef}" stroke-width="5.2" stroke-linecap="round"
             stroke-dasharray="250 750" opacity="0.11" ${glowFilter}/>
       <path class="gp-sweep" d="${path}" pathLength="1000" fill="none"
             stroke="${strokeRef}" stroke-width="2.6" stroke-linecap="round"
             stroke-dasharray="92 908" ${glowFilter}/>`'''
if body.count(old_trace) != 1:
    raise SystemExit(f'expected one ECG trace target, found {body.count(old_trace)}')
body = body.replace(old_trace, new_trace, 1)

old_grid = '''      }" height="${lay.bandH}" fill="url(#gp-grid)" opacity="0.9"/>`'''
new_grid = '''      }" height="${lay.bandH}" fill="url(#gp-grid)" opacity="0.9" class="gp-grid-pulse"/>`'''
if body.count(old_grid) != 1:
    raise SystemExit(f'expected one grid target, found {body.count(old_grid)}')
body = body.replace(old_grid, new_grid, 1)

old_pill = '''    : `<rect x="${round(pillX)}" y="${lay.pillY}" width="${round(pillW)}" height="19"
        rx="9.5" fill="none" stroke="${stateColor}" opacity="0.85"/>'''
new_pill = '''    : `<rect class="gp-pill-pulse" x="${round(pillX)}" y="${lay.pillY}" width="${round(pillW)}" height="19"
        rx="9.5" fill="none" stroke="${stateColor}" opacity="0.85"/>'''
if body.count(old_pill) != 1:
    raise SystemExit(f'expected one pill target, found {body.count(old_pill)}')
body = body.replace(old_pill, new_pill, 1)

old_trace_slot = '''  ${options.goal ? goalMarkup(pulse, lay, theme, options.goal) : ""}
  ${trace}'''
new_trace_slot = '''  ${options.goal ? goalMarkup(pulse, lay, theme, options.goal) : ""}
  <line x1="${lay.waveX0}" y1="${lay.baseline}" x2="${lay.waveX1}" y2="${lay.baseline}"
        stroke="${theme.grid}" stroke-width="1" opacity="0.25"/>
  ${trace}'''
if body.count(old_trace_slot) != 1:
    raise SystemExit(f'expected one baseline guide target, found {body.count(old_trace_slot)}')
body = body.replace(old_trace_slot, new_trace_slot, 1)

# Reuse upstream's existing BPM cluster as the first metric. Replace only the
# old single-line stats with three additional monitor-style blocks to its right.
stats_pattern = re.compile(
    r'  const statsText =\n'
    r'    lay\.statsX !== null && !options\.hide\.has\("stats"\) && alive\n'
    r'      \? `<text.*?\n'
    r'      : "";\n\n'
    r'  const pill =',
    re.S,
)
new_stats = '''  const isRepoPulse = pulse.login.includes("/");
  const metric2Label = isRepoPulse ? "OPEN PRS" : "PRS / YR";
  const metric2Value = String(pulse.prs);
  const metric3Label = isRepoPulse ? "OPEN ISSUES" : "REVIEWS / YR";
  const metric3Value = String(isRepoPulse ? pulse.issues : pulse.reviews);
  const statsText = !alive || options.hide.has("stats")
    ? ""
    : `<text x="26" y="214" font-family="${MONO}" font-size="9.5"
           letter-spacing="1.4" fill="${theme.muted}">HEART RATE</text>
       <text x="190" y="214" font-family="${MONO}" font-size="9.5"
           letter-spacing="1.4" fill="${theme.muted}">${metric2Label}</text>
       <text x="190" y="240" font-family="${MONO}" font-size="24"
           font-weight="700" fill="${theme.trace}">${esc(metric2Value)}</text>
       <text x="326" y="214" font-family="${MONO}" font-size="9.5"
           letter-spacing="1.4" fill="${theme.muted}">${metric3Label}</text>
       <text x="326" y="240" font-family="${MONO}" font-size="24"
           font-weight="700" fill="${theme.warn}">${esc(metric3Value)}</text>
       <text x="462" y="214" font-family="${MONO}" font-size="9.5"
           letter-spacing="1.4" fill="${theme.muted}">STREAK · TYPE</text>
       <text x="462" y="240" font-family="${MONO}" font-size="24"
           font-weight="700" fill="${theme.text}">${pulse.streak}d<tspan
           fill="${theme.muted}" font-size="16" dx="8">${esc(pulse.bloodType)}</tspan></text>`;

  const pill ='''
body, replaced = stats_pattern.subn(new_stats, body, count=1)
if replaced != 1:
    raise SystemExit(f'expected one left metric block target, replaced {replaced}')

old_bpm_number = 'font-size="22" font-weight="700" fill="${theme.text}">${bpmText}'
new_bpm_number = 'font-size="24" font-weight="700" fill="${theme.trace}">${bpmText}'
if body.count(old_bpm_number) != 1:
    raise SystemExit(f'expected one BPM value style target, found {body.count(old_bpm_number)}')
body = body.replace(old_bpm_number, new_bpm_number, 1)

card = card[:start] + body + card[end:]
card_path.write_text(card)
print('Wide+ patch verified: larger single ECG + four left-aligned monitor metrics')

# Dense repository correctness: paginate default-branch history via GraphQL.
github_path = Path('/tmp/github-pulse/lib/github.ts')
github = github_path.read_text()

replacements = [
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
for i, (old, new) in enumerate(replacements, 1):
    if github.count(old) != 1:
        raise SystemExit(f'expected one GraphQL patch target {i}, found {github.count(old)}')
    github = github.replace(old, new, 1)

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
    if (!res.ok) throw new Error(`GitHub GraphQL ${res.status}`);
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
    recentDates.push(...(pageHistory?.recent.nodes.map((n) => n.committedDate) ?? []));
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
    raise SystemExit(f'expected one fetchRepoViaGraphQL function, replaced {replaced}')

github_path.write_text(github)
print('Repo history pagination verified')
PY

grep -Fq 'l2 -28`; // QRS complex' /tmp/github-pulse/lib/card.ts
grep -Fq 'w: 830, h: 260, waveX0: 26, waveX1: 804, baseline: 126, ampMax: 56' /tmp/github-pulse/lib/card.ts
grep -Fq 'HEART RATE' /tmp/github-pulse/lib/card.ts
grep -Fq 'STREAK · TYPE' /tmp/github-pulse/lib/card.ts
grep -Fq 'class="gp-trail"' /tmp/github-pulse/lib/card.ts
grep -Fq 'history(first: 100, after: $cursor, since: $since)' /tmp/github-pulse/lib/github.ts
grep -Fq 'partial: recentPartial,' /tmp/github-pulse/lib/github.ts

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
