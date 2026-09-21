"""Векторные SVG-иконки ПРОРЫВа.

Каждая иконка описана примитивами в сетке 24x24 — из одного описания
рендерится PNG в память (для tkinter) и записывается .svg файл
(assets/icons/*.svg — дизайн-исходники).
Монохром: глиф рисуется заданным цветом на прозрачном фоне.
"""
from __future__ import annotations
from pathlib import Path

try:
    from PIL import Image, ImageDraw
    _PIL = True
except ImportError:
    _PIL = False

GRID = 24

# ---------------- описания иконок ----------------
# Примитивы: ("rect", x0,y0,x1,y1)
#            ("rrect", x0,y0,x1,y1, r)
#            ("poly", [(x,y),...])
#            ("ellipse", x0,y0,x1,y1, width)      # только контур
#            ("disc", x0,y0,x1,y1)                # залитый эллипс
#            ("arc", x0,y0,x1,y1, start, end, width)  # дуга, градусы PIL
#            ("bar", x0,y0,x1,y1, r)              # залитый скруглённый столбец

ICONS: dict[str, list[tuple]] = {
    "download": [
        ("poly", [(5.5, 10.5), (12, 17.0), (18.5, 10.5), (14.9, 10.5), (14.9, 9.0)]),
        ("rect", (10.7, 3.0, 13.3, 12.0)),
        ("rrect", (4.5, 19.0, 19.5, 21.4, 1.0)),
    ],
    "play": [
        ("poly", [(8.5, 5.5), (18.5, 12.0), (8.5, 18.5)]),
    ],
    "pause": [
        ("rrect", (7.5, 5.5, 11.0, 18.5, 1.2),),
        ("rrect", (13.0, 5.5, 16.5, 18.5, 1.2),),
    ],
    "stop": [
        ("rrect", (6.5, 6.5, 17.5, 17.5, 2.5),),
    ],
    "spark": [  # звезда автоподбора
        ("poly", [(11, 2.5), (13.2, 8.8), (19.5, 11), (13.2, 13.2),
                  (11, 19.5), (8.8, 13.2), (2.5, 11), (8.8, 8.8)]),
        ("poly", [(18.2, 3.2), (19.0, 5.4), (21.2, 6.2), (19.0, 7.0),
                  (18.2, 9.2), (17.4, 7.0), (15.2, 6.2), (17.4, 5.4)]),
    ],
    "power": [  # кольцо с разрывом сверху + столбец
        ("arc", (6.0, 7.5, 18.0, 19.5, 305.0, 595.0, 2.4)),
        ("bar", (10.9, 3.0, 13.1, 10.5, 1.1)),
    ],
}

LOGO_BG = "#0B0B0C"  # цвет подложки шапки (для «прорыва» в плашке)


# ---------------- рендер в PIL ----------------

def render(name: str, size: int = 24, color=(255, 255, 255, 255)) -> "Image.Image":
    if not _PIL:
        raise RuntimeError("Нужен pillow: pip install pillow")
    shapes = ICONS[name]
    sup = 4
    big = size * sup
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = big / GRID

    def pts(p):
        return [(x * k, y * k) for x, y in p]

    for s in shapes:
        kind = s[0]
        if kind == "rect":
            (x0, y0, x1, y1) = s[1]
            d.rectangle([x0 * k, y0 * k, x1 * k, y1 * k], fill=color)
        elif kind in ("rrect", "bar"):
            (x0, y0, x1, y1, r) = s[1]
            d.rounded_rectangle([x0 * k, y0 * k, x1 * k, y1 * k], radius=r * k, fill=color)
        elif kind == "poly":
            d.polygon(pts(s[1]), fill=color)
        elif kind == "ellipse":
            (x0, y0, x1, y1, w) = s[1]
            d.ellipse([x0 * k, y0 * k, x1 * k, y1 * k], outline=color, width=max(1, int(w * k)))
        elif kind == "disc":
            (x0, y0, x1, y1) = s[1]
            d.ellipse([x0 * k, y0 * k, x1 * k, y1 * k], fill=color)
        elif kind == "arc":
            (x0, y0, x1, y1, a0, a1, w) = s[1]
            d.arc([x0 * k, y0 * k, x1 * k, y1 * k], start=a0, end=a1,
                  fill=color, width=max(1, int(w * k)))
    return img.resize((size, size), Image.LANCZOS)


def render_logo(size: int = 96) -> "Image.Image":
    """Плашка-логотип: белая скруглённая плитка, чёрная «П», сверху вырез-прорыв."""
    if not _PIL:
        raise RuntimeError("Нужен pillow: pip install pillow")
    sup = 4
    big = size * sup
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    k = big / 96.0
    white = (255, 255, 255, 255)
    black = (0, 0, 0, 255)
    hole = (11, 11, 12, 255)  # цвет шапки — «прорыв» сквозь плитку
    d.rounded_rectangle([6 * k, 6 * k, 90 * k, 90 * k], radius=22 * k, fill=white)
    # буква П из трёх брусков
    d.rectangle([28 * k, 34 * k, 38 * k, 68 * k], fill=black)
    d.rectangle([58 * k, 34 * k, 68 * k, 68 * k], fill=black)
    d.rectangle([28 * k, 34 * k, 68 * k, 44 * k], fill=black)
    # вырез сверху по центру
    d.rectangle([43 * k, 6 * k, 53 * k, 20 * k], fill=hole)
    return img.resize((size, size), Image.LANCZOS)


# ---------------- экспорт в SVG ----------------

def _svg_primitives(shapes, color: str) -> str:
    out = []
    for s in shapes:
        kind = s[0]
        if kind == "rect":
            (x0, y0, x1, y1) = s[1]
            out.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="{color}"/>')
        elif kind in ("rrect", "bar"):
            (x0, y0, x1, y1, r) = s[1]
            out.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="{r}" fill="{color}"/>')
        elif kind == "poly":
            p = " ".join(f"{x},{y}" for x, y in s[1])
            out.append(f'<polygon points="{p}" fill="{color}"/>')
        elif kind == "ellipse":
            (x0, y0, x1, y1, w) = s[1]
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
            out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="{color}" stroke-width="{w}"/>')
        elif kind == "disc":
            (x0, y0, x1, y1) = s[1]
            cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
            out.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{color}"/>')
        elif kind == "arc":
            # дуга power: разрыв сверху; PIL start=305 end=595 -> SVG path
            import math
            (x0, y0, x1, y1, a0, a1, w) = s[1]
            cx, cy, r = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2
            # начало a0=305° (верх-справа), конец 595°=235° (верх-слева), длинная дуга по часовой
            x_1, y_1 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
            a1n = a1 % 360
            x_2, y_2 = cx + r * math.cos(math.radians(a1n)), cy + r * math.sin(math.radians(a1n))
            out.append(f'<path d="M {x_1:.2f} {y_1:.2f} A {r:.2f} {r:.2f} 0 1 1 {x_2:.2f} {y_2:.2f}" '
                       f'fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round"/>')
    return "\n  ".join(out)


def export_svg(name: str, path: Path, color: str = "#FFFFFF") -> Path:
    body = _svg_primitives(ICONS[name], color)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
           f'width="24" height="24">\n  {body}\n</svg>\n')
    path.write_text(svg, encoding="utf-8")
    return path


def export_logo_svg(path: Path) -> Path:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" width="96" height="96">\n'
           f'  <rect x="6" y="6" width="84" height="84" rx="22" fill="#FFFFFF"/>\n'
           f'  <rect x="28" y="34" width="10" height="34" fill="#000000"/>\n'
           f'  <rect x="58" y="34" width="10" height="34" fill="#000000"/>\n'
           f'  <rect x="28" y="34" width="40" height="10" fill="#000000"/>\n'
           f'  <rect x="43" y="6" width="10" height="14" fill="{LOGO_BG}"/>\n'
           f'</svg>\n')
    path.write_text(svg, encoding="utf-8")
    return path


def build_assets(assets_dir: Path | str = "assets") -> list[Path]:
    """Записать все .svg файлы в assets/icons/. Вызывать при разработке."""
    d = Path(assets_dir) / "icons"
    d.mkdir(parents=True, exist_ok=True)
    made = []
    for name in ICONS:
        made.append(export_svg(name, d / f"{name}.svg"))
    made.append(export_logo_svg(d / "logo.svg"))
    return made


if __name__ == "__main__":
    import sys
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "assets"
    for p in build_assets(base):
        print("SVG:", p)
