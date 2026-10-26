#!/usr/bin/env python3
"""Generate RallyCut logo candidates. Pure paths, no mask/clipPath."""
import math, pathlib

OUT = pathlib.Path(__file__).resolve().parent / "svg"
OUT.mkdir(parents=True, exist_ok=True)

INK   = "#111417"
LIME  = "#C2EC94"
CREAM = "#F3F7EE"
FONT  = "'Helvetica Neue', Helvetica, Inter, Arial, sans-serif"


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def pt(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def circle_path(cx, cy, r):
    return (f"M{f(cx - r)} {f(cy)}A{f(r)} {f(r)} 0 1 0 {f(cx + r)} {f(cy)}"
            f"A{f(r)} {f(r)} 0 1 0 {f(cx - r)} {f(cy)}Z")


def rounded_poly(points, r):
    n = len(points)
    corners = []
    for i, p in enumerate(points):
        prev, nxt = points[i - 1], points[(i + 1) % n]
        v1 = (prev[0] - p[0], prev[1] - p[1])
        v2 = (nxt[0] - p[0], nxt[1] - p[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        rr = min(r, l1 / 2, l2 / 2)
        corners.append(((p[0] + v1[0] / l1 * rr, p[1] + v1[1] / l1 * rr), p,
                        (p[0] + v2[0] / l2 * rr, p[1] + v2[1] / l2 * rr)))
    d = f"M{f(corners[0][2][0])} {f(corners[0][2][1])}"
    for i in range(1, n + 1):
        a, p, b = corners[i % n]
        d += f"L{f(a[0])} {f(a[1])}Q{f(p[0])} {f(p[1])} {f(b[0])} {f(b[1])}"
    return d + "Z"


# --------------------------------------------------------------- concept 1
def c1():
    """Slice Paddle — blade with a bite cut out; the ball sits in the bite."""
    cx, cy, r = 112, 104, 60
    mouth, half = -38, 28
    x1, y1 = pt(cx, cy, r, mouth + half)
    x2, y2 = pt(cx, cy, r, mouth - half)
    blade = (f"M{f(cx)} {f(cy)}L{f(x1)} {f(y1)}"
             f"A{f(r)} {f(r)} 0 1 1 {f(x2)} {f(y2)}Z")
    hx, hy = pt(cx, cy, r + 40, mouth + 180)
    bx, by = pt(cx, cy, r + 6, mouth)
    return f"""  <g transform="rotate(52 {f(hx)} {f(hy)})">
    <rect x="{f(hx - 14)}" y="{f(hy - 4)}" width="28" height="84" rx="14" fill="{LIME}"/>
  </g>
  <path d="{blade}" fill="{LIME}"/>
  <circle cx="{f(bx)}" cy="{f(by)}" r="17" fill="{CREAM}"/>
  <circle cx="{f(bx + 36)}" cy="{f(by - 30)}" r="6" fill="{CREAM}" opacity=".3"/>"""


# --------------------------------------------------------------- concept 2
def c2():
    """Play Ball — the ball's negative space is a play button."""
    tri = rounded_poly([(96, 78), (166, 120), (96, 162)], 9)
    return (f'  <path d="{circle_path(126, 120, 74)} {tri}" fill-rule="evenodd" '
            f'fill="{CREAM}"/>\n'
            f'  <rect x="24" y="99" width="38" height="12" rx="6" fill="{LIME}" opacity=".95"/>\n'
            f'  <rect x="12" y="121" width="26" height="12" rx="6" fill="{LIME}" opacity=".5"/>\n'
            f'  <rect x="26" y="143" width="16" height="12" rx="6" fill="{LIME}" opacity=".3"/>')


# --------------------------------------------------------------- concept 3
def c3():
    """Timeline Bounce — a rally's flight path over the clip timeline.

    Chosen direction: dotted flight path + ball + timeline rows where one
    clip is highlighted (= the rally you keep).
    """
    tiles = [(20, 32, False), (62, 24, False), (96, 46, True), (152, 20, False), (182, 28, False)]
    bars = "".join(
        f'<rect x="{x}" y="162" width="{w}" height="18" rx="9" '
        f'fill="{CREAM if hl else LIME}" opacity="{1 if hl else .3}"/>' for x, w, hl in tiles)
    return f"""  <path d="M26 100C44 158 88 158 114 96" fill="none" stroke="{LIME}" stroke-width="9.5"
        stroke-linecap="round" stroke-dasharray="10 12"/>
  <circle cx="126" cy="88" r="18" fill="{CREAM}"/>
  {bars}"""


def c3_body(bars_color=LIME, bars_op=0.3, ball=CREAM, arc=LIME, hl_color=None):
    """Same mark with overridable colours, for mono variants."""
    tiles = [(20, 32, False), (62, 24, False), (96, 46, True), (152, 20, False), (182, 28, False)]
    bars = "".join(
        f'<rect x="{x}" y="162" width="{w}" height="18" rx="9" '
        f'fill="{(hl_color or ball) if hl else bars_color}" opacity="{1 if hl else bars_op}"/>'
        for x, w, hl in tiles)
    return f"""  <path d="M26 100C44 158 88 158 114 96" fill="none" stroke="{arc}" stroke-width="9.5"
        stroke-linecap="round" stroke-dasharray="10 12"/>
  <circle cx="126" cy="88" r="18" fill="{ball}"/>
  {bars}"""


# --------------------------------------------------------------- concept 4
def c4():
    """Cut Ball — the ball itself is sliced and slid, with a lime cut face."""
    cx, cy, r, gap, ang = 118, 112, 62, 5, -22
    # half-disc paths built in a rotated frame
    top = (f"M-{r} -{gap}A{r} {r} 0 0 1 {r} -{gap}Z")
    bottom = (f"M{r} {gap}A{r} {r} 0 0 1 -{r} {gap}Z")
    return f"""  <g transform="translate({cx} {cy}) rotate({ang})">
    <path d="{top}" fill="{CREAM}"/>
    <path d="M{-r + 8} {-gap}L{r - 8} {-gap}" stroke="{LIME}" stroke-width="5"
          stroke-linecap="round" opacity=".9"/>
    <g transform="translate(13 15)">
      <path d="{bottom}" fill="{CREAM}"/>
    </g>
  </g>"""


# --------------------------------------------------------------- concept 5
def c5():
    """Classic Serve — paddle, ball, dotted flight path."""
    bcx, bcy, br = 78, 132, 41
    n = (math.cos(math.radians(-45)), math.sin(math.radians(-45)))   # normal to handle axis
    ax = (math.cos(math.radians(45)), math.sin(math.radians(45)))
    base = (118, 172)
    tip = (152, 206)
    hw_base, hw_tip = 12, 8.5
    pts = [(base[0] + n[0] * hw_base, base[1] + n[1] * hw_base),
           (tip[0] + n[0] * hw_tip, tip[1] + n[1] * hw_tip),
           (tip[0] - n[0] * hw_tip, tip[1] - n[1] * hw_tip),
           (base[0] - n[0] * hw_base, base[1] - n[1] * hw_base)]
    return f"""  <path d="{rounded_poly(pts, 9)}" fill="{LIME}"/>
  <circle cx="{bcx}" cy="{bcy}" r="{br}" fill="{LIME}"/>
  <circle cx="{bcx}" cy="{bcy}" r="{br - 9}" fill="none" stroke="{CREAM}"
        stroke-width="3" opacity=".28"/>
  <path d="M118 116Q158 70 170 78" fill="none" stroke="{LIME}" stroke-width="7"
        stroke-linecap="round" stroke-dasharray="1 15"/>
  <circle cx="188" cy="62" r="17" fill="{CREAM}"/>"""


# --------------------------------------------------------------- concept 6
def c6():
    """Type Slash — the wordmark itself is cut by the edit."""
    txt = (f'<text x="24" y="130" font-family="{FONT}" font-size="78" font-weight="700" '
           f'letter-spacing="-2.6" fill="{CREAM}">Rally<tspan fill="{LIME}">Cut</tspan></text>')
    cut = (f'<g transform="rotate(-9 176 96)">'
           f'<path d="M14 92H338" stroke="{INK}" stroke-width="13" stroke-linecap="round"/>'
           f'<path d="M22 99H330" stroke="{LIME}" stroke-width="3.5" stroke-linecap="round" '
           f'opacity=".85"/></g>')
    return f"  {txt}\n  {cut}"


ICONS = {
    "c1-slice-paddle": (c1, 240, 240),
    "c2-play-ball": (c2, 240, 240),
    "c3-timeline-bounce": (c3, 240, 240),
    "c4-cut-ball": (c4, 240, 240),
    "c5-classic-serve": (c5, 240, 240),
    "c6-type-slash": (c6, 400, 200),
}

for name, (fn, w, h) in ICONS.items():
    body = fn()
    doc = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
           f'role="img" aria-label="RallyCut logo candidate {name}">\n{body}\n</svg>\n')
    (OUT / f"{name}-icon.svg").write_text(doc)


def wordmark(size, x, y):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="700" letter-spacing="-{size * 0.033:.1f}" fill="{CREAM}">'
            f'Rally<tspan fill="{LIME}">Cut</tspan></text>')


def tagline(x, y, size=15):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="500" letter-spacing="{size * 0.16:.1f}" fill="#8FA2AB">'
            f'让每个好球，留下来</text>')


for name, (fn, w, h) in ICONS.items():
    body = fn()
    if name == "c6-type-slash":
        doc = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="6 12 400 188" '
               f'role="img" aria-label="RallyCut wordmark">\n{body}\n{tagline(26, 178, 14)}\n</svg>\n')
    else:
        s = 0.55
        doc = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 196" '
               f'role="img" aria-label="RallyCut logo lockup">\n'
               f'  <g transform="translate(14 22) scale({s})">\n{body}\n  </g>\n'
               f'  {wordmark(74, 186, 112)}\n  {tagline(192, 152, 14)}\n</svg>\n')
    (OUT / f"{name}-lockup.svg").write_text(doc)



# ------------------------------------------------------------------ gallery
SEL = "c3-timeline-bounce"          # the direction chosen for production
META = {
    "c1-slice-paddle": dict(
        title="Slice Paddle", zh="一口切",
        line="球拍咬掉一口，球正好在缺口里——「Cut」变成了一个动作，也是一张脸。",
        pros="最活泼、最有记忆点；小尺寸仍是一个圆加一个球。",
        cons="容易被读成吃豆人 / 表情，球拍感取决于手柄。"),
    "c2-play-ball": dict(
        title="Play Ball", zh="开球即播放",
        line="球的负空间就是播放键：乒乓球 × 视频，两个语义一次说完。",
        pros="最小、最像 app 图标，16px 也认得出；天然可做播放动画。",
        cons="没有「剪辑」的手感，稍偏「播放器」。"),
    "c3-timeline-bounce": dict(
        title="Timeline Bounce", zh="回合时间轴",
        line="球的飞行轨迹压在剪辑时间轴上，高亮的那一段就是留下的回合。",
        pros="直接对应界面本身（时间轴 + 回合），信息量最大。",
        cons="元素最多，超过 32px 才开始舒服；做成图标要简化。"),
    "c4-cut-ball": dict(
        title="Cut Ball", zh="切片球",
        line="球被切开、两半错位，切面留一道青柠边——最字面的「cut」。",
        pros="图形语言最当代，做徽标/贴纸/动效都很好用。",
        cons="需要解释才看得出「球」；偏抽象。"),
    "c5-classic-serve": dict(
        title="Classic Serve", zh="经典发球",
        line="球拍 + 球 + 虚线飞行轨迹，是这个品类最不需要解释的组合。",
        pros="一眼就懂是乒乓；对普通用户最安全。",
        cons="同类产品用得多，个性最弱；小尺寸元素会糊。"),
    "c6-type-slash": dict(
        title="Type Slash", zh="字里带刀",
        line="整个字标被一条斜切带穿过，切面泛青柠光——剪辑感写在名字里。",
        pros="不用解释图标，信息全在字上；做标题、海报、启动画面很帅。",
        cons="不能当独立图标用，必须配一个符号版。"),
}


def gallery():
    cards = []
    for name, meta in META.items():
        icon = f"svg/{name}-icon.svg"
        lock = f"svg/{name}-lockup.svg"
        cards.append(f"""
  <section class="card{ ' selected' if name == SEL else ''}">
    <div class="head">
      <span class="idx">{name.split('-')[0].upper()}</span>
      <h2>{meta['title']}</h2><em>{meta['zh']}</em>
      {'<span class="sel">已选定</span>' if name == SEL else ''}
    </div>
    <div class="stage">
      <div class="plate big"><img src="{icon}" alt="{meta['title']}"></div>
      <div class="side">
        <div class="plate sm"><img src="{icon}" alt=""></div>
        <div class="plate xs"><img src="{icon}" alt=""></div>
        <div class="plate fav"><img src="{icon}" alt=""></div>
      </div>
    </div>
    <img class="lockup" src="{lock}" alt="{meta['title']} 横版组合">
    <p class="line">{meta['line']}</p>
    <ul><li class="pro">{meta['pros']}</li><li class="con">{meta['cons']}</li></ul>
  </section>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RallyCut · Logo 候选</title>
<style>
  :root {{
    --ink:#111417; --panel:#191d20; --line:#2a3033; --lime:#c2ec94;
    --text:#e6e8e7; --muted:#838c8d; --mono:"SFMono-Regular",Menlo,Consolas,monospace;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--ink); color:var(--text);
    font:15px/1.6 -apple-system,"SF Pro Text","Helvetica Neue",sans-serif; }}
  header {{ padding:56px 40px 24px; border-bottom:1px solid var(--line); }}
  h1 {{ margin:0; font-size:30px; letter-spacing:-.6px; }}
  h1 span {{ color:var(--lime); }}
  header p {{ margin:10px 0 0; color:var(--muted); max-width:62ch; }}
  .meta {{ margin-top:18px; display:flex; gap:10px; flex-wrap:wrap; font-family:var(--mono); font-size:11px;
    letter-spacing:.12em; text-transform:uppercase; color:var(--muted); }}
  .meta b {{ color:var(--lime); font-weight:600; }}
  .grid {{ display:grid; gap:1px; background:var(--line); grid-template-columns:repeat(auto-fit,minmax(430px,1fr)); }}
  .card {{ background:var(--ink); padding:28px 30px 30px; }}
  .head {{ display:flex; align-items:baseline; gap:10px; margin-bottom:20px; }}
  .idx {{ font-family:var(--mono); font-size:11px; color:var(--lime); letter-spacing:.14em;
    border:1px solid var(--line); border-radius:4px; padding:2px 6px; }}
  .head h2 {{ margin:0; font-size:18px; letter-spacing:-.2px; }}
  .head em {{ color:var(--muted); font-style:normal; font-size:13px; }}
  .sel {{ margin-left:auto; font-family:var(--mono); font-size:10.5px; letter-spacing:.14em;
    color:#1a2718; background:var(--lime); border-radius:4px; padding:3px 7px; }}
  .card.selected {{ box-shadow:inset 0 0 0 1px rgba(194,236,148,.45); }}
  .card.selected h2 {{ color:var(--lime); }}
  .stage {{ display:flex; gap:12px; align-items:stretch; }}
  .plate {{ background:var(--panel); border:1px solid var(--line); border-radius:16px;
    display:grid; place-items:center; }}
  .plate img {{ display:block; width:100%; height:100%; object-fit:contain; }}
  .big {{ flex:1; aspect-ratio:1; padding:26px; border-radius:22px; }}
  .side {{ display:flex; flex-direction:column; gap:12px; }}
  .sm {{ width:76px; height:76px; padding:10px; border-radius:14px; }}
  .xs {{ width:76px; height:42px; padding:6px 10px; border-radius:10px; }}
  .fav {{ width:76px; height:42px; padding:6px 10px; border-radius:10px; background:#0b0e10; }}
  .lockup {{ width:100%; margin-top:18px; background:var(--panel); border:1px solid var(--line);
    border-radius:12px; padding:6px; }}
  .line {{ color:#c9d0cd; margin:18px 0 12px; }}
  ul {{ margin:0; padding:0; list-style:none; font-size:13.5px; }}
  li {{ padding-left:18px; position:relative; color:var(--muted); }}
  li::before {{ position:absolute; left:0; font-family:var(--mono); }}
  .pro::before {{ content:"+"; color:var(--lime); }}
  .con::before {{ content:"−"; color:#efb8a9; }}
  footer {{ padding:34px 40px 60px; border-top:1px solid var(--line); color:var(--muted); font-size:13px; }}
  code {{ font-family:var(--mono); color:var(--lime); background:#0b0e10; padding:1px 5px; border-radius:4px; }}
</style></head>
<body>
<header>
  <h1>RallyCut <span>logo 候选</span></h1>
  <p>沿用现有应用图标的调性：深色底 <code>#111417</code> + 青柠 <code>#c2ec94</code> + 奶白 <code>#f3f7ee</code>。
  六个方向：两个说「球」、两个说「切」、一个说「时间轴」、一个只在字上做文章。</p>
  <div class="meta"><span>全部纯路径 SVG，无 mask / clipPath / 位图</span>
  <span>尺寸 <b>240×240</b></span><span>锁定词标 <b>660×200</b></span></div>
</header>
<div class="grid">{''.join(cards)}
</div>
<footer>
  由 <code>generate.py</code> 生成：改几何后重跑即可覆盖 <code>svg/</code>。
  词标暂用系统字体渲染，定稿后需转成轮廓路径；浅底版 / 单色版也等定稿再补。
</footer>
</body></html>"""
    (OUT.parent / "index.html").write_text(html)


gallery()
print("wrote", len(list(OUT.glob("*.svg"))), "svg files + index.html")

# ------------------------------------------------------------------ preview png
def preview():
    """One-image contact sheet: design/logo/preview.png (needs rsvg-convert)."""
    import shutil, subprocess
    if not shutil.which("rsvg-convert"):
        print("skip preview.png: rsvg-convert not found")
        return
    cells = []
    order = list(META.items())
    for i, (name, meta) in enumerate(order):
        svg = (OUT / f"{name}-icon.svg").read_text()
        inner = svg[svg.index(">", svg.index("<svg")) + 1:].rsplit("</svg>", 1)[0]
        vb = svg.split('viewBox="', 1)[1].split('"', 1)[0].split()
        w, h = float(vb[2]), float(vb[3])
        sc = min(150 / w, 150 / h)
        col, row = i % 3, i // 3
        x, y = col * 380 + 40, row * 320 + 40
        cells.append(
            f'<g transform="translate({x} {y})">'
            f'<rect width="320" height="250" rx="20" fill="#191d20" stroke="#2a3033"/>'
            f'<g transform="translate({(320 - w * sc) / 2} {14 + (178 - h * sc) / 2}) scale({sc})">{inner}</g>'
            f'<text x="20" y="226" font-family="{FONT}" font-size="17" font-weight="700" '
            f'fill="#e6e8e7">{meta["title"]}<tspan font-size="14" font-weight="400" '
            f'fill="#838c8d" dx="10">{meta["zh"]}</tspan></text>'
            f'</g>')
    sheet = (f'<svg xmlns="http://www.w3.org/2000/svg" width="1180" height="680">'
             f'<rect width="1180" height="680" fill="#111417"/>{"" .join(cells)}</svg>')
    tmp = OUT.parent / ".preview.svg"
    tmp.write_text(sheet)
    subprocess.run(["rsvg-convert", "-w", "1180", str(tmp),
                    "-o", str(OUT.parent / "preview.png")], check=True)
    tmp.unlink()
    print("wrote preview.png")


preview()


# ------------------------------------------------------- chosen logo delivery
MARK_FONT = "Avenir Next"
# tight content box of the mark inside its 240x240 canvas (see c3())
MARK_BOX = (20, 70, 190, 110)


def tight(mark_svg_body, width, cx, cy):
    """Centre the mark's content box on (cx, cy) at the requested width."""
    bx, by, bw, bh = MARK_BOX
    s = width / bw
    tx, ty = cx - (bx + bw / 2) * s, cy - (by + bh / 2) * s
    return f'<g transform="translate({tx:.2f} {ty:.2f}) scale({s:.4f})">\n{mark_svg_body}\n</g>'


def deliverables():
    """Write the chosen mark: mark, lockup, mono variants, app icon."""
    root = OUT.parent
    final = root / "final"
    final.mkdir(exist_ok=True)

    def svg(vb, body, w, h, label):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w}" height="{h}" '
                f'role="img" aria-label="{label}">\n{body}\n</svg>\n')

    (final / "rallycut-mark.svg").write_text(
        svg("0 0 240 240", c3(), 240, 240, "RallyCut mark"))
    (final / "rallycut-mark-mono-lime.svg").write_text(
        svg("0 0 240 240", c3_body(bars_color=LIME, ball=LIME, arc=LIME), 240, 240,
            "RallyCut mark, single lime"))
    (final / "rallycut-mark-mono-ink.svg").write_text(
        svg("0 0 240 240", c3_body(bars_color=INK, ball=INK, arc=INK), 240, 240,
            "RallyCut mark, single ink"))

    # horizontal lockup: mark + Avenir Next wordmark (the app's UI face)
    word = (f'<text x="206" y="104" font-family="{MARK_FONT}" font-size="52" font-weight="700" '
            f'letter-spacing="-1.5" fill="{CREAM}">Rally<tspan fill="{LIME}">Cut</tspan></text>')
    tag = (f'<text x="210" y="134" font-family="{MARK_FONT}" font-size="13.5" font-weight="500" '
           f'letter-spacing="2" fill="#8FA2AB">让每个好球，留下来</text>')
    (final / "rallycut-logo.svg").write_text(svg(
        "0 0 560 160",
        f'  {tight(c3(), 168, 100, 80)}\n  {word}\n  {tag}',
        560, 160, "RallyCut logo"))

    # app icon: ink plate + centred mark (Wails reads build/appicon.png)
    plate = (f'  <rect width="1024" height="1024" rx="225" fill="{INK}"/>\n'
             f'  {tight(c3(), 760, 512, 512)}')
    (final / "rallycut-appicon.svg").write_text(
        svg("0 0 1024 1024", plate, 1024, 1024, "RallyCut app icon"))

    import shutil, subprocess
    if shutil.which("rsvg-convert"):
        for size in (1024, 512, 256, 128, 64):
            subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size),
                            str(final / "rallycut-appicon.svg"),
                            "-o", str(final / f"rallycut-appicon-{size}.png")], check=True)
    print("wrote", len(list(final.iterdir())), "files to", final)


deliverables()
