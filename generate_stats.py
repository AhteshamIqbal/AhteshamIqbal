#!/usr/bin/env python3
"""Generate themed GitHub statistics SVG cards for the profile README.

Runs inside GitHub Actions (see .github/workflows/update-profile.yml) using the
built-in GITHUB_TOKEN. Only real data returned by the GitHub GraphQL API is used.

Outputs (in assets/generated/):
  stats.svg      – contributions, commits, PRs, issues, repos, stars, followers
  languages.svg  – most used languages across public, non-fork repositories
  streak.svg     – total contributions, current streak, longest streak (past year)
  activity.svg   – daily contributions for the last 31 days

Usage:
  python3 generate_stats.py               # fetch live data (needs GITHUB_TOKEN, USERNAME)
  python3 generate_stats.py --placeholder # write "awaiting first run" cards
"""
import datetime as dt
import json
import os
import sys
import urllib.request

OUT_DIR = os.environ.get("OUT_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets", "generated")
BG, PANEL, GREEN, BLUE, PURPLE = "#050505", "#0A0F0B", "#00FF41", "#00BFFF", "#8A2BE2"
TEXT, MUTED, LINE = "#D6E2D8", "#6F8A76", "#1B3A22"
FONT = "'JetBrains Mono','Fira Code',Consolas,'Courier New',monospace"

QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


# ------------------------------------------------------------------ helpers
def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fmt(n):
    return f"{n:,}"


def card(w, h, title, inner, desc):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d">
<title id="t">{esc(title)}</title><desc id="d">{esc(desc)}</desc>
<style>text{{font-family:{FONT}}}.h{{font-size:17px;font-weight:700;fill:{GREEN}}}.l{{font-size:13px;fill:{TEXT}}}.v{{font-size:13px;font-weight:700;fill:{BLUE}}}.m{{font-size:11px;fill:{MUTED}}}
.fade{{animation:f .8s ease-out both}}@keyframes f{{from{{opacity:0}}to{{opacity:1}}}}</style>
<rect x=".75" y=".75" width="{w - 1.5}" height="{h - 1.5}" rx="12" fill="{BG}" stroke="{GREEN}" stroke-opacity=".35" stroke-width="1.5"/>
<text x="24" y="36" class="h">&gt; {esc(title)}</text>
{inner}
</svg>
"""


def write(name, svg):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
        f.write(svg)
    print("wrote", name)


# ------------------------------------------------------------------ data
def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]["user"]


def days_of(user):
    days = [d for w in user["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    today = dt.date.today().isoformat()
    return [d for d in days if d["date"] <= today]


def streaks(days):
    longest = cur = 0
    best = (None, None)
    start = None
    for d in days:
        if d["contributionCount"] > 0:
            if cur == 0:
                start = d["date"]
            cur += 1
            if cur > longest:
                longest, best = cur, (start, d["date"])
        else:
            cur = 0
    # current streak: today may still be empty without breaking the streak
    current, i = 0, len(days) - 1
    if i >= 0 and days[i]["contributionCount"] == 0:
        i -= 1
    cur_start = None
    while i >= 0 and days[i]["contributionCount"] > 0:
        current += 1
        cur_start = days[i]["date"]
        i -= 1
    return current, cur_start, longest, best


def short(date):
    return dt.date.fromisoformat(date).strftime("%d %b %Y") if date else "—"


# ------------------------------------------------------------------ cards
def stats_svg(user):
    repos = user["repositories"]
    cc = user["contributionsCollection"]
    rows = [
        ("Contributions (past year)", cc["contributionCalendar"]["totalContributions"]),
        ("Commits (past year)", cc["totalCommitContributions"]),
        ("Pull requests", user["pullRequests"]["totalCount"]),
        ("Issues opened", user["issues"]["totalCount"]),
        ("Public repositories", repos["totalCount"]),
        ("Stars earned", sum(n["stargazerCount"] for n in repos["nodes"])),
        ("Followers", user["followers"]["totalCount"]),
    ]
    inner = "".join(
        f'<g class="fade" style="animation-delay:{0.1 * i:.1f}s"><text x="24" y="{70 + 24 * i}" class="l"><tspan fill="{GREEN}">$</tspan> {esc(k)}</text>'
        f'<text x="456" y="{70 + 24 * i}" class="v" text-anchor="end">{fmt(v)}</text></g>'
        for i, (k, v) in enumerate(rows)
    )
    inner += f'<text x="24" y="{70 + 24 * len(rows) + 4}" class="m">updated {dt.date.today().strftime("%d %b %Y")} · public data</text>'
    return card(480, 250, "GitHub Stats", inner, "; ".join(f"{k}: {v}" for k, v in rows))


def languages_svg(user):
    totals = {}
    colors = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            totals[n] = totals.get(n, 0) + e["size"]
            colors[n] = e["node"]["color"] or GREEN
    top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    total = sum(v for _, v in top) or 1
    if not top:
        inner = f'<text x="24" y="110" class="l">No public code yet. Languages appear once repositories contain code.</text>'
        return card(480, 250, "Most Used Languages", inner, "No language data yet")
    x, bar = 24, ""
    for name, v in top:
        w = 432 * v / total
        bar += f'<rect x="{x:.1f}" y="58" width="{max(w, 1.5):.1f}" height="10" fill="{colors[name]}"/>'
        x += w
    legend = ""
    for i, (name, v) in enumerate(top):
        cx, cy = 24 + (i % 2) * 220, 104 + (i // 2) * 34
        legend += (f'<g class="fade" style="animation-delay:{0.1 * i:.1f}s"><circle cx="{cx + 6}" cy="{cy - 4}" r="6" fill="{colors[name]}"/>'
                   f'<text x="{cx + 20}" y="{cy}" class="l">{esc(name)}</text><text x="{cx + 200}" y="{cy}" class="v" text-anchor="end">{100 * v / total:.1f}%</text></g>')
    inner = f'<clipPath id="bc"><rect x="24" y="58" width="432" height="10" rx="5"/></clipPath><g clip-path="url(#bc)">{bar}</g>{legend}'
    inner += '<text x="24" y="226" class="m">by code size · public non-fork repositories</text>'
    return card(480, 250, "Most Used Languages", inner, "; ".join(f"{n} {100 * v / total:.1f}%" for n, v in top))


def streak_svg(days):
    total = sum(d["contributionCount"] for d in days)
    current, cs, longest, (ls, le) = streaks(days)
    first = days[0]["date"] if days else None
    cols = [
        ("Total contributions", fmt(total), f"{short(first)} – today", GREEN),
        ("Current streak", f"{current} day{'s' if current != 1 else ''}", f"since {short(cs)}" if current else "start one today", BLUE),
        ("Longest streak", f"{longest} day{'s' if longest != 1 else ''}", f"{short(ls)} – {short(le)}" if longest else "past year", PURPLE),
    ]
    inner = ""
    for i, (label, val, sub, col) in enumerate(cols):
        cx = 160 + i * 320
        inner += (f'<g class="fade" style="animation-delay:{0.15 * i:.2f}s"><text x="{cx}" y="96" text-anchor="middle" style="font-size:30px;font-weight:700;fill:{col}">{esc(val)}</text>'
                  f'<text x="{cx}" y="124" text-anchor="middle" class="l">{esc(label)}</text><text x="{cx}" y="146" text-anchor="middle" class="m">{esc(sub)}</text></g>')
        if i:
            inner += f'<path d="M{cx - 160} 64V150" stroke="{LINE}" stroke-width="1.5"/>'
    return card(960, 180, "Contribution Streak (past year)", inner, "; ".join(f"{a}: {b} ({c})" for a, b, c, _ in cols))


def activity_svg(days):
    last = days[-31:]
    W, H = 960, 300
    x0, x1, y0, y1 = 60, 930, 250, 70
    mx = max([d["contributionCount"] for d in last] + [1])
    mx = -(-mx // 4) * 4  # round up to a multiple of 4 for even axis ticks
    step = (x1 - x0) / max(len(last) - 1, 1)
    pts = [(x0 + i * step, y0 - (y0 - y1) * d["contributionCount"] / mx) for i, d in enumerate(last)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"M{x0},{y0} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L{pts[-1][0]:.1f},{y0} Z" if pts else ""
    grid = ""
    for k in range(5):
        y = y0 - (y0 - y1) * k / 4
        grid += f'<path d="M{x0} {y:.1f}H{x1}" stroke="{LINE}" stroke-dasharray="3 5"/><text x="{x0 - 10}" y="{y + 4:.1f}" class="m" text-anchor="end">{mx * k // 4}</text>'
    labels = "".join(
        f'<text x="{x0 + i * step:.1f}" y="{y0 + 22}" class="m" text-anchor="middle">{dt.date.fromisoformat(d["date"]).strftime("%d %b")}</text>'
        for i, d in enumerate(last) if i % 5 == 0 or i == len(last) - 1)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{BG}" stroke="{GREEN}" stroke-width="1.8"/>' for x, y in pts)
    inner = f"""<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{GREEN}" stop-opacity=".35"/><stop offset="1" stop-color="{GREEN}" stop-opacity="0"/></linearGradient></defs>
{grid}{labels}<path d="{area}" fill="url(#ag)"/>
<polyline points="{line}" fill="none" stroke="{GREEN}" stroke-width="2.2" stroke-linejoin="round" stroke-dasharray="3000" stroke-dashoffset="3000"><animate attributeName="stroke-dashoffset" from="3000" to="0" dur="2.5s" fill="freeze"/></polyline>{dots}"""
    total = sum(d["contributionCount"] for d in last)
    return card(W, H, "Contribution Activity (last 31 days)", inner, f"{total} contributions in the last 31 days; daily values: " + ", ".join(f'{d["date"]}: {d["contributionCount"]}' for d in last))


def placeholder(name, w, h, title):
    inner = (f'<text x="{w / 2}" y="{h / 2 + 6}" text-anchor="middle" class="l">Awaiting first run of the “Update profile” GitHub Action…</text>'
             f'<text x="{w / 2}" y="{h / 2 + 30}" text-anchor="middle" class="m">real data from github.com/AhteshamIqbal appears here automatically</text>')
    write(name, card(w, h, title, inner, "Statistics will appear after the first automated update."))


def main():
    if "--placeholder" in sys.argv:
        placeholder("stats.svg", 480, 250, "GitHub Stats")
        placeholder("languages.svg", 480, 250, "Most Used Languages")
        placeholder("streak.svg", 960, 180, "Contribution Streak (past year)")
        placeholder("activity.svg", 960, 300, "Contribution Activity (last 31 days)")
        placeholder("snake.svg", 960, 180, "Contribution Snake")
        return
    if "--mock" in sys.argv:
        user = json.load(open(sys.argv[sys.argv.index("--mock") + 1]))
    else:
        user = fetch(os.environ["USERNAME"], os.environ["GITHUB_TOKEN"])
    days = days_of(user)
    write("stats.svg", stats_svg(user))
    write("languages.svg", languages_svg(user))
    write("streak.svg", streak_svg(days))
    write("activity.svg", activity_svg(days))


if __name__ == "__main__":
    main()
