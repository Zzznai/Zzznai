"""Render the last year of GitHub contributions as an isometric 3D SVG card."""
import json
import math
import os
import sys
import urllib.request
from datetime import date

LOGIN = os.environ["USERNAME"]
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "profile-3d-contrib/contrib-3d.svg"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount contributionLevel } }
      }
    }
  }
}"""

req = urllib.request.Request(
    "https://api.github.com/graphql",
    data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
    headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    payload = json.load(resp)
if "errors" in payload:
    sys.exit(f"GraphQL error: {payload['errors']}")
cal = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]

cells = []  # (week, weekday, date, count, level)
for w, week in enumerate(cal["weeks"]):
    for d in week["contributionDays"]:
        cells.append((w, d["weekday"], d["date"], d["contributionCount"], d["contributionLevel"]))
days = sorted(cells, key=lambda c: c[2])

# ---- stats ----
total = cal["totalContributions"]
busiest = max(days, key=lambda c: c[3])
active = sum(1 for c in days if c[3] > 0)
streak = best = 0
for c in days:
    streak = streak + 1 if c[3] > 0 else 0
    best = max(best, streak)

# ---- geometry ----
W, H = 700, 495
X0, Y0 = 55, 170          # screen position of week 0 / back row origin
UX, UY = 10.0, 5.6        # one week step (down-right)
VX, VY = 10.0, -5.6       # one weekday step (up-right)
MAX_H = 46
INSET = 0.08

BG = "#0d1117"
EMPTY = "#22262d"
LEVEL = {
    "NONE": EMPTY,
    "FIRST_QUARTILE": "#0e4429",
    "SECOND_QUARTILE": "#006d32",
    "THIRD_QUARTILE": "#26a641",
    "FOURTH_QUARTILE": "#39d353",
}

def shade(hex_color, f):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % (int(r * f), int(g * f), int(b * f))

def pt(u, v, h=0.0):
    return (X0 + u * UX + v * VX, Y0 + u * UY + v * VY - h)

def poly(points, fill):
    p = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polygon points="{p}" fill="{fill}"/>'

max_count = max(c[3] for c in days) or 1
tiles, bars = [], []
# Back-to-front painter's order: smaller (u - v) is further back.
for w, wd, dt, count, level in sorted(cells, key=lambda c: (c[0] - (6 - c[1]), c[0])):
    v = 6 - wd  # Sunday at the back edge
    u0, u1, v0, v1 = w + INSET, w + 1 - INSET, v + INSET, v + 1 - INSET
    base = [pt(u0, v0), pt(u1, v0), pt(u1, v1), pt(u0, v1)]
    tiles.append(poly(base, EMPTY))
    if count == 0:
        continue
    h = 4 + (MAX_H - 4) * math.sqrt(count / max_count)
    color = LEVEL.get(level, LEVEL["FOURTH_QUARTILE"])
    top = [pt(u0, v0, h), pt(u1, v0, h), pt(u1, v1, h), pt(u0, v1, h)]
    left = [pt(u0, v0), pt(u1, v0), pt(u1, v0, h), pt(u0, v0, h)]
    right = [pt(u1, v0), pt(u1, v1), pt(u1, v1, h), pt(u1, v0, h)]
    ox, oy = pt((u0 + u1) / 2, (v0 + v1) / 2)
    bars.append(
        f'<g class="b" style="transform-origin:{ox:.1f}px {oy:.1f}px;animation-delay:{w * 0.025:.3f}s">'
        f"<title>{dt}: {count} contribution{'s' if count != 1 else ''}</title>"
        + poly(left, shade(color, 0.72)) + poly(right, shade(color, 0.55)) + poly(top, color)
        + "</g>"
    )

def fmt(d):
    return date.fromisoformat(d).isoformat()

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<style>
@keyframes grow {{ from {{ transform: scaleY(0) }} to {{ transform: scaleY(1) }} }}
.b {{ transform-box: view-box; animation: grow .9s cubic-bezier(.2,.8,.2,1) both; }}
text {{ font-family: {FONT}; }}
</style>
<rect width="{W}" height="{H}" fill="{BG}"/>
<text x="40" y="54" fill="#e6edf3" font-size="21" font-weight="600">{total:,} contributions · 3D</text>
<text x="40" y="80" fill="#8b949e" font-size="15">{fmt(days[0][2])} → {fmt(days[-1][2])}</text>
<g>{''.join(tiles)}</g>
<g>{''.join(bars)}</g>
<text x="40" y="412" fill="#8b949e" font-size="15">Busiest day {busiest[2]} ({busiest[3]})</text>
<text x="40" y="434" fill="#8b949e" font-size="15">Longest streak {best} day{'s' if best != 1 else ''}</text>
<text x="40" y="456" fill="#8b949e" font-size="15">Active on {active} of {len(days)} days</text>
</svg>
"""
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print(f"wrote {OUT}: {total} contributions, busiest {busiest[2]} ({busiest[3]}), streak {best}, active {active}/{len(days)}")
