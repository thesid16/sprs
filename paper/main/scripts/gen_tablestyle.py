#!/usr/bin/env python3
r"""
gen_tablestyle.py -- shared LaTeX table styling for every generator in this
tree.  IMPORTED, never run: it is not in the Makefile's `tables` target and
writes no file of its own.

Why it exists.  Every generated table used to emit its own ad-hoc tabular:
booktabs rules but no tint, units repeated in every cell, and numeric columns
whose decimal points did not line up because the generator used `%.3g`.  The
figures were colourised from figures/_palette.tex; the tables were not.  This
module is the one place the table look is defined, so the two cannot drift.

WHAT IS AND IS NOT AVAILABLE.  main.tex loads booktabs, array, multirow,
tabularx and xcolor -- it does NOT load colortbl (verified: no `Package:
colortbl` line in main.log), and this task may not edit main.tex.  So
\rowcolor, \cellcolor and \columncolor are unavailable and a row tint has to
be drawn some other way.

  \spband{<colour>}  placed as the first token of a row draws a zero-size,
                     zero-width rule spanning the whole table width.  Because
                     an \halign row is shipped out left-to-right, the rule is
                     painted BEFORE the cells of that row, so the text lands on
                     top of the tint exactly as \rowcolor would put it.  Height
                     and depth are \arraystretch times \strutbox's, i.e. the
                     exact height of an array row, so consecutive bands tile
                     without a seam.

The table width the band needs is not known until the table is typeset, so
each emitted file defines its tabular once as \spTBL, measures it into a box
(the band is zero-size, so it does not perturb the measurement), and then
typesets it for real with \spwd set.  Two passes over the same macro; the body
still appears exactly once in the file.

  \spbar{<colour>}{<len>}          solid magnitude bar
  \spspan{<track>}{<off>}{<col>}{<len>}
                                   a bar segment on a light full-range track,
                                   for ranges and confidence intervals
  \sphd{<text>}                    header cell

Colours come from figures/_palette.tex only (\spBlue, \spVerm, \spGreen,
\spAmber, \spMute, \spInk and the fills \spBlueF, \spVermF, \spGreenF,
\spAmberF, \spSkyF, \spGrid).  Nothing here defines a colour of its own.
"""

# ----------------------------------------------------------------- style block
# Emitted at the head of every generated table.  \providecommand-equivalent
# guard: several of these files can be \input into one document, and the length
# and box registers must be allocated once.
STYLE = r"""% ---- shared table style (figures/_palette.tex); see scripts/gen_tablestyle.py.
% main.tex does not load colortbl, so a row tint is a zero-size rule emitted at
% the start of the row and painted under the cells that follow it.
% Defined once per document: these files are \input INSIDE float environments,
% so the definitions must be global or the second table finds them gone.
\makeatletter
\@ifundefined{spwd}{\begingroup\globaldefs\@ne
  \newlength{\spwd}%
  \newsavebox{\spbox}%
  \newcommand{\spmeasure}[1]{\sbox{\spbox}{#1}\spwd=\wd\spbox}%
  \newcommand{\spband}[1]{\rlap{\raisebox{0pt}[0pt][0pt]{\textcolor{#1}{%
    \rule[-\dimexpr\arraystretch\dp\strutbox+0.35pt\relax]{\spwd}%
    {\dimexpr\arraystretch\ht\strutbox+\arraystretch\dp\strutbox+0.7pt\relax}}}}}%
  \newcommand{\spbar}[2]{\textcolor{#1}{\rule[0.04em]{#2}{0.40em}}}%
  \newcommand{\spspan}[4]{\makebox[#1][l]{\rlap{\textcolor{spSkyF}%
    {\rule[0.04em]{#1}{0.40em}}}\hspace*{#2}\textcolor{#3}%
    {\rule[0.04em]{#4}{0.40em}}}}%
  \newcommand{\sphd}[1]{\textbf{#1}}%
\endgroup}{}
\makeatother"""

HEAD = "spBlueF"      # header band
ZEBRA = "spGrid"      # body banding
GOOD = "spGreenF"     # confirmed / summary row
WARN = "spAmberF"     # the one row that is not like the others


STYLE_FILE = "tables/_style.tex"


def style():
    r"""What every generated table emits in place of the style block.

    The block itself lives in tables/_style.tex (written by main() below and
    listed in scripts/verify_tables.py's MANIFEST), so eighteen tables do not
    each carry twenty lines of boilerplate.  The path is relative to the main
    document, which is what \input wants.
    """
    return [r"\input{tables/_style}"]


def wrap(tabular_lines):
    r"""Wrap a tabular in the measure-then-typeset idiom.

    The tabular body appears once, inside \spTBL.  \spmeasure sets \spwd to its
    natural width; the bands are zero-size so the measuring pass sees exactly
    the same width the real pass produces.
    """
    out = style()
    out.append(r"\def\spTBL{%")
    out += tabular_lines
    out.append(r"}%")
    out.append(r"\spmeasure{\spTBL}\spTBL")
    return out


def band(colour):
    return "\\spband{%s}" % colour


def zebra(i, first_is_tinted=False):
    """Band token for body row i (0-based), or '' for an untinted row."""
    return band(ZEBRA) if (i % 2 == (0 if first_is_tinted else 1)) else ""


# ------------------------------------------------------- numeric formatting
def align_decimal(values):
    r"""Pad a column of already-formatted numbers with \phantom so that the
    decimal points line up under right alignment, WITHOUT changing any printed
    digit.  IEEEtran sets Times, whose digits are tabular-width, so equal
    fractional widths are sufficient.

    align_decimal(["4", "2.5", "23.4375"]) ->
        ["4\\phantom{.0000}", "2.5\\phantom{000}", "23.4375"]
    """
    fr = []
    for v in values:
        s = str(v)
        fr.append(len(s.split(".", 1)[1]) if "." in s else -1)
    w = max(fr) if fr else -1
    if w <= 0:
        return [str(v) for v in values]
    out = []
    for v, f in zip(values, fr):
        s = str(v)
        if f == w:
            out.append(s)
        elif f < 0:
            out.append(s + r"\phantom{." + "0" * w + "}")
        else:
            out.append(s + r"\phantom{" + "0" * (w - f) + "}")
    return out


def barlen(value, vmax, full_em=4.0, floor_em=0.0):
    r"""Length string for a magnitude bar, as an absolute em width."""
    if vmax <= 0:
        return "0pt"
    f = max(0.0, min(1.0, float(value) / float(vmax)))
    L = floor_em + f * (full_em - floor_em)
    return "%.3fem" % L if L > 0.001 else "0pt"


def bar(value, vmax, colour="spBlue", full_em=4.0):
    return "\\spbar{%s}{%s}" % (colour, barlen(value, vmax, full_em))


def span(lo, hi, vlo, vhi, colour="spVerm", full_em=4.0):
    r"""A [lo,hi] segment drawn on a light track covering [vlo,vhi]."""
    rng = float(vhi) - float(vlo)
    if rng <= 0:
        return "\\spspan{%.3fem}{0pt}{%s}{%.3fem}" % (full_em, colour, full_em)

    def pos(v):
        return max(0.0, min(1.0, (float(v) - float(vlo)) / rng)) * full_em
    a, b = pos(lo), pos(hi)
    if b - a < 0.09:                       # keep a degenerate interval visible
        b = min(full_em, a + 0.09)
    return "\\spspan{%.3fem}{%.3fem}{%s}{%.3fem}" % (full_em, a, colour, b - a)


def main():
    """Write tables/_style.tex.  Run from the `tables` target of the Makefile."""
    import datetime
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    paper = os.path.dirname(here)
    dst = os.path.join(paper, STYLE_FILE)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    hdr = ("% GENERATED — do not edit by hand.\n"
           "% script : scripts/gen_tablestyle.py\n"
           "% source : figures/_palette.tex (colours) + the LaTeX preamble of\n"
           "%          main.tex, which loads booktabs/array/xcolor but NOT colortbl\n"
           f"% date   : {datetime.date.today().isoformat()}\n"
           "% note   : \\input by every generated table; defines the shared row\n"
           "%          tint, magnitude bar and range-span macros exactly once\n")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(hdr + STYLE + "\n")
    print(f"  wrote {dst}")


if __name__ == "__main__":
    main()
