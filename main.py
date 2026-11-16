#!/usr/bin/env python3
"""The Village That Sailed the Sky — make.fun ai-excited-01 entry.

Pure Python standard library. No network, no randomness, no clock.
Draws a layered illustrated poster (1024x1024 PNG) and writes it to
/output/entry.png (or $OUTPUT_PATH when set, for local verification).
Deterministic: two runs produce byte-identical output.

SPDX-License-Identifier: MIT
"""

import math
import os
import struct
import zlib

W, H = 1024, 1024

# ---------------------------------------------------------------- buffer
rows = [bytearray(W * 3) for _ in range(H)]


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def blend(dst, src, alpha):
    return (int(dst[0] + (src[0] - dst[0]) * alpha),
            int(dst[1] + (src[1] - dst[1]) * alpha),
            int(dst[2] + (src[2] - dst[2]) * alpha))


def row_fill(y, x0, x1, color):
    """Fill span [x0, x1) on row y with a solid color (fast)."""
    if y < 0 or y >= H:
        return
    x0 = max(0, int(x0))
    x1 = min(W, int(x1))
    if x1 <= x0:
        return
    rows[y][x0 * 3:x1 * 3] = bytes(color) * (x1 - x0)


def span_blend(y, x0, x1, color, alpha):
    """Alpha-blend a span over what is already on row y."""
    if y < 0 or y >= H or alpha <= 0.0:
        return
    if alpha >= 1.0:
        row_fill(y, x0, x1, color)
        return
    x0 = max(0, int(x0))
    x1 = min(W, int(x1))
    if x1 <= x0:
        return
    row = rows[y]
    cr, cg, cb = color
    a = alpha
    for x in range(x0, x1):
        i = x * 3
        row[i] = int(row[i] + (cr - row[i]) * a)
        row[i + 1] = int(row[i + 1] + (cg - row[i + 1]) * a)
        row[i + 2] = int(row[i + 2] + (cb - row[i + 2]) * a)


def set_px(x, y, color):
    if 0 <= x < W and 0 <= y < H:
        rows[y][x * 3:x * 3 + 3] = bytes(color)


def line(x0, y0, x1, y1, color):
    """Bresenham line, 1px."""
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        set_px(x0, y0, color)
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def poly_fill(points, color):
    """Scanline fill of a polygon given as [(x, y), ...]."""
    ys = [p[1] for p in points]
    y0 = max(0, min(ys))
    y1 = min(H - 1, max(ys))
    n = len(points)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            x1, yy1 = points[i]
            x2, yy2 = points[(i + 1) % n]
            if yy1 == yy2:
                continue
            if min(yy1, yy2) <= y < max(yy1, yy2):
                t = (y - yy1) / (yy2 - yy1)
                xs.append(x1 + t * (x2 - x1))
        if len(xs) >= 2:
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                row_fill(y, xs[k], xs[k + 1], color)


def poly_fill_alpha(points, color, alpha):
    """Scanline fill of a polygon with a uniform alpha blend."""
    ys = [p[1] for p in points]
    y0 = max(0, min(ys))
    y1 = min(H - 1, max(ys))
    n = len(points)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            x1, yy1 = points[i]
            x2, yy2 = points[(i + 1) % n]
            if yy1 == yy2:
                continue
            if min(yy1, yy2) <= y < max(yy1, yy2):
                t = (y - yy1) / (yy2 - yy1)
                xs.append(x1 + t * (x2 - x1))
        if len(xs) >= 2:
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                span_blend(y, xs[k], xs[k + 1], color, alpha)


def disc(cx, cy, r, color):
    for y in range(max(0, cy - r), min(H, cy + r + 1)):
        dy = y - cy
        w = int(math.sqrt(max(0, r * r - dy * dy)))
        row_fill(y, cx - w, cx + w, color)


def ellipse(cx, cy, rx, ry, color):
    for y in range(max(0, cy - ry), min(H, cy + ry + 1)):
        t = (y - cy) / ry
        w = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
        row_fill(y, cx - w, cx + w, color)


def ellipse_vgrad(cx, cy, rx, ry, top, bottom):
    """Ellipse filled with a vertical gradient (top color -> bottom)."""
    for y in range(max(0, cy - ry), min(H, cy + ry + 1)):
        t = (y - cy) / ry
        w = int(rx * math.sqrt(max(0.0, 1.0 - t * t)))
        row_fill(y, cx - w, cx + w, lerp(top, bottom, clamp(t * 0.5 + 0.5, 0.0, 1.0)))


# ---------------------------------------------------------------- font
# 5x7 bitmap font, rows of 5 bits ('1' = ink). Space + A-Z + . ! ' - ,
FONT = {
    ' ': ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    'A': ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    'B': ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    'C': ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    'D': ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    'E': ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    'F': ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    'G': ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    'H': ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    'I': ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    'J': ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    'K': ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    'L': ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    'M': ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    'N': ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    'O': ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    'P': ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    'Q': ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    'R': ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    'S': ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    'T': ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    'U': ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    'V': ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    'W': ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    'X': ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    'Y': ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    'Z': ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    '.': ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    '!': ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"],
    '-': ["00000", "00000", "00000", "01110", "00000", "00000", "00000"],
    ',': ["00000", "00000", "00000", "00000", "01100", "00100", "01000"],
}


def draw_text(text, x, y, scale, color, outline=None):
    """Draw text with a 5x7 font scaled by `scale`. (x, y) = top-left."""
    def blit(ox, oy, col):
        for ci, ch in enumerate(text):
            glyph = FONT.get(ch, FONT[' '])
            gx = ox + ci * 6 * scale
            for r in range(7):
                bits = glyph[r]
                for c in range(5):
                    if bits[c] == '1':
                        for dy in range(scale):
                            row_fill(oy + r * scale + dy,
                                     gx + c * scale, gx + (c + 1) * scale, col)
    if outline is not None:
        d = max(2, scale // 2)
        blit(x - d, y, outline)
        blit(x + d, y, outline)
        blit(x, y - d, outline)
        blit(x, y + d, outline)
    blit(x, y, color)


def text_width(text, scale):
    return len(text) * 6 * scale - scale


# ------------------------------------------------- deterministic helper
def lcg(seed):
    """Tiny deterministic pseudo-random generator (fixed seed)."""
    state = seed & 0xFFFFFFFF

    def nxt():
        nonlocal state
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF
    return nxt


# ---------------------------------------------------------------- scene
def draw_sky():
    stops = [(0, (18, 26, 54)), (260, (66, 52, 104)), (470, (168, 82, 104)),
             (580, (224, 122, 88)), (640, (247, 178, 103))]
    for y in range(0, 640):
        for i in range(len(stops) - 1):
            y0, c0 = stops[i]
            y1, c1 = stops[i + 1]
            if y0 <= y <= y1:
                t = (y - y0) / max(1, y1 - y0)
                row_fill(y, 0, W, lerp(c0, c1, t))
                break
        else:
            row_fill(y, 0, W, stops[-1][1])
    # cloud-sea base below the horizon
    for y in range(640, H):
        t = (y - 640) / (H - 640)
        row_fill(y, 0, W, lerp((247, 178, 103), (104, 72, 112), t))


def draw_sun_and_rays():
    sx, sy = 700, 272
    # light rays: translucent gold wedges fanning from the sun
    for ang, length, half in ((-38, 430, 26), (-18, 470, 20), (2, 420, 24),
                              (22, 380, 18), (42, 330, 22), (-58, 360, 18)):
        a = math.radians(ang)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy, dx
        tipx = int(sx + dx * length)
        tipy = int(sy + dy * length)
        poly_fill_alpha([(sx, sy),
                         (int(sx + px * half), int(sy + py * half)),
                         (tipx, tipy),
                         (int(sx - px * half), int(sy - py * half))],
                        (255, 205, 130), 0.13)
    # halo rings, faintest first (many gentle steps = smooth glow)
    for r, alpha in ((220, 0.05), (195, 0.07), (170, 0.10), (148, 0.13),
                     (128, 0.17), (110, 0.22), (95, 0.30)):
        for y in range(max(0, sy - r), min(H, sy + r + 1)):
            dy = y - sy
            w = int(math.sqrt(max(0, r * r - dy * dy)))
            sky = tuple(rows[y][0:3])
            span_blend(y, sx - w, sx + w, blend(sky, (255, 200, 120), alpha), 1.0)
    # sun disc with a hot core
    disc(sx, sy, 86, (255, 214, 138))
    disc(sx, sy, 62, (255, 232, 168))
    disc(sx, sy, 40, (255, 244, 205))


def cloud_puff(cx, cy, rx, ry, lit, mid, shade):
    """One billowing cloud: gradient body + bright cap."""
    ellipse_vgrad(cx, cy, rx, ry, mid, shade)
    ellipse_vgrad(cx, cy - int(ry * 0.38), int(rx * 0.72), int(ry * 0.55), lit, mid)


def draw_cloud_sea():
    rnd = lcg(20261116)
    # far row: small, warm-lit
    for i in range(9):
        cx = 60 + i * 112 + int(rnd() * 40)
        cloud_puff(cx, 668 + int(rnd() * 26), 62 + int(rnd() * 30), 20 + int(rnd() * 10),
                   (255, 216, 160), (238, 168, 122), (168, 118, 148))
    # middle row: larger
    for i in range(8):
        cx = 30 + i * 130 + int(rnd() * 50)
        cloud_puff(cx, 762 + int(rnd() * 34), 84 + int(rnd() * 40), 30 + int(rnd() * 14),
                   (255, 222, 172), (236, 164, 118), (148, 100, 138))
    # front row: biggest, cool shadows at the bottom
    for i in range(7):
        cx = 10 + i * 155 + int(rnd() * 60)
        cloud_puff(cx, 884 + int(rnd() * 40), 118 + int(rnd() * 55), 44 + int(rnd() * 18),
                   (255, 228, 184), (232, 158, 116), (122, 82, 124))
    # a few extra puffs to fill gaps low down
    for i in range(6):
        cx = 80 + i * 165 + int(rnd() * 50)
        cloud_puff(cx, 972 + int(rnd() * 26), 96 + int(rnd() * 40), 34 + int(rnd() * 12),
                   (250, 214, 170), (224, 152, 116), (108, 74, 116))


def draw_island():
    # rocky floating island: plateau top, tapering to a point below
    pts = [(168, 468), (566, 468), (520, 540), (452, 632), (372, 730),
           (316, 640), (238, 552), (182, 500)]
    # vertical rock gradient, row by row
    ys = [p[1] for p in pts]
    y0, y1 = min(ys), max(ys)
    n = len(pts)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            x1, yy1 = pts[i]
            x2, yy2 = pts[(i + 1) % n]
            if yy1 == yy2:
                continue
            if min(yy1, yy2) <= y < max(yy1, yy2):
                xs.append(x1 + (y - yy1) / (yy2 - yy1) * (x2 - x1))
        if len(xs) >= 2:
            xs.sort()
            col = lerp((122, 74, 56), (36, 21, 34), (y - y0) / max(1, y1 - y0))
            for k in range(0, len(xs) - 1, 2):
                row_fill(y, xs[k], xs[k + 1], col)
    # sunlit rim along the plateau edge
    line(168, 468, 566, 468, (232, 160, 98))
    line(566, 468, 520, 540, (214, 140, 88))
    # strata lines on the rock face
    line(210, 540, 500, 540, (58, 36, 46))
    line(250, 600, 452, 600, (52, 32, 42))
    line(300, 656, 420, 656, (46, 28, 38))
    # hanging rock spikes under the island
    poly_fill([(300, 640), (318, 640), (309, 690)], (52, 32, 42))
    poly_fill([(400, 668), (416, 668), (408, 712)], (46, 28, 38))


def house(x, y, w, h, roof_h, lit):
    """A small house: dark body, terracotta roof, glowing windows."""
    body = (58, 36, 48)
    poly_fill([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], body)
    poly_fill([(x - 4, y), (x + w // 2, y - roof_h), (x + w + 4, y)], (198, 90, 58))
    poly_fill([(x + w // 2, y - roof_h), (x + w + 4, y), (x + w - 2, y)],
              (232, 138, 84))
    # glowing windows
    for wx in (x + 6, x + w - 14):
        for wy in (y + 8, y + h - 14):
            row_fill(wy, wx, wx + 8, (255, 217, 122))
            row_fill(wy + 1, wx, wx + 8, (255, 217, 122))
            row_fill(wy + 2, wx, wx + 8, (255, 217, 122))
            row_fill(wy + 3, wx, wx + 8, (255, 217, 122))
            row_fill(wy + 4, wx, wx + 8, (255, 217, 122))


def draw_village():
    # warm glow wash over the plateau so windows feel lit
    for y in range(420, 470):
        span_blend(y, 190, 550, (255, 190, 110), 0.10)
    house(196, 428, 52, 42, 22, False)
    house(256, 436, 44, 34, 18, False)
    house(308, 424, 58, 46, 24, True)
    house(374, 434, 46, 36, 18, False)
    house(428, 428, 54, 42, 22, False)
    house(490, 438, 44, 32, 16, False)
    # tower with a pointed roof and a small flag
    poly_fill([(516, 470), (516, 392), (540, 392), (540, 470)], (48, 30, 42))
    poly_fill([(512, 392), (528, 356), (544, 392)], (198, 90, 58))
    line(528, 356, 528, 336, (28, 18, 26))
    poly_fill([(528, 336), (548, 342), (528, 348)], (226, 72, 60))
    row_fill(410, 520, 536, (255, 217, 122))
    row_fill(411, 520, 536, (255, 217, 122))
    row_fill(412, 520, 536, (255, 217, 122))
    # trees: dark crowns with a warm sunlit rim on the sunrise side
    for tx, ty, r in ((180, 452, 15), (466, 452, 13), (556, 456, 14)):
        disc(tx, ty, r, (30, 56, 40))
        disc(tx + 4, ty - 3, r - 5, (58, 96, 58))
        disc(tx + 6, ty - 4, 3, (232, 170, 96))


def draw_waterfall():
    # pours from the island's left underside into the cloud mist
    for y in range(505, 845):
        wob = int(6 * math.sin(y * 0.045))
        wob2 = int(5 * math.sin(y * 0.03 + 2.0))
        x0 = 252 + wob
        x1 = 294 + wob2
        row_fill(y, x0, x1, (207, 230, 245))
        # bright core streaks
        for k, off in enumerate((6, 18, 30)):
            sx = x0 + off + int(3 * math.sin(y * 0.06 + k * 1.7))
            row_fill(y, sx, sx + 3, (242, 251, 255))
    # mist where it meets the clouds
    cloud_puff(272, 848, 52, 20, (244, 248, 255), (214, 228, 240), (168, 178, 200))
    cloud_puff(292, 862, 40, 16, (244, 248, 255), (214, 228, 240), (168, 178, 200))


def sail(tl, tr, bl, br, lit, shade):
    """A billowing sail: curved leech edges, lit face, shaded right strip."""
    # midpoints of the side edges, pushed outward for the billow curve
    ml = ((tl[0] + bl[0]) // 2 - 14, (tl[1] + bl[1]) // 2)
    mr = ((tr[0] + br[0]) // 2 + 14, (tr[1] + br[1]) // 2)
    poly_fill([tl, ml, bl, br, mr, tr], lit)
    # narrow shaded strip along the right third for volume
    strip = [tr, mr, br,
             (br[0] - (br[0] - bl[0]) // 3, br[1]),
             (tr[0] - (tr[0] - tl[0]) // 3, tr[1])]
    poly_fill_alpha(strip, shade, 0.35)
    # foot seam
    line(bl[0], bl[1], br[0], br[1], (214, 160, 110))


def draw_big_ship():
    hull = (36, 26, 38)
    # soft shadow in the clouds beneath the hull
    for y in range(878, 906):
        t = (y - 878) / 28
        w = int(210 * math.sqrt(max(0.0, 1.0 - t * t)))
        span_blend(y, 690 - w, 690 + w, (74, 51, 80), 0.30)
    # hull: deck line, bow right, keel below
    poly_fill([(500, 786), (872, 786), (892, 762), (872, 786),
               (860, 812), (812, 852), (700, 880), (606, 858),
               (528, 822), (500, 786)], hull)
    # warm rim light along the deck edge
    line(500, 786, 872, 786, (232, 160, 96))
    # bowsprit
    line(872, 780, 916, 758, (28, 18, 26))
    line(872, 784, 916, 762, (28, 18, 26))
    # masts
    for mx, top in ((600, 606), (690, 542), (782, 622)):
        row_fill(top, mx - 3, mx + 3, (28, 18, 26))
        for y in range(top, 790):
            row_fill(y, mx - 2, mx + 2, (28, 18, 26))
    # sails: one tall wind-filled sail per mast, lit by the sunrise
    sail((566, 626), (632, 626), (560, 724), (640, 724), (250, 224, 182), (232, 178, 118))
    sail((660, 580), (720, 580), (648, 714), (732, 714), (255, 233, 196), (242, 192, 132))
    sail((748, 644), (810, 644), (744, 728), (816, 728), (250, 224, 182), (232, 178, 118))
    # small top sail on the main mast, separated from the main sail
    sail((674, 548), (706, 548), (672, 568), (708, 568), (255, 240, 212), (240, 196, 138))
    # pennant on the main mast
    poly_fill([(690, 542), (724, 550), (690, 558)], (226, 72, 60))
    # rigging
    line(690, 546, 892, 766, (28, 18, 26))
    line(690, 546, 500, 786, (28, 18, 26))
    line(600, 610, 690, 546, (28, 18, 26))
    line(782, 626, 690, 546, (28, 18, 26))
    line(600, 610, 560, 726, (28, 18, 26))
    line(782, 626, 818, 730, (28, 18, 26))
    # cabin windows glowing on the hull
    for wx in (560, 600, 640, 740, 780):
        row_fill(806, wx, wx + 10, (255, 217, 122))
        row_fill(807, wx, wx + 10, (255, 217, 122))
        row_fill(808, wx, wx + 10, (255, 217, 122))
    # cloud puffs breaking around the hull base
    cloud_puff(540, 868, 46, 16, (255, 228, 184), (232, 158, 116), (122, 82, 124))
    cloud_puff(860, 872, 52, 18, (255, 228, 184), (232, 158, 116), (122, 82, 124))


def draw_small_ship():
    # distant ship for scale, a dark silhouette on the cloud sea
    poly_fill([(128, 806), (216, 806), (206, 826), (148, 826)], (52, 38, 52))
    for mx, top in ((152, 758), (176, 742)):
        for y in range(top, 808):
            row_fill(y, mx - 1, mx + 1, (52, 38, 52))
    poly_fill([(140, 760), (164, 760), (160, 800), (144, 800)], (216, 200, 172))
    poly_fill([(166, 746), (186, 746), (182, 798), (170, 798)], (226, 210, 180))
    line(176, 744, 216, 806, (52, 38, 52))


def draw_birds():
    dark = (28, 20, 32)
    for cx, cy, s in ((250, 200, 9), (304, 178, 7), (420, 148, 8), (520, 218, 7),
                      (826, 176, 8), (884, 228, 7), (148, 300, 8), (452, 96, 6)):
        line(cx - s, cy - s // 2, cx, cy, dark)
        line(cx, cy, cx + s, cy - s // 2, dark)
        line(cx - s, cy - s // 2 + 1, cx, cy + 1, dark)
        line(cx, cy + 1, cx + s, cy - s // 2 + 1, dark)


def draw_caption():
    # dark band so the caption reads over the bright clouds
    for y in range(905, H):
        span_blend(y, 0, W, (20, 16, 42), 0.48)
    cream = (255, 243, 214)
    outline = (26, 20, 48)
    line1 = "THE VILLAGE THAT SAILED THE SKY"
    line2 = "IT NEVER CAME DOWN."
    scale = 5
    x1 = (W - text_width(line1, scale)) // 2
    x2 = (W - text_width(line2, scale)) // 2
    draw_text(line1, x1, 918, scale, cream, outline)
    draw_text(line2, x2, 962, scale, cream, outline)
    # thin gold rules above and below the caption
    line(312, 908, 712, 908, (232, 180, 110))
    line(392, 1006, 632, 1006, (232, 180, 110))


# ---------------------------------------------------------------- PNG
def chunk(typ, data):
    out = struct.pack(">I", len(data)) + typ + data
    out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return out


def write_png(path, width, height, rows):
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw += row
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def main():
    out = os.environ.get("OUTPUT_PATH", "/output/entry.png")
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    draw_sky()
    draw_sun_and_rays()
    draw_cloud_sea()
    draw_island()
    draw_village()
    draw_waterfall()
    draw_small_ship()
    draw_big_ship()
    draw_birds()
    draw_caption()
    write_png(out, W, H, rows)


if __name__ == "__main__":
    main()
