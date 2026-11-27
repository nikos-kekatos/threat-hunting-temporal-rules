#!/usr/bin/env python3
"""Anchors with selection on training/validation hosts and a frozen query on a separate test set
(review 2026-10-21, item 1).

The held-out hosts of MINE_DIR are split once more, by a hash of the host name, into a validation half
and a test half. Nothing below looks at the labels of the test half until the queries are frozen.
  1. The bin-view gradient-boosting model is trained on the training hosts exactly as in compare_xai.py.
  2. Anchors (precision threshold 0.95) explains the first positive second of up to N anomalous
     TRAINING hosts. The distinct anchors are the candidate queries.
  3. Two selections, both frozen before the test half is scored:
       modal   : the anchor that occurs most often (training hosts only);
       valsel  : the candidate with the highest host F1 on the validation half.
  4. The frozen queries, the boosting model itself, the conjunction of the SHAP top-3 features
     (positive literals; a diagnostic of what a feature ranking says as a query) and, when present,
     the PSI-Miner rule selected on training hosts are scored on the test half only.
Output: results/anchor_frozen_L<L>.json under MINE_DIR.

usage: anchor_frozen.py MINE_DIR [--lags 3] [--anchors 20] [--seed 1] [--planted SYN_DOM,DPORT_MANY,1-8]
"""
import argparse
import collections
import csv
import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_xai import (bin_matrix, bin_train, flag_all_f1, lag_names, planted_ok, train_f1,  # noqa: E402
                         psiminer_planted, MARGIN)
from evaluate import completions, host_metrics, load_traces, parse_antecedent  # noqa: E402


def half(name):
    return int(hashlib.sha1(("val:" + name).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < 0.5


def conj_predictor(conds):
    def pr(X):
        m = np.ones(len(X), dtype=bool)
        for j, v in conds:
            m &= X[:, j] == v
        return m
    return pr


def flags(traces, lags, pr, cache):
    if id(traces) not in cache:
        cache[id(traces)] = {h: bin_matrix(r, lags) for h, r in traces.items()}
    return {h: bool(pr(X).any()) for h, X in cache[id(traces)].items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mine_dir")
    ap.add_argument("--lags", type=int, default=3)
    ap.add_argument("--anchors", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-neg-bins", type=int, default=50000)
    ap.add_argument("--planted", default="")
    a = ap.parse_args()
    planted = None
    if a.planted:
        x, y, g = a.planted.split(",")
        lo, _, hi = g.partition("-")
        planted = (x, y, int(lo), int(hi or lo))

    split = list(csv.DictReader(open(os.path.join(a.mine_dir, "split.csv"))))
    labels = {s["trace"]: s["class"] == "anomalous" for s in split}
    held = [s["trace"] for s in split if s["split"] == "test"]
    val_names = [h for h in held if half(h)]
    test_names = [h for h in held if not half(h)]
    tdir = os.path.join(a.mine_dir, "mining", "test")
    val, test = load_traces(tdir, val_names), load_traces(tdir, test_names)
    train = load_traces(os.path.join(a.mine_dir, "mining", "ordered"),
                        [s["trace"] for s in split if s["split"] == "train"])
    names = lag_names(a.lags)
    idx = {n: i for i, n in enumerate(names)}
    cache = {}

    from sklearn.ensemble import GradientBoostingClassifier
    import shap
    from anchor import anchor_tabular
    Xtr, ytr = bin_train(train, a.lags, a.max_neg_bins, a.seed)
    gbm = GradientBoostingClassifier(random_state=a.seed).fit(Xtr, ytr)

    # candidates from anomalous training hosts (as compare_xai.anchors_row)
    np.random.seed(a.seed)
    ex = anchor_tabular.AnchorTabularExplainer(["0", "1"], names, Xtr, {i: ["0", "1"] for i in range(len(names))})
    predict = lambda X: gbm.predict(np.asarray(X, dtype=float))
    cand = []
    for h in sorted(train):
        if not labels[h]:
            continue
        X = bin_matrix(train[h], a.lags)
        hit = np.where(gbm.predict(X) == 1)[0]
        if len(hit):
            cand.append(X[hit[0]])
        if len(cand) >= a.anchors:
            break
    counts = collections.Counter()
    for x in cand:
        e = ex.explain_instance(x, predict, threshold=0.95)
        lits = []
        for n in e.names():
            f, _, v = n.partition(" = ")
            lits.append((f.strip(), v.strip() == "1"))
        counts[tuple(sorted(lits))] += 1

    def text(anc):
        return " && ".join(("" if s else "!") + f for f, s in anc)

    cands = []
    for anc, c in counts.most_common():
        pr = conj_predictor([(idx[f], int(s)) for f, s in anc])
        cands.append({"anchor": text(anc), "count": c, "lits": anc, "pr": pr,
                      "val": host_metrics(flags(val, a.lags, pr, cache), labels)})
    modal = cands[0] if cands else None
    valsel = max(cands, key=lambda c: (c["val"]["f1"], c["count"])) if cands else None

    rows = []

    def add(name, pr, explanation, size, groups=None, val_m=None):
        hm = host_metrics(flags(test, a.lags, pr, cache), labels)
        r = {"method": name, "query": explanation, "size": size, "test": hm, "validation": val_m}
        if planted is not None:
            r["planted_recovered"] = bool(groups is not None and planted_ok(groups, planted)
                                          and hm["f1"] > flag_all_f1(hm) + MARGIN)
        rows.append(r)

    if modal:
        add("anchors_modal (train only)", modal["pr"], modal["anchor"], len(modal["lits"]),
            [list(modal["lits"])], modal["val"])
        add("anchors_valsel (validation F1)", valsel["pr"], valsel["anchor"], len(valsel["lits"]),
            [list(valsel["lits"])], valsel["val"])
    add("gbm (model)", lambda X: gbm.predict(X) == 1, "gradient boosting, %d features" % len(names), None,
        None, host_metrics(flags(val, a.lags, lambda X: gbm.predict(X) == 1, cache), labels))
    rng = np.random.default_rng(a.seed)
    Xs = Xtr[rng.choice(len(Xtr), min(2000, len(Xtr)), replace=False)]
    imp = np.abs(shap.TreeExplainer(gbm).shap_values(Xs)).mean(axis=0)
    top = [names[i] for i in np.argsort(-imp)[:3]]
    add("shap_top3_conjunction", conj_predictor([(idx[f], 1) for f in top]), " && ".join(top), 3,
        [[(f, True) for f in top]])

    # PSI-Miner rule selected on training hosts, scored on the same test half
    hp = os.path.join(a.mine_dir, "results", "hunt_eval.json")
    meta = json.load(open(os.path.join(a.mine_dir, "rules.json")))
    if os.path.exists(hp) and not meta["rules"].get("ordered_crashed"):
        rules = [r for r in json.load(open(hp))["rules"]["ordered"] if r["consequent"].strip() == "ANOM"]
        if rules:
            r = max(rules, key=lambda r: train_f1(r, train, labels))
            conjs, gaps = parse_antecedent(r["antecedent"])
            fl = {h: any(completions(conjs, gaps, rows)) for h, rows in test.items()}
            hm = host_metrics(fl, labels)
            rows.append({"method": "psiminer_trainsel", "query": r["antecedent"], "size": r["length"],
                         "test": hm, "validation": None,
                         "planted_recovered": (bool(psiminer_planted(r["antecedent"], planted)
                                                    and hm["f1"] > flag_all_f1(hm) + MARGIN)
                                               if planted else None)})

    out = {"params": vars(a), "n_validation": len(val), "n_test": len(test),
           "base_rate_test": round(sum(labels[h] for h in test) / len(test), 4),
           "candidates": [{"anchor": c["anchor"], "count": c["count"], "validation_f1": c["val"]["f1"]}
                          for c in cands],
           "methods": rows}
    json.dump(out, open(os.path.join(a.mine_dir, "results", "anchor_frozen_L%d.json" % a.lags), "w"), indent=1)
    print("validation %d, test %d hosts, test base rate %.3f, %d anchor candidates from %d training seconds" % (
        len(val), len(test), out["base_rate_test"], len(cands), len(cand)))
    for r in rows:
        print("%-32s valF1 %-6s testP %.3f R %.3f F1 %.3f planted %-5s %s" % (
            r["method"], "%.3f" % r["validation"]["f1"] if r["validation"] else "-", r["test"]["precision"],
            r["test"]["recall"], r["test"]["f1"], r.get("planted_recovered"), r["query"][:70]))


if __name__ == "__main__":
    main()
