#!/usr/bin/env python3
"""Event-level recall by planted delay for the synthetic delay sweep (review 2026-10-21, item 2).

Host recall counts a host once if ANY of its episodes is matched, so a query that covers delays up to
6 s can reach host recall near 1 at G = 8 with three episodes per host. This script scores every
episode of every anomalous held-out host separately:
  * an episode is an A second (SYN_DOM, syn share 100 %, 12 packets) at t and its B second (ANOM) at t+g;
  * PSI-Miner (rule selected by host F1 on the training hosts, as in compare_xai.py) matches the episode
    when the antecedent completes at some second u with t+g in [u+lo, u+hi];
  * a bin-view model (tree d3, RIPPER, GBM, retrained exactly as in compare_xai.py) or the modal anchor
    (read from results/xai_L<L>.json) matches the episode when it is positive in the B second, which is
    the second its training label marks.
Output: results/event_recall.json under MINE_DIR with, per method and lag budget, host P/R/F1 (as a
cross-check against xai_L<L>.json), event recall overall and per delay g (matched/total).

usage: event_recall.py MINE_DIR [--lags 3,8] [--seed 1] [--max-neg-bins 50000]
"""
import argparse
import collections
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_xai import (bin_matrix, bin_train, lag_names, ripper_predictor, train_f1)  # noqa: E402
from evaluate import completions, host_metrics, load_traces, parse_antecedent  # noqa: E402


def episodes(rows):
    """(A second, B second) pairs of one anomalous host: B = ANOM second, A = latest SYN event before it."""
    out = []
    for i, r in enumerate(rows):
        if r["anom"] >= 1:
            a = [j for j in range(i) if rows[j]["syn_pct"] == 100 and rows[j]["pkts"] == 12]
            out.append((a[-1] if a else None, i))
    return out


def tally(per_host_hits, eps, labels, beps=None):
    """per_host_hits: host -> set of matched B indices; returns event recall overall and by delay, and
    the share of benign B seconds matched (event-level false-alarm rate)."""
    by = collections.defaultdict(lambda: [0, 0])
    for h, ep in eps.items():
        for a, b in ep:
            g = (b - a) if a is not None else -1
            by[g][1] += 1
            if b in per_host_hits.get(h, set()):
                by[g][0] += 1
    k = sum(v[0] for v in by.values())
    n = sum(v[1] for v in by.values())
    bk = sum(1 for h, bs in (beps or {}).items() for b in bs if b in per_host_hits.get(h, set()))
    bn = sum(len(bs) for bs in (beps or {}).values())
    return {"event_recall": round(k / n, 4) if n else 0.0, "matched": k, "episodes": n,
            "benign_b_matched": bk, "benign_b_total": bn,
            "by_delay": {str(g): {"matched": v[0], "total": v[1], "recall": round(v[0] / v[1], 4)}
                         for g, v in sorted(by.items())}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mine_dir")
    ap.add_argument("--lags", default="3,8")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-neg-bins", type=int, default=50000)
    a = ap.parse_args()

    split = list(csv.DictReader(open(os.path.join(a.mine_dir, "split.csv"))))
    labels = {s["trace"]: s["class"] == "anomalous" for s in split}
    test = load_traces(os.path.join(a.mine_dir, "mining", "test"),
                       [s["trace"] for s in split if s["split"] == "test"])
    train = load_traces(os.path.join(a.mine_dir, "mining", "ordered"),
                        [s["trace"] for s in split if s["split"] == "train"])
    eps = {h: episodes(rows) for h, rows in test.items() if labels[h]}
    # benign B seconds (many destination ports, 12 packets): matching one is an event-level false alarm
    beps = {h: [i for i, r in enumerate(rows) if r["ndport"] == 20 and r["pkts"] == 12]
            for h, rows in test.items() if not labels[h]}
    out = {"mine_dir": a.mine_dir, "n_test": len(test), "n_anom_test": len(eps), "methods": []}

    # PSI-Miner, rule selected on training hosts
    ev = json.load(open(os.path.join(a.mine_dir, "results", "hunt_eval.json")))
    rules = [r for r in ev["rules"]["ordered"] if r["consequent"].strip() == "ANOM"]
    if rules:
        r = max(rules, key=lambda r: train_f1(r, train, labels))
        conjs, gaps = parse_antecedent(r["antecedent"])
        lo, hi = int(round(r["lo"])), int(round(r["hi"]))
        flags, hits = {}, {}
        for h, rows in test.items():
            m = completions(conjs, gaps, rows)
            flags[h] = any(m)
            hits[h] = {u + d for u, x in enumerate(m) if x for d in range(lo, hi + 1)}
        out["methods"].append({"method": "psiminer_trainsel", "lags": None, "rule": r["antecedent"],
                               "host": host_metrics(flags, labels), **tally(hits, eps, labels, beps)})

    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import GradientBoostingClassifier
    import wittgenstein as lw
    for L in [int(x) for x in a.lags.split(",")]:
        names = lag_names(L)
        Xtr, ytr = bin_train(train, L, a.max_neg_bins, a.seed)
        Xte = {h: bin_matrix(rows, L) for h, rows in test.items()}
        preds = {}
        clf = DecisionTreeClassifier(max_depth=3, random_state=0).fit(Xtr, ytr)
        preds["tree_d3"] = lambda X, c=clf: c.predict(X) == 1
        df = pd.DataFrame(Xtr.astype(str), columns=names)
        df["y"] = ytr
        rip = lw.RIPPER(random_state=a.seed)
        rip.fit(df, class_feat="y", pos_class=1)
        preds["ripper"] = ripper_predictor(rip.ruleset_, names)
        gbm = GradientBoostingClassifier(random_state=a.seed).fit(Xtr, ytr)
        preds["gbm"] = lambda X, g=gbm: g.predict(X) == 1
        xj = os.path.join(a.mine_dir, "results", "xai_L%d.json" % L)
        if os.path.exists(xj):
            anc = [m for m in json.load(open(xj))["methods"] if m["method"] == "anchors" and "explanation" in m]
            if anc:
                idx = {n: i for i, n in enumerate(names)}
                conds = [(idx[l.strip().lstrip("!")], 0 if l.strip().startswith("!") else 1)
                         for l in anc[0]["explanation"].split("&&")]

                def pa(X, conds=conds):
                    m = np.ones(len(X), dtype=bool)
                    for j, v in conds:
                        m &= X[:, j] == v
                    return m
                preds["anchors_modal"] = pa
        for name, pr in preds.items():
            flags, hits = {}, {}
            for h, X in Xte.items():
                p = pr(X)
                flags[h] = bool(p.any())
                hits[h] = set(np.where(p)[0].tolist())
            out["methods"].append({"method": name, "lags": L, "host": host_metrics(flags, labels),
                                   **tally(hits, eps, labels, beps)})

    os.makedirs(os.path.join(a.mine_dir, "results"), exist_ok=True)
    json.dump(out, open(os.path.join(a.mine_dir, "results", "event_recall.json"), "w"), indent=1)
    print("test hosts %d, anomalous %d" % (len(test), len(eps)))
    for m in out["methods"]:
        bd = " ".join("g%s:%d/%d" % (g, v["matched"], v["total"]) for g, v in m["by_delay"].items())
        print("%-18s L%-4s hostF1 %.3f hostR %.3f eventR %.3f benignB %d/%d  %s" % (
            m["method"], m["lags"], m["host"]["f1"], m["host"]["recall"], m["event_recall"],
            m["benign_b_matched"], m["benign_b_total"], bd))


if __name__ == "__main__":
    main()
