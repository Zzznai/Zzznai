#!/usr/bin/env python3
"""Momo the red panda.

Keeps the pet's state (pet/state.json) and draws it as an animated pixel-art
SVG (assets/panda.svg) for the profile README.

    python pet/pet.py render            redraw from the current state
    python pet/pet.py feed --user NAME  feed Momo, then redraw
    python pet/pet.py pet  --user NAME  pet Momo, then redraw
    python pet/pet.py tick              let time pass (hunger), then redraw
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state.json"
SVG_FILE = ROOT.parent / "assets" / "panda.svg"

FOOD_LOSS_PER_HOUR = 1.5      # a full belly lasts just under three days
LOVE_LOSS_PER_HOUR = 1.0
FEED_GAIN = 25
PET_GAIN = 20
HUNGRY_BELOW = 30
RECENT_SECONDS = 30 * 60      # how long Momo keeps munching / glowing after an action

DEFAULT_STATE = {
    "name": "Momo",
    "food": 70.0,
    "love": 60.0,
    "fed_count": 0,
    "pet_count": 0,
    "last_fed": None,
    "last_pet": None,
    "last_feeder": None,
    "last_petter": None,
    "updated": None,
}

# ---------------------------------------------------------------- sprites ---
PAL = {
    "K": "#2b1a16",  # outline, paws, nose
    "O": "#d9541e",  # fur
    "D": "#9c3414",  # dark fur (ear centres, tear tracks, tail tip)
    "L": "#f6b26b",  # tail rings
    "W": "#fff4e6",  # cream
    "B": "#4a2a20",  # belly and limbs
    "E": "#1b1210",  # eyes
    "P": "#ff8fa3",  # blush
    "R": "#ff5d73",  # tongue, hearts
    "T": "#7fd4ff",  # tears
    "G": "#5fbf4a",  # bamboo
    "g": "#2f8f3a",  # bamboo shade
}

HEAD = [
    "..KK................KK..",
    ".KWWK..............KWWK.",
    "KWWWWK..KKKKKKKK..KWWWWK",
    "KWDDWWKKOOOOOOOOKKWWDDWK",
    "KWDDWOOOOOOOOOOOOOOWDDWK",
    ".KWWOOOOOOOOOOOOOOOOWWK.",
    ".KOOOOWWOOOOOOOOWWOOOOK.",
    "KOOOOWWWWOOOOOOWWWWOOOOK",
    "KOOOOOOOOOOOOOOOOOOOOOOK",
    "KOOOOOOOOOWKKWOOOOOOOOOK",
    "KWWOODDDOWWKKWWODDDOOWWK",
    "KWWWODDOWWWWWWWWODDOWWWK",
    ".KWWWODWWWWWWWWWWDOWWWK.",
    ".KKWWWWWWWWWWWWWWWWWWKK.",
    "...KKKWWWWWWWWWWWWKKK...",
    "......KKKKKKKKKKKK......",
]

BODY = [  # drawn from row 16 down
    "....KOOOBBBBBBBBOOOK....",
    "...KKOOBBBBBBBBBBOOKK...",
    "..KBBKOBBBBBBBBBBOKBBK..",
    "..KBBKOBBBBBBBBBBOKBBK..",
    "..KBBKOBBBBBBBBBBOKBBK..",
    "...KKKOOBBBBBBBBOOKKK...",
    "...KBBBKOOOOOOOOKBBBK...",
    "..KBBBBBKKKKKKKKBBBBBK..",
    "..KBBBBBBK....KBBBBBBK..",
    "...KKKKKK......KKKKKK...",
]

TAIL = [
    "......KKKK..",
    ".....KDDDDK.",
    "....KDDDDDDK",
    "....KOOOOOOK",
    "....KOOOOOOK",
    "...KLLLLLLK.",
    "...KOOOOOOK.",
    "..KOOOOOOK..",
    "..KLLLLLLK..",
    ".KOOOOOOK...",
    ".KOOOOOK....",
    "KLLLLLK.....",
    "KOOOOK......",
    ".KKKK.......",
]
TAIL_AT = (19, 10)

HEART = [
    ".RR.RR.",
    "RRRRRRR",
    "RRRRRRR",
    ".RRRRR.",
    "..RRR..",
    "...R...",
]

EYES_OPEN = [(6, 8, "W"), (7, 8, "E"), (6, 9, "E"), (7, 9, "E"),
             (16, 8, "W"), (17, 8, "E"), (16, 9, "E"), (17, 9, "E")]
EYES_HAPPY = [(5, 9, "E"), (6, 8, "E"), (7, 8, "E"), (8, 9, "E"),
              (15, 9, "E"), (16, 8, "E"), (17, 8, "E"), (18, 9, "E")]
EYES_SAD = [(8, 8, "E"), (7, 8, "E"), (6, 9, "E"), (5, 9, "E"),      # closed, sloping down
            (15, 8, "E"), (16, 8, "E"), (17, 9, "E"), (18, 9, "E")]   # towards the outside
EYES_WIDE = [(6, 7, "E"), (7, 7, "E"), (16, 7, "E"), (17, 7, "E")] + EYES_OPEN
EYES_PLEAD = [(6, 8, "W"), (7, 8, "E"), (6, 9, "E"), (7, 9, "W"),
              (16, 8, "W"), (17, 8, "E"), (16, 9, "E"), (17, 9, "W"),
              (6, 7, "E"), (7, 7, "E"), (16, 7, "E"), (17, 7, "E")]
MOUTH_HAPPY = [(9, 11, "K"), (14, 11, "K"), (10, 12, "K"), (11, 12, "R"),
               (12, 12, "R"), (13, 12, "K"), (11, 13, "K"), (12, 13, "K")]
MOUTH_SAD = [(11, 12, "K"), (12, 12, "K"), (10, 13, "K"), (13, 13, "K")]
MOUTH_O = [(11, 12, "K"), (12, 12, "K")]
MOUTH_SMALL = [(10, 11, "K"), (13, 11, "K"), (11, 12, "K"), (12, 12, "K")]
MOUTH_CHEW_A = [(10, 12, "K"), (11, 12, "K"), (12, 12, "K"), (13, 12, "K")]
MOUTH_CHEW_B = [(10, 11, "K"), (13, 11, "K"), (11, 12, "K"), (12, 12, "K"),
                (11, 13, "K"), (12, 13, "K")]
BLUSH = [(2, 11, "P"), (3, 11, "P"), (20, 11, "P"), (21, 11, "P")]


def grid_rects(grid, ox=0, oy=0):
    width = len(grid[0])
    out = []
    for y, row in enumerate(grid):
        assert len(row) == width, f"row {y} is {len(row)} wide, expected {width}: {row}"
        x = 0
        while x < width:
            c = row[x]
            if c == ".":
                x += 1
                continue
            end = x
            while end < width and row[end] == c:
                end += 1
            out.append(f'<rect x="{ox + x}" y="{oy + y}" width="{end - x}" height="1" fill="{PAL[c]}"/>')
            x = end
    return "".join(out)


def dots(points):
    return "".join(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{PAL[c]}"/>' for x, y, c in points)


def wagged(grid):
    """Second tail frame: the upper part swings one or two pixels to the right."""
    out = []
    for y, row in enumerate(grid):
        shift = 2 if y < 3 else 1 if y < 7 else 0
        out.append("." * shift + row + "." * (2 - shift))
    return out


# ------------------------------------------------------------- animation ---
def fade(begin, end=None):
    """Attribute + <set> tags that make a group visible from `begin` to `end` seconds."""
    attr = "" if begin == 0 else ' opacity="0"'
    anim = "" if begin == 0 else f'<set attributeName="opacity" to="1" begin="{begin}s"/>'
    if end is not None:
        anim += f'<set attributeName="opacity" to="0" begin="{end}s"/>'
    return attr, anim


def blink(first_visible, begin, dur):
    """Two-frame toggle: returns the <animate> for frame A or frame B."""
    values = "1;0" if first_visible else "0;1"
    return (f'<animate attributeName="opacity" values="{values}" calcMode="discrete" '
            f'dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>')


def bubble(lines, cx, bottom, begin, end=None):
    char_w, line_h = 8.2, 18
    w = max(max(len(line) for line in lines) * char_w + 30, 54)
    h = line_h * len(lines) + 16
    x, y = cx - w / 2, bottom - h
    attr, anim = fade(begin, end)
    text = "".join(
        f'<text x="{cx}" y="{y + 22 + i * line_h}" text-anchor="middle" font-size="14" '
        f'font-weight="700" fill="#2b1a16">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return (
        f'<g{attr}>{anim}'
        f'<rect x="{x:.0f}" y="{y}" width="{w:.0f}" height="{h}" rx="9" fill="#fff8ee" stroke="#2b1a16" stroke-width="3"/>'
        f'<path d="M {cx - 8} {bottom - 2} L {cx} {bottom + 11} L {cx + 8} {bottom - 2} Z" fill="#fff8ee" stroke="#2b1a16" stroke-width="3"/>'
        f'<rect x="{cx - 9}" y="{bottom - 5}" width="18" height="4" fill="#fff8ee"/>'
        f'{text}</g>'
    )


def heart(x, y, begin, dur=2.6, scale=3, rise=70):
    return (
        f'<g opacity="0"><animate attributeName="opacity" values="0;1;1;0" keyTimes="0;0.15;0.7;1" '
        f'dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>'
        f'<animateTransform attributeName="transform" type="translate" from="{x} {y}" to="{x} {y - rise}" '
        f'dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>'
        f'<g transform="scale({scale})" shape-rendering="crispEdges">{grid_rects(HEART)}</g></g>'
    )


def bamboo(x, ground, segments, s):
    """A pixel bamboo stalk growing up from the ground at screen x."""
    out = []
    y = ground
    for i in range(segments):
        seg_h = 5 * s
        y -= seg_h
        out.append(f'<rect x="{x}" y="{y}" width="{2 * s}" height="{seg_h}" fill="{PAL["G"]}"/>')
        out.append(f'<rect x="{x + s}" y="{y}" width="{s}" height="{seg_h}" fill="{PAL["g"]}"/>')
        out.append(f'<rect x="{x - 1}" y="{y}" width="{2 * s + 2}" height="{s // 2}" fill="#1f6b2b"/>')
        if i % 2 == 1 and i < segments - 1:
            side = -1 if (i // 2) % 2 else 1
            lx = x + (2 * s if side > 0 else -3 * s)
            out.append(f'<rect x="{lx}" y="{y + s}" width="{3 * s}" height="{s}" fill="{PAL["G"]}"/>')
            out.append(f'<rect x="{lx + side * s}" y="{y}" width="{2 * s}" height="{s}" fill="{PAL["G"]}"/>')
    # leafy top
    out.append(f'<rect x="{x - 2 * s}" y="{y - s}" width="{6 * s}" height="{s}" fill="{PAL["G"]}"/>')
    out.append(f'<rect x="{x - s}" y="{y - 2 * s}" width="{4 * s}" height="{s}" fill="{PAL["g"]}"/>')
    out.append(f'<rect x="{x}" y="{y - 3 * s}" width="{2 * s}" height="{s}" fill="{PAL["G"]}"/>')
    return "".join(out)


def meter(x, y, value, color):
    filled = max(0, min(10, round(value / 10)))
    return "".join(
        f'<rect x="{x + i * 19}" y="{y}" width="15" height="12" fill="{color if i < filled else "#22303f"}"/>'
        for i in range(10)
    )


def clean_user(name):
    name = re.sub(r"[^A-Za-z0-9-]", "", name or "")[:20]
    return name or None


# ----------------------------------------------------------------- state ---
def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_time(text):
    return datetime.fromisoformat(text) if text else None


def load_state():
    state = dict(DEFAULT_STATE)
    if STATE_FILE.exists():
        state.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return state


def let_time_pass(state, now):
    last = parse_time(state["updated"])
    if last:
        hours = max(0.0, (now - last).total_seconds() / 3600)
        state["food"] = round(max(0.0, state["food"] - hours * FOOD_LOSS_PER_HOUR), 2)
        state["love"] = round(max(0.0, state["love"] - hours * LOVE_LOSS_PER_HOUR), 2)
    state["updated"] = now.isoformat()


def mood_of(state, now):
    def recent(key):
        when = parse_time(state[key])
        return when is not None and (now - when).total_seconds() < RECENT_SECONDS

    fed, petted = recent("last_fed"), recent("last_pet")
    if fed and petted:
        return "eating" if parse_time(state["last_fed"]) >= parse_time(state["last_pet"]) else "loved"
    if fed:
        return "eating"
    if petted:
        return "loved"
    if state["food"] < HUNGRY_BELOW:
        return "hungry"
    return "happy"


# ------------------------------------------------------------------ draw ---
def build_svg(state, mood):
    s = 6                       # screen pixels per sprite pixel
    width, height, ground = 720, 340, 292
    px, py = 96, ground - 26 * s
    cx = px + 12 * s            # centre of the head
    t_notice, t_happy = 2.6, 3.3
    name = escape(state["name"])
    feeder, petter = clean_user(state["last_feeder"]), clean_user(state["last_petter"])

    # what happens after the greeting, per mood
    settle = None               # when the excited phase ends (None = never)
    if mood == "happy":
        lines, status = ["you came!!", "best day ever"], "happy and full"
    elif mood == "loved":
        lines = ["that was the best", f"pet ever, @{petter}!" if petter else "pet ever!"]
        status = "feeling loved"
    elif mood == "eating":
        settle = t_happy + 1.8
        lines, status = ["yay, you're here!"], "munching bamboo"
        after = ["nom nom nom...", f"thanks @{feeder}!" if feeder else "thank you!"]
    else:
        settle = t_happy + 1.8
        lines, status = ["yay, you're here!"], "hungry"
        after = ["...do you have", "any bamboo?"]

    # ---- face layers -----------------------------------------------------
    a, anim = fade(0, t_notice)
    tear = (f'<rect x="6" y="10" width="1" height="1" fill="{PAL["T"]}">'
            f'<animate attributeName="y" values="10;11;12;13;14" calcMode="discrete" dur="1.2s" repeatCount="indefinite"/></rect>'
            f'<rect x="17" y="10" width="1" height="1" fill="{PAL["T"]}">'
            f'<animate attributeName="y" values="12;13;14;10;11" calcMode="discrete" dur="1.2s" repeatCount="indefinite"/></rect>')
    face = f'<g{a}>{anim}{dots(EYES_SAD + MOUTH_SAD)}{tear}</g>'

    a, anim = fade(t_notice, t_happy)
    face += f'<g{a}>{anim}{dots(EYES_WIDE + MOUTH_O)}</g>'

    a, anim = fade(t_happy, settle)
    face += f'<g{a}>{anim}{dots(EYES_HAPPY + MOUTH_HAPPY + BLUSH)}</g>'

    if mood == "eating":
        a, anim = fade(settle)
        stalk = (f'<rect x="13" y="12" width="12" height="2" fill="{PAL["G"]}"/>'
                 f'<rect x="13" y="13" width="12" height="1" fill="{PAL["g"]}"/>'
                 f'<rect x="17" y="12" width="1" height="2" fill="#1f6b2b"/>'
                 f'<rect x="22" y="12" width="1" height="2" fill="#1f6b2b"/>'
                 f'<rect x="24" y="10" width="3" height="1" fill="{PAL["G"]}"/>'
                 f'<rect x="25" y="11" width="3" height="1" fill="{PAL["G"]}"/>'
                 f'<rect x="25" y="14" width="3" height="1" fill="{PAL["G"]}"/>'
                 f'<rect x="15" y="13" width="3" height="3" fill="{PAL["B"]}"/>'
                 f'<rect x="15" y="16" width="3" height="1" fill="{PAL["K"]}"/>')
        face += (f'<g{a}>{anim}{dots(EYES_HAPPY + BLUSH)}{stalk}'
                 f'<g>{blink(True, settle, 0.5)}{dots(MOUTH_CHEW_A)}</g>'
                 f'<g opacity="0">{blink(False, settle, 0.5)}{dots(MOUTH_CHEW_B)}</g></g>')
    elif mood == "hungry":
        a, anim = fade(settle)
        face += f'<g{a}>{anim}{dots(EYES_PLEAD + MOUTH_SMALL)}</g>'

    # ---- body motion -----------------------------------------------------
    hop = "0 0;0 -10;0 -16;0 -10;0 0;0 -10;0 -16;0 -10;0 0;0 0;0 0;0 0"
    repeat = "indefinite" if settle is None else "1"
    motion = (f'<animateTransform attributeName="transform" type="translate" values="{hop}" '
              f'calcMode="discrete" dur="1.8s" begin="{t_happy}s" repeatCount="{repeat}"/>')
    # a little startled hop when Momo notices you
    motion += (f'<animateTransform attributeName="transform" type="translate" values="0 0;0 -8;0 0" '
               f'calcMode="discrete" dur="0.45s" begin="{t_notice}s" repeatCount="1"/>')
    if mood == "hungry":
        motion += (f'<animateTransform attributeName="transform" type="translate" '
                   f'values="0 0;2 0;-2 0;2 0;0 0;0 0;0 0;0 0;0 0;0 0" calcMode="discrete" dur="3s" '
                   f'begin="{settle + 1}s" repeatCount="indefinite"/>')

    tx, ty = TAIL_AT
    wag_dur = 0.4 if mood != "hungry" else 0.9
    tail = (f'<g>{blink(True, t_happy, wag_dur)}{grid_rects(TAIL + [], tx, ty)}</g>'
            f'<g opacity="0">{blink(False, t_happy, wag_dur)}{grid_rects(wagged(TAIL), tx, ty)}</g>')

    panda = (
        f'<g transform="translate({px} {py})"><g>{motion}'
        f'<g transform="scale({s})" shape-rendering="crispEdges">'
        f'{tail}{grid_rects(BODY, 0, 16)}{grid_rects(HEAD)}{face}'
        f'</g></g></g>'
    )

    # ---- bubbles and hearts ------------------------------------------------
    bubble_bottom = py - 22
    bubbles = bubble([". . ."], cx, bubble_bottom, 0, t_notice)
    bubbles += bubble(["!"], cx, bubble_bottom, t_notice, t_happy)
    bubbles += bubble(lines, cx, bubble_bottom, t_happy, settle)
    if settle is not None:
        bubbles += bubble(after, cx, bubble_bottom, settle)

    hearts = ""
    spots = [(-70, 10, 0.0), (78, 0, 0.9), (-40, -20, 1.7)]
    if mood == "loved":
        spots += [(50, -30, 0.4), (-95, -10, 1.3), (100, 20, 2.1), (5, -45, 2.4)]
    if mood in ("happy", "loved"):
        for dx, dy, delay in spots:
            hearts += heart(cx + dx, py + 40 + dy, t_happy + delay)
    else:
        for dx, dy, delay in spots[:2]:   # a short burst while greeting
            hearts += (f'<g>{"".join(fade(0, settle)[1:])}'
                       f'{heart(cx + dx, py + 40 + dy, t_happy + delay, dur=1.6)}</g>')

    # ---- scenery -------------------------------------------------------------
    stars = ""
    for i, (x, y) in enumerate([(60, 40), (150, 78), (232, 30), (330, 62), (402, 24), (470, 96),
                                (545, 38), (612, 70), (668, 28), (694, 120), (30, 130), (385, 130)]):
        stars += (f'<rect x="{x}" y="{y}" width="3" height="3" fill="#dfe9ff">'
                  f'<animate attributeName="opacity" values="1;0.2;1" dur="{2 + i % 4}s" '
                  f'begin="{(i * 0.37) % 2:.2f}s" repeatCount="indefinite"/></rect>')
    moon = ('<g shape-rendering="crispEdges"><rect x="612" y="34" width="36" height="48" fill="#ffe9a8"/>'
            '<rect x="606" y="40" width="48" height="36" fill="#ffe9a8"/>'
            '<rect x="624" y="46" width="12" height="12" fill="#f1d27c"/>'
            '<rect x="636" y="64" width="6" height="6" fill="#f1d27c"/></g>')
    grove = (bamboo(22, ground, 9, 4) + bamboo(54, ground, 6, 4) + bamboo(318, ground, 8, 4)
             + bamboo(352, ground, 5, 4) + bamboo(690, ground, 7, 4))
    grass = (f'<rect x="0" y="{ground}" width="{width}" height="{height - ground}" fill="#173b2a"/>'
             f'<rect x="0" y="{ground}" width="{width}" height="6" fill="#2c6e3f"/>')
    for x in range(8, width, 34):
        grass += f'<rect x="{x}" y="{ground - 6}" width="4" height="6" fill="#2c6e3f"/>'
        grass += f'<rect x="{x + 12}" y="{ground - 3}" width="4" height="3" fill="#2c6e3f"/>'

    # ---- info panel ------------------------------------------------------------
    ix = 420
    facts = f'fed {state["fed_count"]}x  ·  petted {state["pet_count"]}x'
    last = ""
    if feeder:
        last = f"last snack from @{feeder}"
    elif petter:
        last = f"last pet from @{petter}"
    panel = (
        f'<text x="{ix}" y="150" font-size="30" font-weight="700" fill="#fff4e6" letter-spacing="3">{name.upper()}</text>'
        f'<text x="{ix}" y="170" font-size="12" fill="#9db4c9">the red panda who lives here</text>'
        f'<text x="{ix}" y="198" font-size="12" font-weight="700" fill="#9db4c9">FOOD</text>'
        f'<g shape-rendering="crispEdges">{meter(ix + 46, 188, state["food"], "#5fbf4a")}</g>'
        f'<text x="{ix}" y="222" font-size="12" font-weight="700" fill="#9db4c9">LOVE</text>'
        f'<g shape-rendering="crispEdges">{meter(ix + 46, 212, state["love"], "#ff5d73")}</g>'
        f'<text x="{ix}" y="248" font-size="12" fill="#dfe9ff">mood: <tspan font-weight="700" fill="#ffd27a">{status}</tspan></text>'
        f'<text x="{ix}" y="266" font-size="12" fill="#9db4c9">{escape(facts)}</text>'
        f'<text x="{ix}" y="282" font-size="12" fill="#9db4c9">{escape(last)}</text>'
    )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'font-family="Consolas, Menlo, \'DejaVu Sans Mono\', \'Courier New\', monospace">'
        f'<title>{name} the pixel red panda: sad until you arrive, then very happy</title>'
        f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#0b1524"/><stop offset="1" stop-color="#1b3147"/></linearGradient>'
        f'<clipPath id="card"><rect width="{width}" height="{height}" rx="16"/></clipPath></defs>'
        f'<g clip-path="url(#card)"><rect width="{width}" height="{height}" fill="url(#sky)"/>'
        f'{stars}{moon}<g shape-rendering="crispEdges">{grove}{grass}</g>'
        f'{panda}{hearts}{bubbles}{panel}</g></svg>\n'
    )


def save(state, now):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    SVG_FILE.parent.mkdir(exist_ok=True)
    SVG_FILE.write_text(build_svg(state, mood_of(state, now)), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["render", "feed", "pet", "tick"])
    parser.add_argument("--user", default=None, help="GitHub login of whoever fed or petted")
    args = parser.parse_args()

    now = now_utc()
    state = load_state()
    if args.action != "render":
        let_time_pass(state, now)
    if args.action == "feed":
        state["food"] = min(100.0, state["food"] + FEED_GAIN)
        state["fed_count"] += 1
        state["last_fed"], state["last_feeder"] = now.isoformat(), clean_user(args.user)
    elif args.action == "pet":
        state["love"] = min(100.0, state["love"] + PET_GAIN)
        state["pet_count"] += 1
        state["last_pet"], state["last_petter"] = now.isoformat(), clean_user(args.user)
    if state["updated"] is None:
        state["updated"] = now.isoformat()
    save(state, now)
    print(f'{state["name"]}: food {state["food"]:.0f}, love {state["love"]:.0f}, mood {mood_of(state, now)}')


if __name__ == "__main__":
    main()
