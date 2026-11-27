#!/usr/bin/env python3
"""Figure: host-level recall per MAWILab anomaly class for rules, analyst hypotheses, tree.

usage: fig_recall.py HUNT_EVAL_JSON OUT_PDF [--min-n 3]
Classes with fewer than --min-n held-out anomalous hosts are pooled as "other".
"""
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# reference categorical palette, slots 1-3 (validated: CVD dE 9.2, normal dE 27.6);
# slot 3 is below 3:1 contrast, so every bar carries a visible k/n label.
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]
INK, INK2 = "#0b0b0b", "#52514e"


def pooled(d, keep):
    out = {t: list(d.get(t, [0, 0])) for t in keep}
    oth = [0, 0]
    for t, (k, n) in d.items():
        if t not in keep:
            oth[0] += k
            oth[1] += n
    if oth[1]:
        out["other"] = oth
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_json")
    ap.add_argument("out_pdf")
    ap.add_argument("--min-n", type=int, default=3)
    a = ap.parse_args()
    e = json.load(open(a.eval_json))
    series = [("Mined rules", e["playbook_recall_by_taxonomy"]),
              ("Analyst hypotheses", e["playbook_expert_recall_by_taxonomy"]),
              ("Decision tree", e["tree_recall_by_taxonomy"])]
    base = series[0][1]
    keep = sorted([t for t, (k, n) in base.items() if n >= a.min_n], key=lambda t: -base[t][1])
    data = [(name, pooled(d, keep)) for name, d in series]
    classes = list(data[0][1].keys())

    plt.rcParams.update({"font.family": "serif", "font.size": 7, "axes.edgecolor": INK2,
                         "axes.labelcolor": INK, "xtick.color": INK2, "ytick.color": INK})
    h = 0.24
    fig, ax = plt.subplots(figsize=(3.45, 0.42 * len(classes) + 0.55))
    for j, (name, d) in enumerate(data):
        for i, c in enumerate(classes):
            k, n = d[c]
            r = k / n if n else 0.0
            y = i + (j - 1) * (h + 0.02)
            ax.barh(y, r, height=h, color=COLORS[j], edgecolor="white", linewidth=0.6,
                    label=name if i == 0 else None)
            ax.text(r + 0.012, y, "%d/%d" % (k, n), va="center", fontsize=5.5, color=INK2)
    ax.set_yticks(range(len(classes)))
    ax.set_yticklabels(["%s (n=%d)" % (c, data[0][1][c][1]) for c in classes])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.12)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xlabel("Recall on held-out anomalous hosts")
    ax.grid(axis="x", color="#e4e3df", linewidth=0.5)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(loc="lower center", bbox_to_anchor=(0.45, 1.0), ncol=3, frameon=False,
              fontsize=6, handlelength=1.2, columnspacing=1.0)
    fig.tight_layout(pad=0.3)
    fig.savefig(a.out_pdf)
    fig.savefig(a.out_pdf.replace(".pdf", ".png"), dpi=200)


if __name__ == "__main__":
    main()
