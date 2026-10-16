"""Outline every stroke in an SVG into filled shapes (like Illustrator's Outline Stroke)."""
"""Usage: pip install shapely svgelements && python3 tools/outline_strokes.py source/healthcare_illustration_stroked.svg healthcare_illustration.svg"""
import sys, math, re
import xml.etree.ElementTree as ET
from svgelements import Path, Close, Move, Line
from shapely.geometry import LineString, LinearRing, Polygon, MultiPolygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
SHAPES = {'rect', 'circle', 'ellipse', 'line', 'path'}
STROKE_ATTRS = ['stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit']

def f(e, k, d=0.0): return float(e.get(k, d))

def sample_arc(cx, cy, rx, ry, a0, a1, n):
    return [(cx + rx * math.cos(a0 + (a1 - a0) * i / n), cy + ry * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]

def subpaths(e):
    """Return list of (points, closed) in the element's local coordinates."""
    tag = e.tag.split('}')[1]
    if tag == 'circle':
        r = f(e, 'r'); return [(sample_arc(f(e, 'cx'), f(e, 'cy'), r, r, 0, 2 * math.pi, 128)[:-1], True)]
    if tag == 'ellipse':
        return [(sample_arc(f(e, 'cx'), f(e, 'cy'), f(e, 'rx'), f(e, 'ry'), 0, 2 * math.pi, 160)[:-1], True)]
    if tag == 'line':
        return [([(f(e, 'x1'), f(e, 'y1')), (f(e, 'x2'), f(e, 'y2'))], False)]
    if tag == 'rect':
        x, y, w, h = f(e, 'x'), f(e, 'y'), f(e, 'width'), f(e, 'height')
        r = min(float(e.get('rx', e.get('ry', 0))), w / 2, h / 2)
        if r <= 0: return [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
        pts = []
        for cx, cy, a in [(x + w - r, y + r, -math.pi / 2), (x + w - r, y + h - r, 0), (x + r, y + h - r, math.pi / 2), (x + r, y + r, math.pi)]:
            pts += sample_arc(cx, cy, r, r, a, a + math.pi / 2, 24)
        return [(pts, True)]
    out = []
    for sp in Path(e.get('d')).as_subpaths():
        pts, closed = [], False
        for seg in sp:
            if isinstance(seg, Move): pts.append((seg.end.x, seg.end.y)); continue
            if isinstance(seg, Close): closed = True; continue
            if isinstance(seg, Line): pts.append((seg.end.x, seg.end.y)); continue
            n = max(8, int(seg.length() / 1.5))
            pts += [(p.x, p.y) for p in (seg.point(i / n) for i in range(1, n + 1))]
        out.append((pts, closed))
    return out

def stroke_geom(e, inherited):
    a = lambda k, d: e.get(k, inherited.get(k, d))
    w = float(a('stroke-width', 1))
    cap = {'round': 'round', 'square': 'square'}.get(a('stroke-linecap', 'butt'), 'flat')
    join = {'round': 'round', 'bevel': 'bevel'}.get(a('stroke-linejoin', 'miter'), 'mitre')
    geoms = []
    for pts, closed in subpaths(e):
        if closed and len(pts) >= 3:
            g = LinearRing(pts)
        else:
            g = LineString(pts)
        geoms.append(g.buffer(w / 2, quad_segs=16, cap_style=cap, join_style=join, mitre_limit=float(a('stroke-miterlimit', 4))))
    return unary_union(geoms)

def fmt(v): s = f'{v:.2f}'.rstrip('0').rstrip('.'); return '0' if s == '-0' else s

def ring_d(coords):
    c = list(coords)[:-1]
    return 'M' + ' L'.join(f'{fmt(x)} {fmt(y)}' for x, y in c) + ' Z'

def geom_d(g):
    polys = [g] if isinstance(g, Polygon) else list(g.geoms)
    parts = []
    for p in polys:
        p = orient(p.simplify(0.04), 1.0)
        parts.append(ring_d(p.exterior.coords))
        parts += [ring_d(i.coords) for i in p.interiors]
    return ' '.join(parts)

def process(parent, inherited):
    children = list(parent)
    for child in children:
        tag = child.tag.split('}')[1]
        if tag == 'g':
            inh = dict(inherited); inh.update({k: v for k, v in child.attrib.items() if k in STROKE_ATTRS})
            for k in STROKE_ATTRS: child.attrib.pop(k, None)
            process(child, inh); continue
        if tag not in SHAPES: continue
        stroke = child.get('stroke', inherited.get('stroke'))
        if not stroke or stroke == 'none': continue
        outline = ET.Element(f'{{{NS}}}path', {'d': geom_d(stroke_geom(child, inherited)), 'fill': stroke})
        if child.get('stroke-opacity'): outline.set('fill-opacity', child.get('stroke-opacity'))
        idx = list(parent).index(child)
        if child.get('fill', 'black') == 'none' or tag == 'line':
            parent.remove(child); parent.insert(idx, outline)
        else:
            for k in STROKE_ATTRS + ['stroke-opacity']: child.attrib.pop(k, None)
            parent.insert(idx + 1, outline)

src, dst = sys.argv[1:3]
tree = ET.parse(src)
process(tree.getroot(), {})
ET.indent(tree, '  ')
tree.write(dst, encoding='UTF-8', xml_declaration=True)
