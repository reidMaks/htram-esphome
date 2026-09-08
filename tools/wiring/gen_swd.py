"""Generate docs/wiring/swd.svg - pictorial SWD hookup drawn over the real board photo."""
import base64, io, os
from PIL import Image
import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import pico as picolib
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = str(ROOT / 'docs')
(ROOT / 'docs' / 'wiring').mkdir(parents=True, exist_ok=True)

SRC = DOCS + '/mainboard-back.jpeg'
OUT = str(ROOT / 'docs' / 'wiring' / 'swd.svg')

full = Image.open(SRC).rotate(180, expand=True)          # silkscreen upright; 4032x3024
FW, FH = full.size

TP16 = (1845, 1205)      # PA14 / SWCLK   (centres detected from the copper)
TP17 = (2328, 1187)      # PA13 / SWDIO
ZOOM = (1660, 1040, 2500, 1355)

FONTS = "Inter, 'Segoe UI', Helvetica, Arial, 'DejaVu Sans', sans-serif"
# wire colours = the ones actually soldered to the Pico on the bench
C = {'clk': '#2f7fd0', 'dio': '#2e9e5b', 'gnd': '#1c1f22',
     'ink': '#0f1720', 'mute': '#5b6875', 'line': '#c8d0d8'}



def _ink(fill):
    """Dark text on light plates (yellow), white on dark ones."""
    r, g, b = (int(fill[i:i+2], 16) for i in (1, 3, 5))
    return '#1a1d20' if (0.299*r + 0.587*g + 0.114*b) > 165 else '#ffffff'


def embed(img, w, q=82):
    img = img.resize((w, round(img.height * w / img.width)), Image.LANCZOS).convert('RGB')
    buf = io.BytesIO(); img.save(buf, 'JPEG', quality=q, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- layout ----
W, H = 1660, 1250
PX, PY, PW = 40, 96, 940
PH = round(FH * PW / FW); sc = PW / FW
IX, IW = 40, 940
IY = PY + PH + 52
isc = IW / (ZOOM[2] - ZOOM[0]); IH = round((ZOOM[3] - ZOOM[1]) * isc)
KX, KY, KW = 1176, 236, 230; KH = round(KW * 1875 / 950)
PICO_URI = embed(Image.open(DOCS + '/pico-wired.jpg').crop(picolib.PH_CROP), 560)
PICO_FRAG, PICO_PINS = picolib.photo(KX, KY, KW, PICO_URI)

photo = on_photo = lambda p: (PX + p[0] * sc, PY + p[1] * sc)
inset = on_inset = lambda p: (IX + (p[0] - ZOOM[0]) * isc, IY + (p[1] - ZOOM[1]) * isc)
pico_pin = lambda n: PICO_PINS[n]

s = []; a = s.append


def chip(x, y, text, fill, fg=None, size=19, bold=True, anchor='middle', pad=9):
    fg = fg or _ink(fill)
    """Text on an opaque rounded plate - readable over the photo in any renderer."""
    w = len(text) * size * (0.60 if bold else 0.53) + pad * 2
    ax = {'middle': x - w / 2, 'start': x - pad, 'end': x - w + pad}[anchor]
    a(f'<rect x="{ax:.1f}" y="{y-size*0.80:.1f}" width="{w:.1f}" height="{size*1.28:.1f}" '
      f'rx="{size*0.34:.1f}" fill="{fill}"/>')
    a(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
      f'font-weight="{700 if bold else 400}" fill="{fg}">{text}</text>')


a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
  f'font-family="{FONTS}">')
a('<defs><filter id="sh" x="-40%" y="-40%" width="180%" height="180%">'
  '<feDropShadow dx="0" dy="3" stdDeviation="5" flood-opacity="0.32"/></filter></defs>')
a(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')

# ---------------------------------------------------------------- header ----
a(f'<text x="{PX}" y="46" font-size="30" font-weight="700" fill="{C["ink"]}">'
  'SWD: Pico → GD32</text>')
a(f'<text x="{PX}" y="75" font-size="17" fill="{C["mute"]}">'
  'зворот плати · '
  'етапи <tspan font-weight="700">probe / unlock / flash</tspan> · '
  'паяти на знеструм'
  'леній платі</text>')

# ----------------------------------------------------------- board photo ----
a(f'<image href="{embed(full, 1180)}" x="{PX}" y="{PY}" width="{PW}" height="{PH}"/>')
a(f'<rect x="{PX}" y="{PY}" width="{PW}" height="{PH}" fill="none" stroke="{C["line"]}"/>')

zx0, zy0 = photo((ZOOM[0], ZOOM[1])); zx1, zy1 = photo((ZOOM[2], ZOOM[3]))
a(f'<rect x="{zx0:.1f}" y="{zy0:.1f}" width="{zx1-zx0:.1f}" height="{zy1-zy0:.1f}" '
  'fill="none" stroke="#ffffff" stroke-width="3"/>')
for xa, xb in ((zx0, IX), (zx1, IX + IW)):
    a(f'<path d="M{xa:.1f},{zy1:.1f} L{xb},{IY}" stroke="#ffffff" stroke-width="1.5" '
      'stroke-dasharray="7 6" fill="none" opacity="0.55"/>')

# ----------------------------------------------------------------- inset ----
a(f'<text x="{IX}" y="{IY-14}" font-size="15" font-weight="600" fill="{C["mute"]}">'
  'збільшено — обидв'
  'і точки поряд, між '
  'ними ~9.5 мм</text>')
a(f'<image href="{embed(full.crop(ZOOM), 1180)}" x="{IX}" y="{IY}" width="{IW}" height="{IH}"/>')
a(f'<rect x="{IX}" y="{IY}" width="{IW}" height="{IH}" fill="none" stroke="#ffffff" stroke-width="3"/>')
for p, col, nm in ((TP16, C['clk'], 'TP16 · PA14 · SWCLK'),
                   (TP17, C['dio'], 'TP17 · PA13 · SWDIO')):
    ix, iy = inset(p)
    a(f'<circle cx="{ix:.1f}" cy="{iy:.1f}" r="34" fill="none" stroke="{col}" stroke-width="5"/>')
    chip(ix, iy - 56, nm, col, size=18)

# ------------------------------------------------------------------ Pico ----
a('<g filter="url(#sh)">')
for _f in PICO_FRAG:
    a(_f)
a('</g>')
a(f'<text x="{KX + KW/2}" y="{KY-46}" text-anchor="middle" font-size="15" font-weight="600" '
  f'fill="{C["mute"]}">USB → хост</text>')

for n, nm, col in ((8, 'GND', C['gnd']), (4, 'GP2', C['clk']), (5, 'GP3', C['dio'])):
    px, py = pico_pin(n)
    a(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="15" fill="none" stroke="{col}" stroke-width="4"/>')
    a(f'<text x="{KX+KW+20}" y="{py+6:.1f}" font-size="17" font-weight="700" fill="{C["ink"]}">'
      f'{nm}<tspan font-weight="400" fill="{C["mute"]}"> · pin {n}</tspan></text>')

# ----------------------------------------------------------------- wires ----
def wire(p0, p1, col, label, bow):
    (x0, y0), (x1, y1) = p0, p1
    mx = (x0 + x1) / 2
    d = f'M{x0:.1f},{y0:.1f} C{mx:.1f},{y0+bow:.1f} {mx:.1f},{y1+bow:.1f} {x1:.1f},{y1:.1f}'
    a(f'<path d="{d}" fill="none" stroke="#000000" stroke-opacity="0.30" stroke-width="12" stroke-linecap="round"/>')
    a(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="7" stroke-linecap="round"/>')
    chip(mx, (y0 + y1) / 2 + bow * 0.60 + 6, label, col, size=18)

wire(photo(TP16), (pico_pin(4)[0], pico_pin(4)[1]), C['clk'], 'SWCLK', -132)
wire(photo(TP17), (pico_pin(5)[0], pico_pin(5)[1]), C['dio'], 'SWDIO',  128)
for p, col in ((TP16, C['clk']), (TP17, C['dio'])):
    x, y = photo(p)
    a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="13" fill="none" stroke="{col}" stroke-width="4"/>')
    a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{col}"/>')

# GND - stops in the gutter on purpose: the exact pad is not established
gx, gy = PX + PW + 74, pico_pin(8)[1] + 92
wire((gx, gy), (pico_pin(8)[0], pico_pin(8)[1]), C['gnd'], '', 0)
chip(gx, gy, 'GND · пад 38 ESP', C['gnd'], size=18)

# ------------------------------------------------------------- side table ---
TX, TY = KX, KY + KH + 44
a(f'<text x="{TX}" y="{TY}" font-size="19" font-weight="700" fill="{C["ink"]}">'
  'Розводка</text>')
for i, (l, r, col) in enumerate((('GP2 · синій · pin 4', 'TP16', C['clk']),
                                 ('GP3 · зелений · pin 5', 'TP17', C['dio']),
                                 ('GND · чорний · pin 8', 'GND', C['gnd']))):
    y = TY + 38 + i * 34
    a(f'<rect x="{TX}" y="{y-13}" width="7" height="17" rx="2" fill="{col}"/>')
    a(f'<text x="{TX+17}" y="{y}" font-size="17" fill="{C["ink"]}">{l} → '
      f'<tspan font-weight="700">{r}</tspan></text>')

# ------------------------------------------------------------------ notes ---
def note(x, y, w, h, bg, br, fg, lines):
    a(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{bg}" stroke="{br}"/>')
    for j, (t, bold) in enumerate(lines):
        a(f'<text x="{x+18}" y="{y+30+j*23}" font-size="16" '
          f'font-weight="{700 if bold else 400}" fill="{fg}">{t}</text>')

NW = W - (IX + IW + 38) - 40
note(IX + IW + 38, IY + 128, NW, 104, '#fff6e6', '#e0b46c', '#7a5312',
     [('TP18 = NRST', True),
      ('потрібен лише дл'
       'я порятунку —', False),
      ('притиснути до GND '
       'пінцетом.', False)])
note(IX + IW + 38, IY + 250, NW, 104, '#eef4fa', '#a9c3dc', '#274b6d',
     [('GND = пад 38 ESP', True),
      ('він з іншого боку плати,', False),
      ('на стороні компонентів.', False)])

a(f'<rect x="{PX}" y="{H-48}" width="{W-80}" height="36" rx="8" fill="#fdecec" stroke="#e0a3a3"/>')
a(f'<text x="{PX+16}" y="{H-24}" font-size="16" fill="#8a2b2b">'
  '<tspan font-weight="700">Порядок увім'
  'кнення:</tspan> спершу жи'
  'влення плати (заря'
  'дка, не цей ПК) → пер'
  'еконатись що прац'
  'ює → лише тоді USB Pico '
  'у комп’ютер.</text>')
a('</svg>')

open(OUT, 'w').write('\n'.join(s))
print('wrote', OUT, round(os.path.getsize(OUT) / 1024), 'KB')
