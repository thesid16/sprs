# Figure authoring brief

Read `figures/MANIFEST.json` first: it is the contract. It lists every figure, its
purpose, the prose it must displace, its data source, and a distinct brief for each
of the four variants.

## Hard rules

1. **TikZ or PGFPlots only.** No external images, no matplotlib, no bitmaps.
2. **Body only.** Each variant file contains just the `tikzpicture` (or a pgfplots
   `axis` inside one). No `\begin{figure}`, no `\caption`, no document preamble —
   `main.tex` supplies those.
3. **Fixed size, not `\linewidth`.** IEEE single column is 3.5in = 8.9cm; use
   `width=8.6cm`. Double column (`figure*`) is 7.16in = 18.2cm; use `width=17.6cm`.
   A fixed size means the guide preview is identical to what the paper typesets.
   `\linewidth` renders correctly in the paper but wrong in the standalone wrapper.
4. **Never invent a number.** Every value must come from a `data/*.tex` macro, a
   `tables/*.tex` file, or a data file you cite in a comment. Prefer the macro over a
   literal so the figure cannot drift from the text. If you cannot source it, leave
   it out.
5. **Greyscale-safe.** Distinguish series by marker and dash pattern, never by colour
   alone. TPDS is printed in black and white.
6. **Variants must differ in EXPLANATORY STRATEGY**, not styling. A recolour or a
   re-layout is not an alternate. Each of b, c, d should argue the point a genuinely
   different way — the manifest says how. The author will choose between them.
7. **Header comment required** in every file: what it shows, its data source, and one
   line on why this strategy differs from the others.

## Build and check your work

    bash figures/render_variants.sh        # renders every variant to PDF + PNG

It must report `ok` for each of your files. Then LOOK at your PNG in
`figures/rendered/` with the Read tool — do not assume it is right because it
compiled. Check specifically: nothing overflows the axis, the legend does not cover
data, labels do not collide, and the figure is legible at print size. Iterate until
it is clean. A figure that compiles but is unreadable is not done.

## Worked reference

`figures/variants/f10_selection/{a,b,c,d}.tex` are complete and reviewed. Read all
four before starting: they show the expected size discipline, the comment header, how
to draw a confidence band as an explicit polygon, how to place a legend clear of the
data, and what "four genuinely different strategies" means in practice.

## Gotchas already hit

- An inline `%` comment at the end of an axis-option line swallows the following
  comma and merges two options. Put comments on their own line.
- `pgfplots` has no `fillbetween` library loaded. Draw a confidence band as one
  closed polygon: forward along the lower bound, back along the upper.
- The wrapper loads every `data/*_macros.tex`, so generated macros are available in
  standalone renders exactly as in the paper.
