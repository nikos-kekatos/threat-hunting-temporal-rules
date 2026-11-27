#!/usr/bin/env python3
"""Fig. delay sweep: host F1 and explanation size against the delay range [1, G], read from
results_xai/SUMMARY.md (mean over three seeds; size from seed 1).

Series: PSI-Miner (bias +1, rule selected on training hosts), RIPPER with L = 3 and L = 8, Anchors (L = 3).
Two stacked panels on one x axis (no dual axis). Colour (validated categorical slots 1-4) is backed by a
marker and line style per series and by direct labels, so the figure reads in greyscale.
usage: fig_delay.py [SUMMARY.md] [OUT.pdf]
"""
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
SUMMARY = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "results_xai", "SUMMARY.md")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "fig_delay.pdf")

# (label, lag budget, method, view, colour, marker, linestyle)
SERIES = [
    ("PSI-Miner", "L3", "psiminer_trainsel_b1", "temporal", "#2a78d6", "o", "-"),
    ("RIPPER, L=8", "L8", "ripper", "bin", "#eb6834", "s", "--"),
    ("RIPPER, L=3", "L3", "ripper", "bin", "#1baf7a", "^", ":"),
    ("Anchors, L=3", "L3", "anchors", "bin", "#eda100", "D", "-."),
]
GS = [2, 4, 6, 8]
INK, MUTED, GRID = "#1f1f1e", "#6b6a63", "#e4e3dc"


def load():
    rows = {}
    for line in open(SUMMARY):
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) == 8 and c[0].startswith("gap1-"):
            rows[(int(c[0][5:]), c[1], c[2], c[3])] = (float(c[4].split()[0]), c[7])
    return rows


def size_of(s):
    m = re.search(r"(\d+) conds", s) or re.search(r"(\d+) literals", s)
    return int(m.group(1))


def main():
    rows = load()
    plt.rcParams.update({"font.family": "serif", "font.size": 7, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "pdf.fonttype": 42})
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(3.45, 2.9), sharex=True,
                                 gridspec_kw={"height_ratios": [1.15, 1], "hspace": 0.12})
    ends = []
    for label, L, meth, view, col, mk, ls in SERIES:
        f1 = [rows[(g, L, meth, view)][0] for g in GS]
        sz = [size_of(rows[(g, L, meth, view)][1]) for g in GS]
        for ax, y in ((a1, f1), (a2, sz)):
            ax.plot(GS, y, color=col, marker=mk, ls=ls, lw=1.6, ms=4.5,
                    markeredgecolor="white", markeredgewidth=0.8, label=label, zorder=3)
        ends.append([f1[-1], label])
    # direct labels at the right end, dodged so that no two are closer than GAP in F1 units
    GAP = 0.05
    ends.sort(key=lambda e: -e[0])
    ypos = []
    for y, _ in ends:
        ypos.append(min(y, ypos[-1] - GAP) if ypos else y)
    for (y, label), yl in zip(ends, ypos):
        a1.annotate(label, (GS[-1], y), xytext=(GS[-1] + 0.25, yl), textcoords="data",
                    va="center", fontsize=6.5, color=INK)
    a1.plot([1.7, 8], [0.645, 0.645], color=MUTED, lw=0.8, ls=(0, (2, 2)), zorder=1)
    a1.text(1.75, 0.632, "flags every host (0.645)", fontsize=6, color=MUTED, va="top")
    a1.set_ylabel("Host F1")
    a1.set_ylim(0.45, 1.03)
    a2.set_yscale("log")
    a2.set_yticks([2, 5, 10, 20, 50, 100])
    a2.set_yticklabels(["2", "5", "10", "20", "50", "100"])
    a2.minorticks_off()
    a2.set_ylabel("Size (literals\nor conditions)")
    a2.set_xlabel("Upper bound $G$ of the delay range $[1, G]$ (s)")
    a2.set_xticks(GS)
    for ax in (a1, a2):
        ax.grid(axis="y", color=GRID, lw=0.6)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    a1.set_xlim(1.7, 10.4)
    a1.legend(loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=6, frameon=False, ncol=4,
              handlelength=2.2, columnspacing=0.9, handletextpad=0.4, borderaxespad=0.2)
    fig.savefig(OUT, bbox_inches="tight")
    fig.savefig(OUT.replace(".pdf", ".png"), dpi=200, bbox_inches="tight")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
