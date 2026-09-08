#!/usr/bin/env python3
"""
gen_guide.py -- build the figure-alternates guide as a single self-contained HTML file.

Reads figures/MANIFEST.json and the PNGs in figures/rendered/, and emits one page
showing, for every figure, the four variants side by side with the strategy each takes,
the prose it replaces, and its data source. PNGs are inlined as base64 data URIs so the
page is one file with no external image requests.

The variant file rendered here is the same file main.tex \\input s, so the guide shows
exactly what the paper typesets -- there is no second rendering path that can drift.

Usage: python3 scripts/gen_guide.py [-o figures/GUIDE.html]
"""
import argparse
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)


def datauri(path):
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode('ascii')


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


CSS = """
:root {
  --bg:#f7f8fa; --card:#ffffff; --fg:#14171c; --mut:#5c6672; --line:#dde1e7;
  --accent:#0f5d63; --accent-soft:#e3eff0; --shadow:0 1px 2px rgba(20,23,28,.05);
  --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --serif:"IBM Plex Serif",Georgia,"Times New Roman",serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#101317; --card:#171b21; --fg:#e6e9ee; --mut:#98a2b0; --line:#252b33;
  --accent:#5fd4dc; --accent-soft:#16323666; --shadow:0 1px 2px rgba(0,0,0,.4);
} }
:root[data-theme="dark"] {
  --bg:#101317; --card:#171b21; --fg:#e6e9ee; --mut:#98a2b0; --line:#252b33;
  --accent:#5fd4dc; --accent-soft:#16323666; --shadow:0 1px 2px rgba(0,0,0,.4);
}
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--fg); margin:0; font-family:var(--sans);
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased; }
.wrap { display:grid; grid-template-columns:200px minmax(0,1fr);
  max-width:1520px; margin:0 auto; }
@media (max-width:860px) { .wrap { grid-template-columns:1fr; } .rail { display:none; } }

header { grid-column:1/-1; padding:3rem 2rem 1.7rem; border-bottom:1px solid var(--line); }
h1 { font-family:var(--serif); font-size:2rem; font-weight:400; margin:0;
  letter-spacing:-.015em; text-wrap:balance; }
.lede { font-family:var(--serif); color:var(--mut); max-width:64ch;
  margin:.75rem 0 0; font-size:1.02rem; }
.counts { display:flex; gap:2rem; margin-top:1.5rem; flex-wrap:wrap;
  font-variant-numeric:tabular-nums; }
.counts div { display:flex; flex-direction:column; }
.counts b { font-size:1.5rem; font-weight:500; line-height:1.1; }
.counts span { font-size:.71rem; text-transform:uppercase; letter-spacing:.09em;
  color:var(--mut); margin-top:.25rem; }

.rail { padding:1.7rem 0 3rem 2rem; position:sticky; top:0; align-self:start;
  max-height:100vh; overflow-y:auto; }
.rail a { display:block; font-family:var(--mono); font-size:.76rem; color:var(--mut);
  text-decoration:none; padding:.3rem 0 .3rem .65rem; border-left:2px solid transparent;
  margin-left:-.65rem; }
.rail a:hover { color:var(--accent); border-left-color:var(--accent); }
.rail a:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }

main { padding:0 2rem 4rem; min-width:0; }
section { padding:2.5rem 0; border-bottom:1px solid var(--line); }
section:last-of-type { border-bottom:none; }
.fid { font-family:var(--mono); font-size:1rem; font-weight:500; margin:0; }
.tags { display:flex; gap:.45rem; margin-top:.5rem; flex-wrap:wrap; }
.tag { font-size:.67rem; text-transform:uppercase; letter-spacing:.07em;
  color:var(--mut); border:1px solid var(--line); border-radius:2px;
  padding:.14rem .45rem; }
.tag.wide { color:var(--accent); border-color:var(--accent); }
.purpose { font-family:var(--serif); margin:.95rem 0 .55rem; max-width:70ch; }
.meta { color:var(--mut); font-size:.82rem; margin:.22rem 0; max-width:78ch; }
.meta b { font-weight:500; color:var(--fg); }
.meta code { font-family:var(--mono); font-size:.76rem; }
.srcline { overflow-x:auto; white-space:nowrap; padding-bottom:.25rem; }

.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(345px,1fr));
  gap:1.15rem; margin-top:1.55rem; }
.tile { margin:0; background:var(--card); border:1px solid var(--line);
  border-radius:4px; padding:.85rem; box-shadow:var(--shadow);
  display:flex; flex-direction:column; }
.tile.chosen { border-color:var(--accent); }
figcaption { display:flex; align-items:baseline; gap:.55rem; margin-bottom:.6rem; }
.k { font-family:var(--mono); font-size:.74rem; font-weight:500;
  text-transform:uppercase; letter-spacing:.08em; color:var(--mut); }
.tile.chosen .k { color:var(--accent); }
.inpaper { font-size:.67rem; color:var(--accent); background:var(--accent-soft);
  border-radius:2px; padding:.1rem .4rem; letter-spacing:.03em; }
.tile img { width:100%; height:auto; display:block; background:#fff; border-radius:2px; }
.brief { font-family:var(--serif); font-size:.86rem; color:var(--mut); margin:.78rem 0 0; }
.missing { padding:3rem 0; text-align:center; color:var(--mut); font-family:var(--mono);
  font-size:.78rem; border:1px dashed var(--line); border-radius:2px; }
.warn { margin:1.25rem 0 0; padding:.68rem .85rem; border-left:2px solid var(--accent);
  background:var(--accent-soft); font-size:.85rem; }
footer { grid-column:1/-1; padding:1.9rem 2rem 3rem; color:var(--mut);
  font-size:.8rem; border-top:1px solid var(--line); }
footer code { font-family:var(--mono); font-size:.76rem; }
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-o', '--out', default=os.path.join(PAPER, 'figures', 'GUIDE.html'))
    a = ap.parse_args()

    man = json.load(open(os.path.join(PAPER, 'figures', 'MANIFEST.json')))
    figs = man['figures']

    missing, cards = [], []
    for f in figs:
        fid = f['id']
        vs = []
        for k in 'abcd':
            png = datauri(os.path.join(PAPER, 'figures', 'rendered', f'{fid}_{k}.png'))
            if png is None:
                missing.append(f'{fid}_{k}')
            vs.append({'k': k, 'png': png, 'brief': f.get('variants', {}).get(k, '')})
        cards.append({'f': f, 'vs': vs})

    parts = []
    for c in cards:
        f, tiles = c['f'], []
        for v in c['vs']:
            chosen = ' chosen' if v['k'] == 'a' else ''
            badge = '<span class="inpaper">in the paper</span>' if v['k'] == 'a' else ''
            img = (f'<img src="{v["png"]}" alt="{esc(f["id"])} variant {v["k"]}" loading="lazy">'
                   if v['png'] else '<div class="missing">not rendered</div>')
            tiles.append(
                f'<figure class="tile{chosen}">'
                f'<figcaption><span class="k">{v["k"]}</span>{badge}</figcaption>'
                f'{img}<p class="brief">{esc(v["brief"])}</p></figure>')
        width = ('<span class="tag wide">double column</span>' if f.get('doublecol')
                 else '<span class="tag">single column</span>')
        parts.append(
            f'<section id="{esc(f["id"])}">'
            f'<p class="fid">{esc(f["id"])}</p>'
            f'<div class="tags"><span class="tag">{esc(f.get("section",""))}</span>{width}</div>'
            f'<p class="purpose">{esc(f.get("purpose",""))}</p>'
            f'<p class="meta"><b>Replaces:</b> {esc(f.get("displaces","—"))}</p>'
            f'<p class="meta srcline"><b>Data:</b> <code>{esc(f.get("data","—"))}</code></p>'
            f'<div class="grid">{"".join(tiles)}</div></section>')

    nav = ''.join(f'<a href="#{esc(c["f"]["id"])}">{esc(c["f"]["id"])}</a>' for c in cards)
    rendered = sum(1 for c in cards for v in c['vs'] if v['png'])
    warn = ('<p class="warn">Not yet rendered: '
            + ', '.join(esc(m) for m in missing) + '</p>') if missing else ''

    html = f"""<title>SPRS Figure Alternates</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header>
  <h1>SPRS Figure Alternates</h1>
  <p class="lede">Every figure in the submission with three alternates, each arguing the
  same point a different way rather than restyling it. The variant marked <em>in the
  paper</em> is the one currently set; the rest are yours to swap in. Each render comes
  from the same TikZ source the paper typesets, so what you see here is what prints.</p>
  <div class="counts">
    <div><b>{len(cards)}</b><span>figures</span></div>
    <div><b>{rendered}</b><span>variants rendered</span></div>
    <div><b>{sum(1 for c in cards if c['f'].get('doublecol'))}</b><span>double column</span></div>
  </div>
  {warn}
</header>
<nav class="rail">{nav}</nav>
<main>{''.join(parts)}</main>
<footer>Generated by <code>scripts/gen_guide.py</code> from
<code>figures/MANIFEST.json</code> and <code>figures/rendered/</code>. Rebuild with
<code>bash figures/render_variants.sh &amp;&amp; python3 scripts/gen_guide.py</code>.
Single-column figures are drawn at 8.6&thinsp;cm, double at 17.6&thinsp;cm &mdash; the
widths IEEE actually gives you.</footer>
</div>
"""
    with open(a.out, 'w', encoding='utf-8') as fh:
        fh.write(html)
    print(f"wrote {a.out}  ({len(cards)} figures, {rendered}/{len(cards)*4} variants, "
          f"{os.path.getsize(a.out)/1048576:.1f} MiB)")
    if missing:
        print("  missing renders: " + ", ".join(missing))
    return 0


if __name__ == '__main__':
    sys.exit(main())
