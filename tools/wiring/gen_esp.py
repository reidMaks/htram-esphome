"""Generate the two ESP-side wiring diagrams over the real board photo."""
import base64, io, os
from PIL import Image
import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import pico as picolib
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
DOCS = str(ROOT / 'docs')
(ROOT / 'docs' / 'wiring').mkdir(parents=True, exist_ok=True)

SRC = DOCS + '/mainboard-front-v2.jpg'
OUTDIR = str(ROOT / 'docs' / 'wiring')

full = Image.open(SRC).rotate(180, expand=True)      # 1500x2000, silkscreen upright

# castellation centres, measured off the photo (14-pad edge row, 38 -> 25)
PX_X = 1381.0
_GAPS = [172, 220, 257, 296, 334, 371, 407, 443, 482, 518, 557, 592, 632, 667, 705]
PADS = {38 - i: (PX_X, (_GAPS[i] + _GAPS[i + 1]) / 2) for i in range(14)}

CROP = (1050, 120, 1462, 790)
FONTS = "Inter, 'Segoe UI', Helvetica, Arial, 'DejaVu Sans', sans-serif"
# wire colours = the ones actually soldered to the Pico on the bench
C = {'tx': '#e3b81f', 'rx': '#e8802a', 'gnd': '#1c1f22', 'tmp': '#8e5bb5',
     'ink': '#0f1720', 'mute': '#5b6875', 'line': '#c8d0d8'}



def _ink(fill):
    """Dark text on light plates (yellow), white on dark ones."""
    r, g, b = (int(fill[i:i+2], 16) for i in (1, 3, 5))
    return '#1a1d20' if (0.299*r + 0.587*g + 0.114*b) > 165 else '#ffffff'


def embed(img, w, q=86):
    img = img.resize((w, round(img.height * w / img.width)), Image.LANCZOS).convert('RGB')
    b = io.BytesIO(); img.save(b, 'JPEG', quality=q, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(b.getvalue()).decode()


IMG_URI = embed(full.crop(CROP), 900)

W, H = 1500, 880
IMX, IMY, IMW = 40, 116, 400
IMH = round(IMW * (CROP[3] - CROP[1]) / (CROP[2] - CROP[0]))
isc = IMW / (CROP[2] - CROP[0])
LBL_X = 540
KX, KY, KW = 640, 162, 230; KH = round(KW * 1875 / 950)
PICO_URI = embed(Image.open(DOCS + '/pico-wired.jpg').crop(picolib.PH_CROP), 560)
PICO_FRAG, PICO_PINS = picolib.photo(KX, KY, KW, PICO_URI)

pad_xy = lambda n: (IMX + (PADS[n][0] - CROP[0]) * isc, IMY + (PADS[n][1] - CROP[1]) * isc)
pico_pin = lambda n: PICO_PINS[n]


def build(fname, title, subtitle, links, gpio0, cross_note, extra):
    s = []; a = s.append

    def chip(x, y, text, fill, size=17, anchor='middle', fg=None):
        fg = fg or _ink(fill)
        w = len(text) * size * 0.60 + 18
        ax = {'middle': x - w / 2, 'start': x - 9, 'end': x - w + 9}[anchor]
        a(f'<rect x="{ax:.1f}" y="{y-size*0.80:.1f}" width="{w:.1f}" height="{size*1.30:.1f}" '
          f'rx="{size*0.34:.1f}" fill="{fill}"/>')
        a(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
          f'font-weight="700" fill="{fg}">{text}</text>')

    a(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
      f'font-family="{FONTS}">')
    a('<defs><filter id="sh" x="-40%" y="-40%" width="180%" height="180%">'
      '<feDropShadow dx="0" dy="3" stdDeviation="5" flood-opacity="0.32"/></filter></defs>')
    a(f'<rect width="{W}" height="{H}" fill="#ffffff"/>')
    a(f'<text x="{IMX}" y="48" font-size="29" font-weight="700" fill="{C["ink"]}">{title}</text>')
    a(f'<text x="{IMX}" y="78" font-size="17" fill="{C["mute"]}">{subtitle}</text>')

    a(f'<image href="{IMG_URI}" x="{IMX}" y="{IMY}" width="{IMW}" height="{IMH}"/>')
    a(f'<rect x="{IMX}" y="{IMY}" width="{IMW}" height="{IMH}" fill="none" stroke="{C["line"]}"/>')
    a(f'<text x="{IMX}" y="{IMY-10}" font-size="14" font-weight="600" fill="{C["mute"]}">'
      'сторона компонентів · ряд уздовж краю плати · 14 падів, 38 зверху</text>')

    # faint tick + number on every pad of the row, so the count is checkable
    for n in sorted(PADS):
        x, y = pad_xy(n)
        hot = n in {l[1] for l in links} or n == gpio0
        if not hot:
            a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="none" stroke="#ffffff" '
              'stroke-width="1.6" opacity="0.75"/>')
            a(f'<text x="{x-14:.1f}" y="{y+4:.1f}" text-anchor="end" font-size="11" '
              'fill="#ffffff" opacity="0.75">{}</text>'.format(n))

    def wire(p0, p1, col, bow, label, dash=None):
        (x0, y0), (x1, y1) = p0, p1
        mx = (x0 + x1) / 2
        d = f'M{x0:.1f},{y0:.1f} C{mx:.1f},{y0+bow:.1f} {mx:.1f},{y1+bow:.1f} {x1:.1f},{y1:.1f}'
        da = f' stroke-dasharray="{dash}"' if dash else ''
        a(f'<path d="{d}" fill="none" stroke="#000000" stroke-opacity="0.28" stroke-width="11" '
          f'stroke-linecap="round"{da}/>')
        a(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="6.5" stroke-linecap="round"{da}/>')
        if label:
            chip(LBL_X, (y0 + y1) / 2 + bow * 0.60 + 5, label, col)

    for (pin, pad, col, bow, label) in links:
        wire(pad_xy(pad), (pico_pin(pin)[0], pico_pin(pin)[1]), col, bow, label.split('|')[0])
        x, y = pad_xy(pad)
        a(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="none" stroke="{col}" stroke-width="4"/>')
        chip(x - 20, y + 5, f'{pad}', col, size=15, anchor='end')

    # GPIO0 -> GND: a held jumper, not a soldered wire
    if gpio0:
        gx, gy = pad_xy(gpio0)
        a(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="12" fill="none" stroke="{C["tmp"]}" '
          'stroke-width="4" stroke-dasharray="5 4"/>')
        chip(gx - 20, gy + 5, f'{gpio0}', C['tmp'], size=15, anchor='end')
        ex = IMX + (1148 - CROP[0]) * isc          # a clear spot on the ESP shield
        ey = IMY + (452 - CROP[1]) * isc
        a(f'<path d="M{gx:.1f},{gy:.1f} C{gx+40:.1f},{gy-30:.1f} {ex+70:.1f},{ey+90:.1f} '
          f'{ex:.1f},{ey:.1f}" fill="none" stroke="{C["tmp"]}" '
          'stroke-width="5" stroke-dasharray="7 5" stroke-linecap="round"/>')
        a(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="13" fill="none" stroke="{C["tmp"]}" '
          'stroke-width="4"/>')
        chip(ex + 4, ey - 26, 'кришка ESP = GND', C['tmp'], size=15)

    a('<g filter="url(#sh)">')
    for _f in PICO_FRAG:
        a(_f)
    a('</g>')
    a(f'<text x="{KX + KW/2}" y="{KY-44}" text-anchor="middle" font-size="14" font-weight="600" '
      f'fill="{C["mute"]}">USB → хост</text>')
    for (pin, pad, col, bow, label) in links:
        px, py = pico_pin(pin)
        a(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="14" fill="none" stroke="{col}" stroke-width="4"/>')

    TX0 = KX + KW + 96
    a(f'<text x="{TX0}" y="{KY+6}" font-size="19" font-weight="700" fill="{C["ink"]}">Розводка</text>')
    for i, (pin, pad, col, bow, label) in enumerate(links):
        y = KY + 44 + i * 46
        a(f'<rect x="{TX0}" y="{y-14}" width="7" height="18" rx="2" fill="{col}"/>')
        a(f'<text x="{TX0+18}" y="{y}" font-size="17" fill="{C["ink"]}">'
          f'<tspan font-weight="700">Pico pin {pin}</tspan> → пад <tspan font-weight="700">{pad}</tspan></text>')
        a(f'<text x="{TX0+18}" y="{y+19}" font-size="14" fill="{C["mute"]}">{label.split("|")[-1]}</text>')

    ny = KY + 44 + len(links) * 46 + 16
    for (bg, br, fg, lines) in extra:
        h = 30 + len(lines) * 22
        a(f'<rect x="{TX0}" y="{ny}" width="{W-TX0-40}" height="{h}" rx="10" fill="{bg}" stroke="{br}"/>')
        for j, (t, b) in enumerate(lines):
            a(f'<text x="{TX0+16}" y="{ny+26+j*22}" font-size="15" '
              f'font-weight="{700 if b else 400}" fill="{fg}">{t}</text>')
        ny += h + 14

    a(f'<rect x="{IMX}" y="{H-52}" width="{W-80}" height="38" rx="8" fill="{cross_note[0]}" '
      f'stroke="{cross_note[1]}"/>')
    a(f'<text x="{IMX+16}" y="{H-27}" font-size="16" fill="{cross_note[2]}">{cross_note[3]}</text>')
    a('</svg>')

    p = os.path.join(OUTDIR, fname)
    open(p, 'w').write('\n'.join(s))
    print('wrote', p, round(os.path.getsize(p) / 1024), 'KB')


build('esp-uart0.svg',
      'UART0: заливка ESPHome в ESP32',
      'етап <tspan font-weight="700">esp</tspan> · перехрестя ПОТРІБНЕ · паяти на знеструмленій платі',
      [(6, 34, C['tx'], -104, 'GP4 · жовтий|GP4 = UART TX → GPIO3 (RXD0)'),
       (7, 35, C['rx'],  104, 'GP5 · помаранч.|GP5 = UART RX → GPIO1 (TXD0)'),
       (8, 38, C['gnd'], -62, 'GND · чорний|GND · чорний · pin 8 → пад 38 (GND модуля)')],
      25,
      ('#eaf6ee', '#a8cdb5', '#1f5c3a',
       '<tspan font-weight="700">Перехрестя тут потрібне:</tspan> Pico виступає хостом, '
       'а не ESP. TX Pico йде на RXD0, RX Pico — на TXD0.'),
      [('#fdecec', '#e0a3a3', '#8a2b2b',
        [('EN не чіпати взагалі', True),
         ('ні замикати, ні смикати.', False)]),
       ('#f6f0fb', '#c9b0de', '#5b3580',
        [('GPIO0 = пад 25', True),
         ('притиснути до GND і тримати — це', False),
         ('і є вхід у download mode. Цілитись', False),
         ('у пін не треба: тисни просто на', False),
         ('металеву кришку ESP, вона земля.', False),
         ('Power-cycle ESP роби кнопкою,', False),
         ('не micro-USB — рейку гейтить GD32.', False)]),
       ('#eef4fa', '#a9c3dc', '#274b6d',
        [('GND: пад 38 або екран micro-USB', True),
         ('док називає екран; пад 38 —', False),
         ('той самий вузол і ближче.', False)])])

build('esp-linkuart.svg',
      'Міжчиповий UART: Pico вдає ESP',
      'етапи <tspan font-weight="700">probe / dump / flash</tspan> · перехрестя НЕ потрібне',
      [(6, 28, C['tx'], -104, 'GP4 · жовтий|GP4 = UART TX → GPIO17 → GD32 PA3 (RX)'),
       (7, 27, C['rx'],  104, 'GP5 · помаранч.|GP5 = UART RX → GPIO16 → GD32 PA2 (TX)'),
       (8, 38, C['gnd'], -62, 'GND · чорний|GND · чорний · pin 8 → пад 38 (GND модуля)')],
      None,
      ('#fdecec', '#e0a3a3', '#8a2b2b',
       '<tspan font-weight="700">НЕ перехрещувати</tspan> — на відміну від етапу esp. Pico тут '
       'заміняє ESP, а перехрестя вже зроблене на боці GD32 (PA3=RX, PA2=TX).'),
      [('#eef4fa', '#a9c3dc', '#274b6d',
        [('Ті самі два дроти, інші пади', True),
         ('з етапу esp вони переїжджають', False),
         ('з пари 34/35 на пару 27/28.', False)]),
       ('#eaf6ee', '#a8cdb5', '#1f5c3a',
        [('ESP не заважає', True),
         ('ESPHome лишає GPIO16/17 входами', False),
         ('(high-Z), конфлікту на лінії немає.', False)]),
       ('#fff6e6', '#e0b46c', '#7a5312',
        [('Альтернатива', True),
         ('можна паяти прямо до ніг GD32', False),
         ('PA2/PA3 — електрично той самий вузол.', False)])])
