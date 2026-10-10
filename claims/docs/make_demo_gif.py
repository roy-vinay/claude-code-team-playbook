"""Render docs/claims-demo.gif: a split-screen replay of demo.sh.

The command output shown is copied from a real run of ./demo.sh. Only the
regeneration of this GIF needs Pillow (pip install pillow); claims itself
has no dependencies.

    python3 claims/docs/make_demo_gif.py
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).with_name("claims-demo.gif")
W, H = 1200, 720
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
SANS = "/usr/share/fonts/opentype/inter/Inter-Medium.otf"
SANS_B = "/usr/share/fonts/opentype/inter/Inter-Bold.otf"

C = {
    "bg": "#0d1117", "pane": "#161b22", "edge": "#30363d", "text": "#e6edf3", "dim": "#8b949e",
    "green": "#3fb950", "red": "#f85149", "amber": "#d29922", "blue": "#58a6ff", "purple": "#bc8cff",
    "row": "#1c2128",
}

f_mono = ImageFont.truetype(MONO, 15)
f_mono_b = ImageFont.truetype(MONO_B, 15)
f_small = ImageFont.truetype(MONO, 13)
f_title = ImageFont.truetype(SANS_B, 20)
f_label = ImageFont.truetype(SANS, 15)
f_label_b = ImageFont.truetype(SANS_B, 15)
f_cap = ImageFont.truetype(SANS, 21)
f_big = ImageFont.truetype(SANS_B, 44)

CHAR_W = f_mono.getlength("m")
PANE_Y, PANE_H = 64, 340
PANES = {"dana": (24, 576), "lee": (600, 576)}
WRAP = int((576 - 32) // CHAR_W)
MAX_LINES = int((PANE_H - 52) // 21)


class State:
    def __init__(self):
        self.lines = {"dana": [], "lee": []}   # (text, color, bold)
        self.rows = []                          # dicts: target, holder, status, color, note
        self.caption = ""
        self.focus = None                       # pane to highlight
        self.link = False                       # draw overlap marker between rows

    def add(self, pane, text, color="text", bold=False, indent=""):
        for i, chunk in enumerate(textwrap.wrap(text, WRAP - len(indent), break_long_words=True,
                                                break_on_hyphens=False) or [""]):
            self.lines[pane].append(((indent if i else "") + chunk, color, bold))


def draw(st: State, typing: tuple[str, str] | None = None) -> Image.Image:
    im = Image.new("RGB", (W, H), C["bg"])
    d = ImageDraw.Draw(im)

    # Header
    d.text((24, 20), "claims", font=f_title, fill=C["text"])
    d.text((24 + f_title.getlength("claims  "), 23), "two agents, one shared file",
           font=f_label, fill=C["dim"])
    tag = "replay of claims/demo.sh"
    d.text((W - 24 - f_small.getlength(tag), 25), tag, font=f_small, fill=C["dim"])

    # Agent panes
    meta = {"dana": ("Dana", "checkout agent", "CHK-412", C["blue"]),
            "lee": ("Lee", "promotions agent", "PRM-207", C["purple"])}
    for key, (x, w) in PANES.items():
        name, role, ticket, col = meta[key]
        border = col if st.focus == key else C["edge"]
        d.rounded_rectangle((x, PANE_Y, x + w, PANE_Y + PANE_H), 10, fill=C["pane"], outline=border,
                            width=2 if st.focus == key else 1)
        d.ellipse((x + 16, PANE_Y + 15, x + 26, PANE_Y + 25), fill=col)
        d.text((x + 34, PANE_Y + 10), name, font=f_label_b, fill=C["text"])
        d.text((x + 34 + f_label_b.getlength(name + "  "), PANE_Y + 10), f"{role} · {ticket}",
               font=f_label, fill=C["dim"])
        d.line((x, PANE_Y + 38, x + w, PANE_Y + 38), fill=C["edge"])
        lines = list(st.lines[key])
        if typing and typing[0] == key:
            for i, chunk in enumerate(textwrap.wrap(typing[1], WRAP, break_long_words=True,
                                                    break_on_hyphens=False) or [""]):
                lines.append((chunk, "text", False))
            lines[-1] = (lines[-1][0] + "▌", lines[-1][1], lines[-1][2])
        y = PANE_Y + 50
        for text, color, bold in lines[-MAX_LINES:]:
            if text.startswith("$ "):
                d.text((x + 16, y), "$", font=f_mono_b, fill=C["green"])
                d.text((x + 16 + 2 * CHAR_W, y), text[2:], font=f_mono, fill=C["text"])
            else:
                d.text((x + 16, y), text, font=f_mono_b if bold else f_mono, fill=C[color])
            y += 21

    # Registry
    ry = PANE_Y + PANE_H + 18
    d.rounded_rectangle((24, ry, W - 24, ry + 220), 10, fill=C["pane"], outline=C["edge"])
    d.text((40, ry + 12), "Claims registry", font=f_label_b, fill=C["text"])
    d.text((40 + f_label_b.getlength("Claims registry  "), ry + 12),
           "src/pricing/calculate.py is a hot file, so it is claimed by function",
           font=f_label, fill=C["dim"])
    cols = (40, 470, 700, 860)
    hy = ry + 44
    for cx, head in zip(cols, ("Target", "Held by", "Status", "")):
        d.text((cx, hy), head, font=f_small, fill=C["dim"])
    d.line((36, hy + 22, W - 36, hy + 22), fill=C["edge"])
    y = hy + 30
    first_hit = None
    for i, r in enumerate(st.rows):
        if r.get("hl"):
            d.rounded_rectangle((32, y - 5, W - 32, y + 25), 6, fill=C["row"])
        d.text((cols[0], y), r["target"], font=f_mono, fill=C["text"])
        d.text((cols[1], y), r["holder"], font=f_mono, fill=C["blue"] if "dana" in r["holder"] else C["purple"])
        col = C[r["color"]]
        chip_w = f_small.getlength(r["status"]) + 22
        d.rounded_rectangle((cols[2], y - 2, cols[2] + chip_w, y + 21), 11, outline=col, width=1,
                            fill=None)
        d.text((cols[2] + 11, y + 2), r["status"], font=f_small, fill=col)
        if r.get("note"):
            d.text((cols[3], y + 1), r["note"], font=f_small, fill=C["dim"])
        if r["target"].endswith("calculate_total") and first_hit is None:
            first_hit = y
        elif r["target"].endswith("calculate_total") and st.link:
            # Bracket on the right showing the two claims on calculate_total collide.
            bx = W - 48
            d.line((bx, first_hit + 10, bx + 8, first_hit + 10), fill=C["amber"], width=2)
            d.line((bx + 8, first_hit + 10, bx + 8, y + 10), fill=C["amber"], width=2)
            d.line((bx, y + 10, bx + 8, y + 10), fill=C["amber"], width=2)
            d.text((bx - 6 - f_small.getlength("same function"), (first_hit + y) / 2 + 2),
                   "same function", font=f_small, fill=C["amber"])
        y += 34

    # Caption
    if st.caption:
        cy = H - 50
        d.text(((W - f_cap.getlength(st.caption)) / 2, cy), st.caption, font=f_cap, fill=C["text"])
    return im


def build():
    frames: list[tuple[Image.Image, int]] = []
    st = State()

    def snap(ms):
        frames.append((draw(st), ms))

    def type_cmd(pane, cmd, step=4):
        st.focus = pane
        text = "$ " + cmd
        for i in range(2, len(text) + step, step):
            frames.append((draw(st, (pane, text[:i])), 45))
        st.add(pane, text, indent="  ")

    def out(pane, text, color="text", bold=False, hold=0, indent=""):
        st.add(pane, text, color, bold, indent)
        if hold:
            snap(hold)

    # Title card
    card = Image.new("RGB", (W, H), C["bg"])
    cd = ImageDraw.Draw(card)
    t1, t2 = "Ask before you build.", "Coding agents claim shared code before they edit it."
    cd.text(((W - f_big.getlength(t1)) / 2, 270), t1, font=f_big, fill=C["text"])
    cd.text(((W - f_cap.getlength(t2)) / 2, 340), t2, font=f_cap, fill=C["dim"])
    frames.append((card, 2200))

    st.caption = "Two developers, two tickets, one shared pricing file."
    snap(1800)

    st.caption = "Dana's agent claims the one function it will change."
    type_cmd("dana", "claims propose src/pricing/calculate.py::calculate_total")
    out("dana", "#1 ACCEPTED: Accepted. You may edit these targets.", "green", True)
    st.rows.append({"target": "calculate.py::calculate_total", "holder": "CHK-412 @dana",
                    "status": "ACCEPTED", "color": "green"})
    snap(1900)

    st.caption = "Lee's agent claims a different function in the same file. No overlap, so it's accepted."
    type_cmd("lee", "claims propose src/pricing/calculate.py::apply_discount src/promotions/")
    out("lee", "#2 ACCEPTED: Accepted. You may edit these targets.", "green", True)
    st.rows.append({"target": "calculate.py::apply_discount", "holder": "PRM-207 @lee",
                    "status": "ACCEPTED", "color": "green"})
    st.rows.append({"target": "src/promotions/", "holder": "PRM-207 @lee",
                    "status": "ACCEPTED", "color": "green"})
    snap(2300)

    st.caption = "Edits inside the claim go straight through."
    out("lee", "● Edit calculate.py  (apply_discount)", "dim", hold=700)
    out("lee", "✓ hook: edit allowed", "green", True, hold=1500)

    st.caption = "Then Lee's agent reaches for Dana's function. The hook blocks the edit."
    out("lee", "● Edit calculate.py  (calculate_total)", "dim", hold=800)
    out("lee", "✗ No accepted claim for src/pricing/calculate.py::calculate_total "
               "on PRM-207. Run: claims propose ... and wait.", "red", True, indent="  ")
    st.rows[0]["hl"] = True
    snap(2600)

    st.caption = "So it asks. The request goes to Dana, not to a merge conflict."
    type_cmd("lee", 'claims propose src/pricing/calculate.py::calculate_total '
                    '--reason "store applied promo codes on the total"')
    out("lee", "#3 PENDING: Paused. Do not edit these targets yet. Request sent to @dana.",
        "amber", True, indent="  ")
    st.rows.append({"target": "calculate.py::calculate_total", "holder": "PRM-207 @lee",
                    "status": "PENDING", "color": "amber", "note": "waiting on @dana", "hl": True})
    st.link = True
    snap(2400)

    st.caption = "Dana sees the request, with the reason, in her inbox."
    type_cmd("dana", "claims inbox")
    out("dana", "request #1  PRM-207 (@lee): calculate.py::calculate_total "
                "is already claimed by CHK-412 (accepted).", "amber", indent="  ")
    out("dana", "    why: store applied promo codes on the total", "dim")
    snap(2600)

    st.caption = "She answers with what to do instead."
    type_cmd("dana", 'claims decline 1 --note "I\'ll add a promo_codes argument '
                     'to calculate_total by 3pm. Build against that."')
    out("dana", "Request #1 declined. Claim #3 is now declined.", "text", True)
    st.rows[3].update(status="DECLINED", color="red", note="note from @dana")
    snap(2200)

    st.caption = "Lee's agent builds against Dana's change. Nothing gets built twice."
    st.focus = "lee"
    out("lee", "note from @dana: I'll add a promo_codes argument to calculate_total "
               "by 3pm. Build against that.", "blue", True, indent="  ")
    out("lee", "● Waiting for Dana's change; continuing in src/promotions/", "dim")
    st.rows[0]["hl"] = st.rows[3]["hl"] = False
    st.link = False
    snap(3200)

    # End card
    card = Image.new("RGB", (W, H), C["bg"])
    cd = ImageDraw.Draw(card)
    t1 = "claims"
    t2 = "Claim before you edit. Overlaps go to the owner."
    t3 = "github.com/roy-vinay/claude-code-team-playbook"
    cd.text(((W - f_big.getlength(t1)) / 2, 250), t1, font=f_big, fill=C["text"])
    cd.text(((W - f_cap.getlength(t2)) / 2, 320), t2, font=f_cap, fill=C["dim"])
    cd.text(((W - f_label.getlength(t3)) / 2, 370), t3, font=f_label, fill=C["blue"])
    frames.append((card, 2800))
    return frames


def main():
    frames = build()
    palette_src = Image.new("RGB", (W, H * 2), C["bg"])
    palette_src.paste(frames[-3][0], (0, 0))
    palette_src.paste(frames[len(frames) // 2][0], (0, H))
    pal = palette_src.quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    imgs = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f, _ in frames]
    imgs[0].save(OUT, save_all=True, append_images=imgs[1:], duration=[ms for _, ms in frames],
                 loop=0, optimize=True, disposal=1)
    total = sum(ms for _, ms in frames) / 1000
    print(f"{OUT} {len(frames)} frames, {total:.1f}s, {OUT.stat().st_size / 1e6:.2f} MB")
    for i, idx in enumerate((10, len(frames) // 2, len(frames) - 2)):
        frames[idx][0].save(OUT.with_name(f"_preview{i}.png"))


if __name__ == "__main__":
    main()
