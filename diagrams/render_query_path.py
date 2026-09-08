#!/usr/bin/env python3
"""Render a public, conceptual RAG query path to editable SVG and PNG.

Requires Pillow. Use --font and --bold-font to select installed TrueType fonts.
No network, runtime configuration, knowledge corpus, or credentials are read.
"""
from pathlib import Path
import argparse
import hashlib
import html
import json
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, default=Path('.'))
parser.add_argument('--font', default='Arial.ttf')
parser.add_argument('--bold-font', default='Arial Bold.ttf')
a = parser.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
W, H = 1600, 1480
C = dict(bg='#0b1220', card='#121e31', inset='#101b2c', border='#2b3b53',
         ink='#edf4fc', muted='#b3c2d7', teal='#55ddc0', blue='#80bbff',
         purple='#c1a8ff', amber='#f7c66b')
im = Image.new('RGB', (W, H), C['bg'])
draw = ImageDraw.Draw(im)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       '<title>NX-Shield RAG: from question to a checkable answer</title>',
       '<desc>Conceptual six-stage answer path with connected retrieval detail. Access restrictions apply throughout; graph signals are not proof and automated checks do not guarantee correctness.</desc>',
       f'<rect width="{W}" height="{H}" fill="{C["bg"]}"/>']
text_records = []
fonts = {}

def font(size, bold=False):
    key = (size, bold)
    if key not in fonts:
        fonts[key] = ImageFont.truetype(a.bold_font if bold else a.font, size)
    return fonts[key]

def rect(x, y, w, h, fill, stroke=None, radius=16, width=1):
    draw.rounded_rectangle((x, y, x+w, y+h), radius, fill, outline=stroke, width=width)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{width}"/>')

def text(x, baseline, value, size=23, color=None, bold=False, max_width=None):
    f = font(size, bold)
    box = draw.textbbox((x, baseline), value, font=f, anchor='ls')
    if max_width is not None:
        assert box[2]-x <= max_width, (value, box[2]-x, max_width)
    assert box[0] >= 0 and box[1] >= 0 and box[2] <= W and box[3] <= H, (value, box)
    color = color or C['ink']
    draw.text((x, baseline), value, font=f, fill=color, anchor='ls')
    svg.append(f'<text x="{x}" y="{baseline}" fill="{color}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{700 if bold else 400}">{html.escape(value)}</text>')
    text_records.append(dict(text=value, bounds=list(box)))

def connector(points, color, dashed=False, arrow=True, width=2):
    # Draw consistent orthogonal paths in both outputs.
    for (x1,y1),(x2,y2) in zip(points, points[1:]):
        assert x1==x2 or y1==y2, 'Connectors must be orthogonal'
        if not dashed:
            draw.line((x1,y1,x2,y2), fill=color, width=width)
        else:
            length=abs(x2-x1)+abs(y2-y1)
            for start in range(0,length,13):
                end=min(start+7,length)
                dx=0 if x1==x2 else (1 if x2>x1 else -1)
                dy=0 if y1==y2 else (1 if y2>y1 else -1)
                draw.line((x1+dx*start,y1+dy*start,x1+dx*end,y1+dy*end), fill=color, width=width)
    coords=' '.join(f'{x},{y}' for x,y in points)
    dash=' stroke-dasharray="7 6"' if dashed else ''
    svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}"{dash}/>')
    if arrow:
        (px,py),(x,y)=points[-2:]
        if x==px:
            d=1 if y>py else -1
            tri=[(x,y),(x-5,y-9*d),(x+5,y-9*d)]
        else:
            d=1 if x>px else -1
            tri=[(x,y),(x-9*d,y-5),(x-9*d,y+5)]
        draw.polygon(tri,fill=color)
        svg.append(f'<polygon points="{" ".join(f"{u},{v}" for u,v in tri)}" fill="{color}"/>')

rect(64,32,208,32,'#18332f',radius=16)
text(80,54,'REFERENCE DESIGN',17,C['teal'],True,180)
text(64,116,'NX-Shield RAG',48,bold=True)
text(64,156,'From a question to a checkable answer',29,C['muted'])
rect(64,188,1472,52,'#142033',C['border'],12)
text(86,222,'Across every stage: identity • source permissions • allowed model processing • auditability',23,max_width=1428)
text(64,279,'THE ANSWER PATH',19,C['teal'],True)
text(840,279,'KNOWLEDGE + RETRIEVAL DETAIL',19,C['blue'],True)

stages = [
 ('Understand the question + caller', C['teal'], [
  'Authenticate identity; keep the question in scope.',
  'Preserve exact identifiers and versions.',
  'Unknown identity or denied request → stop.']),
 ('Retrieve evidence and tool results', C['blue'], [
  'Run complementary search methods.',
  'Add graph hints or calculations when useful.',
  'Keep retrieved content inside its permitted scope.']),
 ('Build the evidence ledger', C['purple'], [
  'Attach sources, versions, and calculation inputs.',
  'Record which points are supported or missing.',
  'Similarity and keyword overlap are not proof.']),
 ('Draft an answer from the evidence', C['purple'], [
  'Use selected passages and explicit tool results.',
  'Cite sources and state relevant assumptions.',
  'Do not fill evidence gaps with invented claims.']),
 ('Check the draft against its evidence', C['amber'], [
  'Check support, citations, caveats, and access.',
  'Revise within a fixed budget and recheck.',
  'Unresolved failures must not become normal answers.']),
 ('Deliver an answer—or explain the gap', C['teal'], [
  'Return citations, assumptions, and uncertainty.',
  'Qualify partial answers; withhold failing claims.',
  'Automated checks do not guarantee correctness.'])]
for i,(title,color,lines) in enumerate(stages):
    y=300+i*178
    rect(64,y,710,152,C['card'],C['border'])
    rect(64,y,5,152,color,radius=2)
    rect(86,y+19,34,34,color,radius=17)
    text(96,y+44,str(i+1),23,C['bg'],True,25)
    text(136,y+45,title,28,bold=True,max_width=616)
    for j,line in enumerate(lines):
        text(88,y+78+j*28,line,23,C['muted'],max_width=664)
    if i<5:
        connector([(419,y+152),(419,y+178)],C['teal'])

rect(840,300,696,152,C['card'],C['border'])
text(864,341,'Prepared knowledge collection',28,bold=True,max_width=648)
for j,line in enumerate([
 'Before questions arrive: parse, chunk, and index.',
 'Store source links, versions, and access metadata.',
 'Only ingest material permitted for the intended use.']):
    text(864,378+j*28,line,23,C['muted'],max_width=648)
connector([(1188,452),(1188,478)],C['blue'])

rect(840,478,696,690,'#0e192a',C['blue'],18)
text(864,516,'Inside step 2: retrieval and tools',26,C['blue'],True,max_width=648)
details = [
 ('A  Search with complementary methods',[
  'Meaning-based vectors + keyword search.',
  'Exact lookups protect document identifiers.',
  'LanceDB: permitted passages + source metadata.']),
 ('B  Use helpers only when needed',[
  'Ladybug graph: relationship hints, not proof.',
  'Calculators: repeatable results + assumptions.',
  'Helpers must obey the same access policy.']),
 ('C  Reconcile permissions, then rank',[
  'Resolve conflicting permissions conservatively.',
  'Combine rankings; optionally rerank relevance.',
  'Keep source versions and citations attached.']),
 ('D  Handle gaps with bounded recovery',[
  'Search additional permitted sources only.',
  'Recheck access and ranking for new evidence.',
  'Stop after a fixed budget; expose remaining gaps.'])]
for i,(title,lines) in enumerate(details):
    y=540+i*142
    rect(860,y,656,132,C['card'],C['border'],12)
    text(880,y+32,title,24,C['ink'],True,max_width=616)
    for j,line in enumerate(lines):
        text(880,y+64+j*27,line,22,C['muted'],max_width=616)
    if i<3:
        connector([(1188,y+132),(1188,y+142)],C['blue'],width=1)
text(864,1144,'Return source-linked evidence and explicit gaps.',22,C['blue'],max_width=648)
# Expansion and return links occupy different vertical gutters.
connector([(774,554),(808,554),(808,510),(840,510)],C['blue'],True)
connector([(840,1136),(800,1136),(800,732),(774,732)],C['blue'],True)
# A bounded revision loop returns to drafting, never bypassing verification.
connector([(64,1088),(32,1088),(32,910),(64,910)],C['amber'],True)

rect(840,1190,696,152,C['card'],C['border'])
text(864,1231,'Evaluate before enabling controls',28,bold=True,max_width=648)
for j,line in enumerate([
 'Test claim support, relevance, and denied access.',
 'Measure latency, failures, and fallback behavior.',
 'Use staged rollout and a tested rollback.']):
    text(864,1268+j*28,line,23,C['muted'],max_width=648)

connector([(64,1380),(1536,1380)],C['border'],arrow=False,width=1)
text(64,1417,'Solid arrows: main flow   •   Dashed arrows: expanded detail or bounded revision',21,C['muted'],max_width=1472)
text(64,1450,'RAG = retrieval-augmented generation. Reference design; validate controls for each deployment.',21,C['muted'],max_width=1472)
svg.append('</svg>')
svg_path=a.out/'rag-query-path.svg'
png_path=a.out/'rag-query-path.png'
svg_path.write_text('\n'.join(svg)+'\n',encoding='utf8')
im.save(png_path,optimize=True)
report={'dimensions':[W,H], 'text_items':len(text_records), 'text_bounds_checked':True,
        'artifacts':[{ 'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [svg_path,png_path]]}
(a.out/'render-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
