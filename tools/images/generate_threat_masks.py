#!/usr/bin/env python3
"""Generate 1-bit monochrome threat masks for HTRAM GD32 SPI Flash."""

from pathlib import Path

from tools.images.make_mask import build

REPO_ROOT = Path(__file__).resolve().parents[2]
IMG_DIR = REPO_ROOT / "esphome/images"
IMG_DIR.mkdir(parents=True, exist_ok=True)

THREAT_SPECS = {
    # Realistic M777 155mm towed howitzer side profile:
    # - Long low-slung rear trail legs with ground spade on the left
    # - Central carriage with road wheel + hydro-pneumatic recoil/recuperator cylinders
    # - Long 39-caliber barrel elevated at ~32 deg with signature double-baffle muzzle brake
    "threat_artillery": (
        34,
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 100" width="160" height="100">
  <!-- Long 155mm main barrel (elevated ~32 deg) -->
  <polygon points="56,54 142,10 146,17 60,61" fill="#000000"/>
  <!-- Upper recuperator / recoil cylinder housing along lower/upper barrel -->
  <polygon points="52,46 102,21 106,29 56,54" fill="#000000"/>
  <!-- Lower cradle / recoil cylinder under barrel -->
  <polygon points="62,60 108,36 111,43 65,67" fill="#000000"/>
  <!-- Signature M777 double-baffle muzzle brake + tow lug at tip -->
  <polygon points="138,7 152,0 158,12 144,19" fill="#000000"/>
  <polygon points="145,4 150,2 155,11 150,14" fill="#FFFFFF"/>
  <polygon points="140,9 144,7 148,15 144,17" fill="#FFFFFF"/>
  <polygon points="136,8 156,18 152,23 133,13" fill="#000000"/>
  <!-- Breech block, trunnion & elevation mechanism -->
  <polygon points="38,48 64,42 70,68 42,72" fill="#000000"/>
  <!-- Gunner sight / shield detail -->
  <polygon points="46,36 58,34 60,46 46,48" fill="#000000"/>
  <!-- Rear split trail leg extending low to the left + rear ground spade -->
  <polygon points="44,68 8,86 10,94 50,76" fill="#000000"/>
  <polygon points="2,80 14,82 14,98 2,98" fill="#000000"/>
  <!-- Front stabilizer outrigger leg extending right-down -->
  <polygon points="66,70 96,88 92,95 60,76" fill="#000000"/>
  <rect x="88" y="90" width="16" height="7" fill="#000000"/>
  <!-- Main road wheel (with white rim gap and solid hub) -->
  <circle cx="58" cy="76" r="20" fill="#FFFFFF"/>
  <circle cx="58" cy="76" r="17" fill="#000000"/>
  <circle cx="58" cy="76" r="8" fill="#FFFFFF"/>
  <circle cx="58" cy="76" r="4" fill="#000000"/>
</svg>""",
    ),
    # Urban fighting: tactical crosshair reticle
    "threat_urban": (
        40,
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <circle cx="50" cy="50" r="40" fill="#000000"/>
  <circle cx="50" cy="50" r="30" fill="#FFFFFF"/>
  <rect x="45" y="2" width="10" height="26" fill="#000000"/>
  <rect x="45" y="72" width="10" height="26" fill="#000000"/>
  <rect x="2" y="45" width="26" height="10" fill="#000000"/>
  <rect x="72" y="45" width="26" height="10" fill="#000000"/>
  <circle cx="50" cy="50" r="9" fill="#000000"/>
</svg>""",
    ),
    # Chemical threat: laboratory flask with toxic bubbles / vapor
    "threat_chemical": (
        40,
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <path d="M36 8 L64 8 L64 16 L58 16 L58 34 L86 78 C90 86 84 94 75 94 L25 94 C16 94 10 86 14 78 L42 34 L42 16 L36 16 Z" fill="#000000"/>
  <polygon points="47,36 25,70 75,70 53,36" fill="#FFFFFF"/>
  <circle cx="42" cy="58" r="5" fill="#000000"/>
  <circle cx="58" cy="62" r="6" fill="#000000"/>
  <circle cx="50" cy="46" r="4" fill="#000000"/>
</svg>""",
    ),
    # Nuclear / radiation threat: standard ISO radiation trefoil with crisp inner gap
    "threat_nuclear": (
        40,
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <path d="M50 50 L26 8 A48 48 0 0 1 74 8 Z" fill="#000000"/>
  <path d="M50 50 L98 50 A48 48 0 0 1 74 92 Z" fill="#000000"/>
  <path d="M50 50 L26 92 A48 48 0 0 1 2 50 Z" fill="#000000"/>
  <circle cx="50" cy="50" r="20" fill="#FFFFFF"/>
  <circle cx="50" cy="50" r="10" fill="#000000"/>
</svg>""",
    ),
    # Explosion: asymmetric detonation burst with hollow shockwave core
    "threat_explosion": (
        40,
        """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <polygon points="48,2 58,24 88,6 72,34 98,44 74,56 94,84 62,72 52,98 38,72 10,90 26,58 2,46 28,34 12,10 40,26" fill="#000000"/>
  <polygon points="49,26 55,39 70,30 61,44 74,50 61,57 68,70 54,62 50,75 43,62 28,70 37,56 24,49 38,43 30,30 44,39" fill="#FFFFFF"/>
</svg>""",
    ),
}


def generate_all() -> dict[str, tuple[int, int]]:
    results: dict[str, tuple[int, int]] = {}
    for name, (target_h, svg_content) in THREAT_SPECS.items():
        svg_path = IMG_DIR / f"{name}.svg"
        png_path = IMG_DIR / f"{name}_mask.png"
        svg_path.write_text(svg_content, encoding="utf-8")
        mask = build(str(svg_path), height=target_h)
        mask.save(png_path)
        results[name] = mask.size
        print(f"Generated {png_path.name}: {mask.size[0]}x{mask.size[1]} px")
    return results


if __name__ == "__main__":
    generate_all()
