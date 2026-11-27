#!/usr/bin/env python3
"""Uncertainty for existing results (added 2026-10-26; no new experiments).

1. MAWI (results_dc/mine_s{0..4}/results/xai_L3.json): host F1 with a 95%
   bootstrap interval per split and method, resampling the held-out hosts
   (multinomial over the four confusion cells, B draws, fixed seed); the same
   for the row-permuted copies; permutation loss against the interval
   half-width; per-split ranking and an exact sign test over the five splits.
2. Synthetic counts (results_review_2026-10-21/SUMMARY.md): Wilson 95%
   intervals for event-level recall and for zero counts.
3. Clean control (results_xai/noise0_s{1,2,3}/mine_b1/results/xai_L3.json):
   pooled host counts of the order-aware queries with Wilson intervals.

usage: stats_1026.py OUT_MD
"""
import json
import math
import os
import numpy as np
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evaluate import wilson  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
B = 2000


def f1(tp, fp, fn):
    d = 2 * tp + fp + fn
    return 2 * tp / d if d else 0.0


def boot_f1(c, rng):
    tp, fp, fn, tn = c
    n = tp + fp + fn + tn
    draws = rng.multinomial(n, [tp / n, fp / n, fn / n, tn / n], size=B)
    a, b, d = draws[:, 0], draws[:, 1], draws[:, 2]
    den = 2 * a + b + d
    vals = np.sort(np.where(den > 0, 2 * a / np.maximum(den, 1), 0.0))
    return float(vals[int(0.025 * B)]), float(vals[int(0.975 * B) - 1])


def binom_sign_p(k, n):
    """Two-sided exact sign test p for k successes of n."""
    m = min(k, n - k)
    p = sum(math.comb(n, i) for i in range(m + 1)) / 2 ** n
    return min(1.0, 2 * p), sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n


def main():
    out = []
    rng = np.random.default_rng(20261026)
    out.append("# Uncertainty for existing results (code/stats_1026.py, 2026-10-26)\n")
    out.append("Bootstrap: %d resamples of the held-out hosts per split (multinomial over the confusion "
               "cells; percentile 95%% interval; seed 20261026). Intervals are per method; methods share "
               "hosts, so comparing two separate intervals is conservative.\n" % B)
    out.append("## 1. MAWI host F1 per split\n")
    out.append("| split | method | view | F1 | 95% CI | F1 perm. | 95% CI perm. | loss | CI half-width |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    per = {}
    maxratio = []
    disjoint = []
    for s in range(5):
        d = json.load(open(os.path.join(ROOT, "results_dc/mine_s%d/results/xai_L3.json" % s)))
        for m in d["methods"]:
            if "host" not in m or not m["method"] in ("tree_d3", "ripper", "gbm+shap", "anchors"):
                continue
            h, p = m["host"], m["host_permuted"]
            c = (h["tp"], h["fp"], h["fn"], h["tn"])
            cp = (p["tp"], p["fp"], p["fn"], p["tn"])
            lo, hi = boot_f1(c, rng)
            plo, phi = boot_f1(cp, rng)
            v, vp = f1(*c[:3]), f1(*cp[:3])
            hw = (hi - lo) / 2
            per.setdefault(s, {})[(m["method"], m["view"])] = (v, lo, hi)
            maxratio.append((v - vp, hw, s, m["method"], m["view"]))
            if plo > hi or phi < lo:
                disjoint.append("split %d %s %s" % (s, m["method"], m["view"]))
            out.append("| %d | %s | %s | %.4f | [%.4f, %.4f] | %.4f | [%.4f, %.4f] | %.4f | %.4f |" %
                       (s, m["method"], m["view"], v, lo, hi, vp, plo, phi, v - vp, hw))
    out.append("")
    big = max(maxratio)
    out.append("Largest permutation loss: %.4f (split %d, %s %s); its F1 interval half-width %.4f." %
               (big[0], big[2], big[3], big[4], big[1]))
    exceed = [r for r in maxratio if r[0] > r[1]]
    out.append("Rows whose loss exceeds the half-width of the unpermuted F1 interval: %d of %d %s\n" %
               (len(exceed), len(maxratio), ["split %d %s %s loss %.4f hw %.4f" % (r[2], r[3], r[4], r[0], r[1])
                                             for r in exceed]))
    out.append("Rows whose unpermuted and permuted F1 intervals are disjoint: %d of %d %s\n" %
               (len(disjoint), len(maxratio), disjoint))
    out.append("## 2. Ranking over the five splits\n")
    gb = ("gbm+shap", "host")
    wins = {}
    sep = {}
    for s in range(5):
        g = per[s][gb]
        for k, v in per[s].items():
            if k == gb:
                continue
            wins.setdefault(k, 0)
            sep.setdefault(k, 0)
            if g[0] > v[0]:
                wins[k] += 1
            if g[1] > v[2]:
                sep[k] += 1
    for k in sorted(wins):
        p2, p1 = binom_sign_p(wins[k], 5)
        out.append("- GBM host vs %s %s: higher F1 on %d of 5 splits (exact sign test two-sided p = %.4f, "
                   "one-sided p = %.4f); intervals disjoint on %d of 5 splits" % (k[0], k[1], wins[k], p2, p1, sep[k]))
    out.append("")
    out.append("## 3. Wilson 95% intervals for synthetic counts (results_review_2026-10-21/SUMMARY.md)\n")
    for label, k, n in [("PSI-Miner G=8 three episodes, event recall", 996, 1314),
                        ("PSI-Miner G=8 three episodes, delay 7-8 s", 0, 318),
                        ("PSI-Miner G=8 one episode, event recall", 341, 438),
                        ("PSI-Miner G=8 one episode, delay 7-8 s", 0, 97),
                        ("PSI-Miner G=8 benign B seconds matched (three episodes)", 0, 1449),
                        ("RIPPER L=8 G=8 three episodes, event recall", 1314, 1314)]:
        lo, hi = wilson(k, n)
        out.append("- %s: %d/%d = %.4f, [%.4f, %.4f]" % (label, k, n, k / n, lo, hi))
    out.append("")
    out.append("## 4. Clean control, pooled over seeds 1-3 (results_xai/noise0_s*/mine_b1/results/xai_L3.json)\n")
    pool = {}
    for s in (1, 2, 3):
        d = json.load(open(os.path.join(ROOT, "results_xai/noise0_s%d/mine_b1/results/xai_L3.json" % s)))
        for m in d["methods"]:
            if "host" not in m:
                continue
            key = (m["method"], m["view"])
            h = m["host"]
            a = pool.setdefault(key, [0, 0, 0, 0])
            for i, c in enumerate(("tp", "fp", "fn", "tn")):
                a[i] += h[c]
    for k, (tp, fp, fn, tn) in sorted(pool.items()):
        r, p = wilson(tp, tp + fn), wilson(tp, tp + fp)
        out.append("- %s %s: tp %d fp %d fn %d tn %d; recall %d/%d [%.4f, %.4f]; precision %d/%d [%.4f, %.4f]" %
                   (k[0], k[1], tp, fp, fn, tn, tp, tp + fn, r[0], r[1], tp, tp + fp, p[0], p[1]))
    open(sys.argv[1], "w").write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
