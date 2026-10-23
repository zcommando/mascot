"""Build the Mascot logo as two SVG paths: a red silhouette (outline + extrusion)
and the cream letters on top.

    make-logo.py Damion-Regular.ttf logo.svg                      # wordmark for index.html
    make-logo.py Damion-Regular.ttf favicon.svg --text M --square \\
        --red '#F9033D' --cream '#FEFBF6'                           # icon
"""
import argparse
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.pens.transformPen import TransformPen
from shapely.geometry import Polygon, LinearRing
from shapely.ops import unary_union
from shapely import affinity

args = argparse.ArgumentParser()
args.add_argument("font")
args.add_argument("out")
args.add_argument("--text", default="Mascot")
args.add_argument("--square", action="store_true", help="pad the viewBox to a square")
args.add_argument("--bg", help="fill the viewBox with this color (for opaque icons)")
args.add_argument("--red", default="var(--red)")
args.add_argument("--cream", default="var(--cream)")
args = args.parse_args()
FONT, OUT, TEXT = args.font, args.out, args.text
EM = 1000.0                 # output units per em
CLOSE = 0.012 * EM          # morphological closing radius (fills the s notch)
OUTLINE = 0.0175 * EM       # visible outline width (outer half of the old 0.035em stroke)
EXTRUDE = (0.1575 * EM, 0.126 * EM)   # down-right, same as the 63-step CSS version
CURVE_STEPS = 24


class FlattenPen(BasePen):
    """Collect contours as lists of points, flattening curves."""
    def __init__(self, glyphset):
        super().__init__(glyphset)
        self.contours, self.cur = [], []
    def _moveTo(self, p):
        self.cur = [p]
    def _lineTo(self, p):
        self.cur.append(p)
    def _curveToOne(self, p1, p2, p3):
        p0 = self.cur[-1]
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS; u = 1 - t
            self.cur.append((u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0],
                             u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]))
    def _qCurveToOne(self, p1, p2):
        p0 = self.cur[-1]
        for i in range(1, CURVE_STEPS + 1):
            t = i / CURVE_STEPS; u = 1 - t
            self.cur.append((u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0],
                             u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1]))
    def _closePath(self):
        if len(self.cur) >= 3:
            self.contours.append(self.cur)
        self.cur = []
    _endPath = _closePath


font = TTFont(FONT)
upem = font["head"].unitsPerEm
scale = EM / upem
glyphset = font.getGlyphSet()
order = font.getGlyphOrder()

blob = hb.Blob.from_file_path(FONT)
hbfont = hb.Font(hb.Face(blob))
buf = hb.Buffer(); buf.add_str(TEXT); buf.guess_segment_properties()
hb.shape(hbfont, buf, {"kern": True, "liga": True, "calt": True})

glyph_shapes = []
x = y = 0
for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
    pen = FlattenPen(glyphset)
    tx = (x + pos.x_offset) * scale
    ty = (y + pos.y_offset) * scale
    glyphset[order[info.codepoint]].draw(TransformPen(pen, (scale, 0, 0, scale, tx, ty)))
    # TrueType: outer contours run clockwise, counters counter-clockwise (y up)
    outers, holes = [], []
    for c in pen.contours:
        ring = LinearRing(c)
        poly = Polygon(c).buffer(0)
        (holes if ring.is_ccw else outers).append(poly)
    shape = unary_union(outers)
    if holes:
        shape = shape.difference(unary_union(holes))
    glyph_shapes.append(shape)
    x += pos.x_advance; y += pos.y_advance

letters = unary_union(glyph_shapes)
closed = letters.buffer(CLOSE, join_style="round", quad_segs=16).buffer(-CLOSE, join_style="round", quad_segs=16)
outlined = closed.buffer(OUTLINE, join_style="round", quad_segs=16)

# exact sweep of the outlined shape along the extrusion vector (y is up here, so dy < 0)
dx, dy = EXTRUDE[0], -EXTRUDE[1]
pieces = [outlined, affinity.translate(outlined, dx, dy)]
geoms = getattr(outlined, "geoms", [outlined])
for g in geoms:
    for ring in [g.exterior, *g.interiors]:
        pts = list(ring.coords)
        for a, b in zip(pts, pts[1:]):
            quad = Polygon([a, b, (b[0] + dx, b[1] + dy), (a[0] + dx, a[1] + dy)])
            if quad.area > 1e-6:
                pieces.append(quad)
red = unary_union(pieces).simplify(0.4)
cream = letters.simplify(0.4)

minx, miny, maxx, maxy = red.bounds
w, h = maxx - minx, maxy - miny
pad = 0.12 * max(w, h) if args.bg else 0.02 * EM    # breathing room on an opaque tile
vb = (minx - pad, -(maxy + pad), w + 2 * pad, h + 2 * pad)
if args.square:
    side = max(vb[2], vb[3])
    vb = (vb[0] - (side - vb[2]) / 2, vb[1] - (side - vb[3]) / 2, side, side)


def to_d(geom):
    out = []
    for g in getattr(geom, "geoms", [geom]):
        for ring in [g.exterior, *g.interiors]:
            pts = list(ring.coords)[:-1]
            out.append("M" + " ".join(f"{px:.1f} {-py:.1f}" for px, py in pts) + "Z")
    return "".join(out)


bg = (f'<rect x="{vb[0]:.1f}" y="{vb[1]:.1f}" width="{vb[2]:.1f}" height="{vb[3]:.1f}" '
      f'style="fill:{args.bg}"/>') if args.bg else ""
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" '
       f'viewBox="{vb[0]:.1f} {vb[1]:.1f} {vb[2]:.1f} {vb[3]:.1f}" '
       f'role="img" aria-label="{TEXT}">{bg}'
       f'<path style="fill:{args.red}" fill-rule="evenodd" d="{to_d(red)}"/>'
       f'<path style="fill:{args.cream}" fill-rule="evenodd" d="{to_d(cream)}"/>'
       f'</svg>')
open(OUT, "w").write(svg)
print(f"upem={upem} glyphs={len(glyph_shapes)} viewBox_em=({vb[2]/EM:.3f} x {vb[3]/EM:.3f}) bytes={len(svg)}")
