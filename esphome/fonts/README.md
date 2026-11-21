# Fonts

The bundled font files and their licences:

| File | Upstream | Licence |
| --- | --- | --- |
| `NotoSans-Regular.ttf` | [Noto](https://github.com/notofonts/notofonts.github.io), Google | SIL OFL 1.1 — [`LICENSE-Noto-OFL.txt`](LICENSE-Noto-OFL.txt) |
| `DejaVuSans-ExtraLight.ttf` | [DejaVu](https://dejavu-fonts.github.io/) | Bitstream Vera — [`LICENSE-DejaVu.txt`](LICENSE-DejaVu.txt) |
| `DejaVuSans-ExtraLight-Oblique.ttf` | generated here from the file above | Bitstream Vera, same file |
| `JetBrainsMono-Variable.ttf` | [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) | SIL OFL 1.1 — [`LICENSE-JetBrainsMono-OFL.txt`](LICENSE-JetBrainsMono-OFL.txt) |

Both licences are permissive and both require that their notice travel with the
font, which is what those two files are for. Keep them next to the `.ttf`s.

The oblique is the only font we modify. ESPHome renders fonts from the TTF at build
time and LVGL cannot shear text, so a slanted clock needs a slanted file:

```bash
.venv/bin/python tools/fonts/make_oblique.py \
    esphome/fonts/DejaVuSans-ExtraLight.ttf \
    esphome/fonts/DejaVuSans-ExtraLight-Oblique.ttf --angle 12 --tight
```

The Bitstream Vera licence allows the modification on one condition — the
result must not be named with the words "Bitstream" or "Vera". `DejaVuSans-
ExtraLight-Oblique` satisfies that. If you re-derive it under some other name,
check the same rule before you commit the result.
