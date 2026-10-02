"""Generates the seasonal, holiday and abstract backgrounds in assets/backgrounds/.

Each is a portrait SVG (the wall is 1080x1920) scaled to cover any screen. Colors stay mid-to-dark
and motifs stay faint so white text and the event cards remain easy to read.

    python tools/make_backgrounds.py

To add one, add an entry to BACKGROUNDS and a matching option in dashboard.html (backgroundGroups).
"""
import math
import os

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'backgrounds')


def star_points(outer, inner, points=5):
    pts = []
    for i in range(points * 2):
        r = outer if i % 2 == 0 else inner
        a = math.pi * i / points - math.pi / 2
        pts.append(f'{r * math.cos(a):.1f},{r * math.sin(a):.1f}')
    return ' '.join(pts)


# Motifs drawn around (0, 0), roughly 40px across, in white; the pattern sets their opacity.
HEART = 'M0,0 L-11,-11 A6.5,6.5 0 0 1 0,-20 A6.5,6.5 0 0 1 11,-11 Z'  # point at the origin
MOTIFS = {
    'snowflake': (
        '<g stroke="#fff" stroke-width="2.6" stroke-linecap="round" fill="none">'
        + ''.join(f'<g transform="rotate({a})"><path d="M0,0 V-20 M0,-12 l-5,-5 M0,-12 l5,-5"/></g>'
                  for a in range(0, 360, 60))
        + '</g>'),
    'star': f'<polygon points="{star_points(13, 5.5)}" fill="#fff"/>',
    'sparkle': '<path d="M0,-15 Q1.8,-1.8 15,0 Q1.8,1.8 0,15 Q-1.8,1.8 -15,0 Q-1.8,-1.8 0,-15 Z" fill="#fff"/>',
    'heart': f'<path d="{HEART}" transform="translate(0,10)" fill="#fff"/>',
    'shamrock': (
        '<g fill="#fff">'
        + ''.join(f'<path d="{HEART}" transform="rotate({a})"/>' for a in (0, 120, 240))
        + '</g><path d="M0,0 q4,14 11,22" stroke="#fff" stroke-width="3" fill="none" stroke-linecap="round"/>'),
    'leaf': ('<path d="M0,-20 C13,-10 13,9 0,20 C-13,9 -13,-10 0,-20 Z" fill="#fff"/>'
             '<path d="M0,-16 V24" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>'),
    'blossom': (
        '<g fill="#fff">'
        + ''.join(f'<ellipse cx="0" cy="-9" rx="6" ry="9" transform="rotate({a})"/>' for a in range(0, 360, 72))
        + '</g>'),
    'egg': '<ellipse cx="0" cy="0" rx="11" ry="15" fill="#fff"/>',
    'dot': '<circle cx="0" cy="0" r="5" fill="#fff"/>',
    'confetti': '<rect x="-3" y="-9" width="6" height="18" rx="2" fill="#fff"/>',
    'bat': ('<path d="M0,-2 C-3,-8 -9,-9 -13,-4 C-17,-9 -24,-8 -27,-1 C-22,-3 -18,-1 -16,4 C-12,0 -6,1 0,6 '
            'C6,1 12,0 16,4 C18,-1 22,-3 27,-1 C24,-8 17,-9 13,-4 C9,-9 3,-8 0,-2 Z" fill="#fff"/>'),
}

# Where motifs sit inside one pattern tile: (motif slot, x, y, scale, rotation)
LAYOUT = [(0, 60, 70, 1.6, 15), (1, 210, 130, 1.0, -20), (0, 140, 250, 1.2, 40), (1, 280, 290, 0.8, 10),
          (0, 330, 40, 0.9, -35)]
TILE = 360


def motif_pattern(motifs, opacity):
    uses = []
    for slot, x, y, scale, rot in LAYOUT:
        name = motifs[slot % len(motifs)]
        uses.append(f'<g transform="translate({x},{y}) rotate({rot}) scale({scale})">{MOTIFS[name]}</g>')
    return (f'<pattern id="m" width="{TILE}" height="{TILE}" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(-8)"><g opacity="{opacity}">{"".join(uses)}</g></pattern>')


def linear(stops):
    s = ''.join(f'<stop offset="{i / (len(stops) - 1):.2f}" stop-color="{c}"/>' for i, c in enumerate(stops))
    return f'<linearGradient id="g" x1="0" y1="0" x2="0.35" y2="1">{s}</linearGradient>'


def themed(stops, motifs, opacity=0.08, extra=''):
    """Gradient plus a faint repeating motif."""
    return (f'<defs>{linear(stops)}{motif_pattern(motifs, opacity)}</defs>'
            f'<rect width="1080" height="1920" fill="url(#g)"/>{extra}'
            f'<rect width="1080" height="1920" fill="url(#m)"/>')


def wash(base, blobs):
    """Abstract: soft overlapping color glows on a dark base, no motifs."""
    defs, circles = [], []
    for i, (color, cx, cy, r) in enumerate(blobs):
        defs.append(f'<radialGradient id="b{i}"><stop offset="0" stop-color="{color}" stop-opacity="0.85"/>'
                    f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')
        circles.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#b{i})"/>')
    return f'<defs>{"".join(defs)}</defs><rect width="1080" height="1920" fill="{base}"/>{"".join(circles)}'


MOON = ('<defs><mask id="crescent"><rect width="1080" height="1920" fill="#fff"/>'
        '<circle cx="880" cy="250" r="120" fill="#000"/></mask></defs>'
        '<circle cx="820" cy="290" r="130" fill="#fff" opacity="0.13" mask="url(#crescent)"/>')
SUN_GLOW = ('<defs><radialGradient id="sun"><stop offset="0" stop-color="#fde68a" stop-opacity="0.45"/>'
            '<stop offset="1" stop-color="#fde68a" stop-opacity="0"/></radialGradient></defs>'
            '<circle cx="860" cy="260" r="520" fill="url(#sun)"/>')

BACKGROUNDS = {
    # Seasonal
    'winter': themed(['#16304f', '#24507a', '#3a6f9a'], ['snowflake', 'dot']),
    'spring': themed(['#2c5f52', '#4a7a5e', '#7a5a86'], ['blossom', 'dot']),
    'summer': themed(['#0b5d73', '#0e7490', '#b45309'], ['sparkle', 'dot'], 0.06, SUN_GLOW),
    'autumn': themed(['#5a1a0c', '#9a3412', '#a16207'], ['leaf', 'dot']),
    # Holidays
    'new-year': themed(['#0f0c29', '#302b63', '#24243e'], ['sparkle', 'confetti'], 0.11),
    'valentines': themed(['#4c0519', '#831843', '#be185d'], ['heart', 'dot']),
    'st-patricks': themed(['#0b3b21', '#14532d', '#1f7a43'], ['shamrock', 'dot']),
    'easter': themed(['#3b3470', '#5b4b8a', '#2f6f7a'], ['egg', 'blossom']),
    'fourth-of-july': themed(['#0b1a4a', '#1e3a8a', '#7f1d1d'], ['star', 'dot'], 0.1),
    'halloween': themed(['#12061f', '#3b1466', '#7c2d12'], ['bat', 'star'], 0.09, MOON),
    'thanksgiving': themed(['#3b1d0b', '#7c3a12', '#a16207'], ['leaf', 'leaf'], 0.08),
    'christmas': themed(['#062a1c', '#0f4a32', '#6b1020'], ['snowflake', 'star'], 0.09),
    # Abstract
    'aurora': wash('#071a24', [('#14b8a6', 200, 300, 700), ('#22c55e', 900, 900, 650), ('#7c3aed', 300, 1600, 750)]),
    'dusk': wash('#1e1b4b', [('#db2777', 900, 300, 700), ('#f97316', 150, 1100, 650), ('#6d28d9', 800, 1700, 700)]),
    'lagoon': wash('#042f2e', [('#0891b2', 150, 400, 750), ('#0d9488', 950, 1100, 650), ('#1d4ed8', 300, 1800, 700)]),
    'ember': wash('#1c0a00', [('#b91c1c', 850, 350, 700), ('#ea580c', 200, 1200, 600), ('#78350f', 900, 1800, 650)]),
    'nebula': wash('#0b0420', [('#9333ea', 250, 450, 700), ('#2563eb', 950, 1000, 650), ('#db2777', 350, 1750, 600)]),
    'mist': wash('#1f2937', [('#475569', 200, 300, 750), ('#64748b', 950, 1100, 700), ('#334155', 300, 1800, 750)]),
    'sage': wash('#14241b', [('#4d7c5f', 200, 400, 750), ('#8a9a5b', 950, 1200, 650), ('#2f4f4f', 300, 1800, 700)]),
    'plum': wash('#22091f', [('#7e22ce', 850, 350, 700), ('#be185d', 200, 1150, 650), ('#4c0519', 900, 1800, 700)]),
}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, body in BACKGROUNDS.items():
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 1920" '
               f'preserveAspectRatio="xMidYMid slice">{body}</svg>\n')
        with open(os.path.join(OUT_DIR, f'{name}.svg'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(svg)
    print(f'wrote {len(BACKGROUNDS)} backgrounds to {OUT_DIR}')


if __name__ == '__main__':
    main()
