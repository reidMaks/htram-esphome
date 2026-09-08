"""A drawn-to-scale Raspberry Pi Pico for the wiring diagrams.

Board is 51.0 x 21.0 mm; the 2x20 headers are on 2.54 mm pitch. Everything else
is cosmetic, but the pin centres this returns are what the wires attach to, so
they follow the real geometry rather than an even split of the outline.
"""

BOARD_L, BOARD_W = 51.0, 21.0
PITCH_MM = 2.54
PAD_INSET_MM = 1.6          # pad centre in from the long edge
N_PER_SIDE = 20

GREEN, GREEN_DK = '#14663f', '#0d4a2d'
GOLD, GOLD_DK = '#d9b45a', '#9c7a2a'
SILVER, SILVER_DK = '#c6ccd2', '#8d959d'
CHIP, CHIP_HI = '#23262a', '#3a3f45'
SILK = '#e8f1ea'


def draw(x, y, w, uid='p'):
    """Vertical Pico, USB at top, top-left corner at (x, y), board width `w` px.

    Returns (svg_fragments, pins) where pins maps physical pin number 1..40 to
    an (x, y) pixel centre. Pin 1 is top-left; the left column runs 1..20 down,
    the right column 21..40 back up, as on the board.
    """
    s = w / BOARD_W                      # px per mm
    h = BOARD_L * s
    a = []

    span = (N_PER_SIDE - 1) * PITCH_MM * s
    y0 = y + (h - span) / 2
    xl, xr = x + PAD_INSET_MM * s, x + w - PAD_INSET_MM * s
    pins = {}
    for i in range(N_PER_SIDE):
        pins[i + 1] = (xl, y0 + i * PITCH_MM * s)                 # 1..20 down the left
        pins[40 - i] = (xr, y0 + i * PITCH_MM * s)                # 40..21 down the right

    a.append(f'<defs>'
             f'<linearGradient id="{uid}pcb" x1="0" y1="0" x2="1" y2="1">'
             f'<stop offset="0" stop-color="#1a7a4c"/><stop offset="1" stop-color="{GREEN}"/>'
             f'</linearGradient>'
             f'<linearGradient id="{uid}usb" x1="0" y1="0" x2="0" y2="1">'
             f'<stop offset="0" stop-color="#e2e7eb"/><stop offset="1" stop-color="{SILVER_DK}"/>'
             f'</linearGradient></defs>')

    # micro-USB shell, poking past the top edge
    uw, uh = 7.6 * s, 5.2 * s
    ux = x + w / 2 - uw / 2
    a.append(f'<rect x="{ux:.1f}" y="{y-uh*0.55:.1f}" width="{uw:.1f}" height="{uh:.1f}" '
             f'rx="{1.0*s:.1f}" fill="url(#{uid}usb)" stroke="{SILVER_DK}" stroke-width="1"/>')
    a.append(f'<rect x="{ux+uw*0.16:.1f}" y="{y-uh*0.40:.1f}" width="{uw*0.68:.1f}" '
             f'height="{uh*0.34:.1f}" rx="{0.5*s:.1f}" fill="#5c646c"/>')

    # board
    a.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
             f'rx="{1.6*s:.1f}" fill="url(#{uid}pcb)" stroke="{GREEN_DK}" stroke-width="1.5"/>')

    # castellations: a gold notch straddling each edge, then the ring pad
    nw, nh = 1.5 * s, 1.9 * s
    for n, (px, py) in pins.items():
        left = n <= N_PER_SIDE
        ex = x if left else x + w
        a.append(f'<rect x="{ex-nw/2:.1f}" y="{py-nh/2:.1f}" width="{nw:.1f}" height="{nh:.1f}" '
                 f'rx="{0.45*s:.1f}" fill="{GOLD}" stroke="{GOLD_DK}" stroke-width="0.8"/>')
    for n, (px, py) in pins.items():
        a.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{0.92*s:.1f}" fill="{GOLD}" '
                 f'stroke="{GOLD_DK}" stroke-width="0.9"/>')
        a.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{0.40*s:.1f}" fill="{GREEN_DK}"/>')

    # BOOTSEL, RP2040, flash, LED, debug header - cosmetic but placed as on the board
    bw = 3.4 * s
    a.append(f'<rect x="{x+w/2-bw/2:.1f}" y="{y+7.4*s:.1f}" width="{bw:.1f}" height="{bw*0.8:.1f}" '
             f'rx="{0.4*s:.1f}" fill="{SILVER}" stroke="{SILVER_DK}"/>')
    a.append(f'<circle cx="{x+w/2:.1f}" cy="{y+7.4*s+bw*0.4:.1f}" r="{0.9*s:.1f}" fill="#6f777e"/>')

    cw = 7.0 * s
    a.append(f'<rect x="{x+w/2-cw/2:.1f}" y="{y+17.5*s:.1f}" width="{cw:.1f}" height="{cw:.1f}" '
             f'rx="{0.5*s:.1f}" fill="{CHIP}" stroke="{CHIP_HI}"/>')
    a.append(f'<circle cx="{x+w/2-cw/2+1.1*s:.1f}" cy="{y+17.5*s+1.1*s:.1f}" r="{0.42*s:.1f}" '
             f'fill="{CHIP_HI}"/>')

    fw, fh = 5.3 * s, 3.3 * s
    a.append(f'<rect x="{x+w/2-fw/2:.1f}" y="{y+28.0*s:.1f}" width="{fw:.1f}" height="{fh:.1f}" '
             f'rx="{0.3*s:.1f}" fill="{CHIP}" stroke="{CHIP_HI}"/>')

    a.append(f'<rect x="{x+w*0.30:.1f}" y="{y+2.1*s:.1f}" width="{1.6*s:.1f}" '
             f'height="{0.9*s:.1f}" rx="{0.2*s:.1f}" fill="#7ee0a0"/>')

    dy = y + h - 3.0 * s
    for k in (-1, 0, 1):
        a.append(f'<circle cx="{x+w/2+k*PITCH_MM*s:.1f}" cy="{dy:.1f}" r="{0.85*s:.1f}" '
                 f'fill="{GOLD}" stroke="{GOLD_DK}" stroke-width="0.8"/>')
        a.append(f'<circle cx="{x+w/2+k*PITCH_MM*s:.1f}" cy="{dy:.1f}" r="{0.36*s:.1f}" '
                 f'fill="{GREEN_DK}"/>')
    a.append(f'<text x="{x+w/2:.1f}" y="{dy-1.6*s:.1f}" text-anchor="middle" '
             f'font-size="{1.05*s:.1f}" fill="{SILK}" opacity="0.7" '
             f'letter-spacing="{0.15*s:.1f}">DEBUG</text>')

    for hx in (x + 5.3 * s, x + w - 5.3 * s):
        for hy in (y + 4.8 * s, y + h - 4.8 * s):
            a.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="{1.05*s:.1f}" fill="{GREEN_DK}" '
                     f'stroke="{GOLD_DK}" stroke-width="{0.35*s:.1f}"/>')

    cx, cy = x + w / 2, y + 38.0 * s
    a.append(f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="{1.42*s:.1f}" '
             f'font-weight="700" fill="{SILK}" opacity="0.88" '
             f'transform="rotate(90 {cx:.1f} {cy:.1f})">Raspberry Pi Pico</text>')
    return a, pins


# --------------------------------------------------------------------------
# The bench Pico, photographed with the harness already soldered on.
# It is the underside, so the labelled column GP0..GP15 is physical pins 1..20.
# Anchor: the two bare gold pads either side of the soldered run are exactly
# 6 pitches apart, which pins the numbering without counting from a board edge.
PH_CROP = (350, 60, 1300, 1935)
PH_PIN_X, PH_PIN1_Y, PH_PITCH = 1035.0, 133.0, 88.9


def photo(x, y, w, uri, uid='pp'):
    """Photographed Pico, top-left at (x, y), crop drawn `w` px wide.

    Returns (svg_fragments, pins) with pins 1..20 of the visible column.
    """
    cw, ch = PH_CROP[2] - PH_CROP[0], PH_CROP[3] - PH_CROP[1]
    s = w / cw
    h = ch * s
    pins = {n: (x + (PH_PIN_X - PH_CROP[0]) * s,
                y + (PH_PIN1_Y + (n - 1) * PH_PITCH - PH_CROP[1]) * s)
            for n in range(1, 21)}
    a = [f'<image href="{uri}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>',
         f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="none" '
         f'stroke="#c8d0d8"/>']
    return a, pins
