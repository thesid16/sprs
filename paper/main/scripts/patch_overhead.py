#!/usr/bin/env python3
"""
patch_overhead.py — replace the fabricated same-fabric-overhead material.

The v5 draft reported a 1.12x median ABI overhead against a "best
non-deterministic reducer on the same substrate". No such baseline reducer
exists in the codebase and none was ever run: the number, the eight-row
per-instance table, the six-curve figure, and the stacked-bar component
breakdown were all placeholders.

This replaces that material with what the project can actually support:
the structural cost argument (hidden_work_inventory.md Sec.8), anchored on
two genuinely measured quantities -- distance to the composite lower bound
Omega, and the GCI-serialisation inflection at N/G ~ 6-8 that the structural
model predicts and the dataset can falsify.

Idempotent: refuses to run twice.
"""
import re
import sys

MAIN = "main.tex"
START = r"\subsection{Same-Fabric ABI Overhead}"
END = r"\subsection{Tournament Characterisation}"

NEW = r"""\subsection{The Cost of the ABI}\label{sec:results-overhead}

The natural way to price the ABI would be to run, on this same fabric, the
best \emph{non}-deterministic reducer we could construct --- one free to
reassociate, to pick $k$-ary partial sums, and to reshape its tree per
$(G,\text{topology})$ --- and report the ratio $\eta$ of the two makespans.
We did not build that baseline, and we therefore report no measured $\eta$.
We say so plainly because the alternative --- quoting a ratio against a
reducer that does not exist --- would not be a measurement.

What can be said without it is stronger than it first appears. The ABI's cost
is not an empirical accident to be discovered by benchmarking; it is a
consequence of the contract, and the contract is small enough to price
analytically. We give the decomposition below, then test one of its
predictions against the measured data.

\subsubsection{Structural decomposition}

Four constraints, each a direct consequence of the ABI rather than of our
implementation, separate \sprs{} from an unconstrained reducer.

\begin{enumerate}
\item \emph{FBT tree depth.} The ABI fixes $\FBT(N)$, so the dependence
  chain is $\log_2 N$ deep regardless of $G$. An unconstrained reducer may
  form partial sums of arbitrary arity; at fan-in $k$ its depth is
  $\log_k N$, and at $k=G$ it is $\log_G N$. This term grows with $G$ and is
  the irreducible core of the ABI's cost.
\item \emph{Operand-binding forbids reassociation.} Fixing
  $(\mathrm{left}(v),\mathrm{right}(v))$ at every internal node forbids
  regrouping operands by locality. An unconstrained reducer may sum
  PE-local values first and cross the network once; \sprs{} must cross
  wherever the tree says to cross, even when a locality-adjacent regrouping
  would be cheaper.
\item \emph{GCI serialisation.} Consecutive \texttt{GENERATE}s on one PE are
  spaced by $\sv{gci\_gap} = \sv{gci\_latency} + 2 = 6$ cycles. A PE holding
  $\lceil N/G \rceil$ leaves therefore spends at least
  $6\lceil N/G\rceil$ cycles producing them. This binds only while
  $N/G \lesssim 6$--$8$; above that, leaf generation overlaps the reduction
  and stops being critical. Unlike the first two, this term is an artefact
  of \emph{our} GCI, not of the ABI, and a multi-channel leaf interface
  would remove it.
\item \emph{Root-gather fan-in.} The root PE must receive contributions from
  the other $G-1$ PEs, giving at least $\lceil\log_2 G\rceil$ merge stages
  plus one traversal of roughly half the network diameter. This is
  $\mathrm{lb}_{\text{gather}}$ in~\eqref{eq:omega} and it binds any reducer,
  deterministic or not.
\end{enumerate}

Terms 1 and 2 are the price of reproducibility and cannot be engineered away
without abandoning the contract. Terms 3 and 4 are shared with any reducer on
this fabric; term 3 is ours to fix, term 4 is nobody's.

\subsubsection{A falsifiable prediction}

Term 3 makes a specific, checkable claim: leaf generation should stop being
the binding constraint once $N/G$ exceeds roughly $6$--$8$. This is a
prediction about our measured cycle counts, and the suite spans
$N/G$ from $1$ (\sv{med\_full\_torus}) to $64$ (\sv{vlarge\_extreme\_1d}),
so it can fail.

\input{tables/nginflection}

Table~\ref{tab:nginflect} groups the HW-validated instances by $N/G$ and
reports the measured champion cycle count normalised by $\Omega$. If term~3
is right, instances below the inflection should sit closer to the
GCI-dominated bound and the normalised cost should flatten above it.

\subsubsection{Distance to the lower bound}

The one absolute statement we can make is how far the compiler lands from
$\Omega$, the composite lower bound of \S\ref{sec:method-lb}. Because
$\Omega$ bounds \emph{any} schedule on this fabric --- including a
non-deterministic one --- the ratio $\text{cycles}/\Omega$ upper-bounds what
an ideal unconstrained reducer could have saved. It is a weaker statement
than $\eta$, but it is a real one, and it is measured rather than asserted.

\input{tables/omegaratio}

"""


def main():
    src = open(MAIN).read()
    if "The Cost of the ABI" in src:
        print("already patched — nothing to do")
        return 0
    i = src.find(START)
    j = src.find(END)
    if i < 0 or j < 0 or j <= i:
        print("ERROR: could not locate section boundaries", file=sys.stderr)
        return 1
    removed = src[i:j]
    out = src[:i] + NEW + src[j:]
    open(MAIN, "w").write(out)

    n_todo = removed.count(r"\todo{")
    print(f"replaced {len(removed)} chars of fabricated overhead material")
    print(f"  removed {n_todo} \\todo placeholders")
    print(f"  removed tables : {removed.count('begin{tabular}')}")
    print(f"  removed figures: {removed.count('begin{tikzpicture}')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
