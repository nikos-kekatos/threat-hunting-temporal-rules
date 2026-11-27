#!/usr/bin/env python3
"""Anchors with query selection inside the TRAINING partition (corrections guide 2026-10-22, item 4.1).

anchor_frozen.py (review 2026-10-21) selects on a validation half of the held-out hosts. This variant
keeps every selection inside the training partition, so no held-out host is used before scoring:
  1. The training hosts of MINE_DIR are split by a hash of the host name into a fitting half and a
     selection half.
  2. The bin-view gradient-boosting model is trained on the fitting half only (same settings as
     compare_xai.py).
  3. Anchors (precision threshold 0.95) explains the first positive second of up to N anomalous
     FITTING hosts. The distinct anchors are the candidate queries.
  4. Two selections, frozen before any held-out host is read:
       modal  : the anchor that occurs most often (fitting half only);
       selsel : the candidate with the highest host F1 on the selection half.
  5. The frozen queries and the boosting model are scored once on all held-out hosts (the same test
     partition as the main tables), and also on the test half used by anchor_frozen.py.
  PSI-Miner: its rules are mined on all training hosts (not re-mined). The rule with the highest host
  F1 on the selection half is reported as a sensitivity row; mining and selection hosts overlap for it.
Output: results/anchor_trainsel_L<L>.json under MINE_DIR.

usage: anchor_trainsel.py MINE_DIR [--lags 3] [--anchors 20] [--seed 1] [--planted SYN_DOM,DPORT_MANY,1-8]
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
from compare_xai import bin_matrix, bin_train, flag_all_f1, lag_names, planted_ok, train_f1, psiminer_planted, MARGIN  # noqa: E402
from evaluate import completions, host_metrics, load_traces, parse_antecedent  # noqa: E402
from anchor_frozen import conj_predictor, flags, half  # noqa: E402


def sel_half(name):
    return int(hashlib.sha1(("sel:" + name).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < 0.5


def counts(names, labels):
    return {"hosts": len(names), "anomalous": sum(1 for h in names if labels[h])}


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
    train_names = [s["trace"] for s in split if s["split"] == "train"]
    fit_names = [h for h in train_names if not sel_half(h)]
    sel_names = [h for h in train_names if sel_half(h)]
    held = [s["trace"] for s in split if s["split"] == "test"]
    test_half_names = [h for h in held if not half(h)]
    odir = os.path.join(a.mine_dir, "mining", "ordered")
    fit, sel = load_traces(odir, fit_names), load_traces(odir, sel_names)
    test = load_traces(os.path.join(a.mine_dir, "mining", "test"), held)
    test_half = {h: test[h] for h in test_half_names}
    names = lag_names(a.lags)
    idx = {n: i for i, n in enumerate(names)}
    cache = {}

    from sklearn.ensemble import GradientBoostingClassifier
    from anchor import anchor_tabular
    Xf, yf = bin_train(fit, a.lags, a.max_neg_bins, a.seed)
    gbm = GradientBoostingClassifier(random_state=a.seed).fit(Xf, yf)

    np.random.seed(a.seed)
    ex = anchor_tabular.AnchorTabularExplainer(["0", "1"], names, Xf, {i: ["0", "1"] for i in range(len(names))})
    predict = lambda X: gbm.predict(np.asarray(X, dtype=float))
    cand = []
    for h in sorted(fit):
        if not labels[h]:
            continue
        X = bin_matrix(fit[h], a.lags)
        hit = np.where(gbm.predict(X) == 1)[0]
        if len(hit):
            cand.append(X[hit[0]])
        if len(cand) >= a.anchors:
            break
    cnt = collections.Counter()
    for x in cand:
        e = ex.explain_instance(x, predict, threshold=0.95)
        lits = []
        for n in e.names():
            f, _, v = n.partition(" = ")
            lits.append((f.strip(), v.strip() == "1"))
        cnt[tuple(sorted(lits))] += 1

    text = lambda anc: " && ".join(("" if s else "!") + f for f, s in anc)
    cands = []
    for anc, c in cnt.most_common():
        pr = conj_predictor([(idx[f], int(s)) for f, s in anc])
        cands.append({"anchor": text(anc), "count": c, "lits": anc, "pr": pr,
                      "sel": host_metrics(flags(sel, a.lags, pr, cache), labels)})
    modal = cands[0] if cands else None
    selsel = max(cands, key=lambda c: (c["sel"]["f1"], c["count"])) if cands else None

    rows = []

    def add(name, pr, explanation, size, groups=None, sel_m=None):
        f_all = flags(test, a.lags, pr, cache)
        hm = host_metrics(f_all, labels)
        hh = host_metrics({h: f_all[h] for h in test_half}, labels)
        r = {"method": name, "query": explanation, "size": size, "test_all": hm, "test_half": hh,
             "selection": sel_m}
        if planted is not None:
            r["planted_recovered"] = bool(groups is not None and planted_ok(groups, planted)
                                          and hm["f1"] > flag_all_f1(hm) + MARGIN)
        rows.append(r)

    if modal:
        add("anchors_modal (fit half only)", modal["pr"], modal["anchor"], len(modal["lits"]),
            [list(modal["lits"])], modal["sel"])
        add("anchors_selsel (selection-half F1)", selsel["pr"], selsel["anchor"], len(selsel["lits"]),
            [list(selsel["lits"])], selsel["sel"])
    add("gbm fit half (model)", lambda X: gbm.predict(X) == 1, "gradient boosting, %d features" % len(names),
        None, None, host_metrics(flags(sel, a.lags, lambda X: gbm.predict(X) == 1, cache), labels))

    hp = os.path.join(a.mine_dir, "results", "hunt_eval.json")
    meta = json.load(open(os.path.join(a.mine_dir, "rules.json")))
    if os.path.exists(hp) and not meta["rules"].get("ordered_crashed"):
        rules = [r for r in json.load(open(hp))["rules"]["ordered"] if r["consequent"].strip() == "ANOM"]
        if rules:
            r = max(rules, key=lambda r: train_f1(r, sel, labels))
            conjs, gaps = parse_antecedent(r["antecedent"])
            fl = {h: any(completions(conjs, gaps, rw)) for h, rw in test.items()}
            hm = host_metrics(fl, labels)
            rows.append({"method": "psiminer_selsel (mined on all training hosts)", "query": r["antecedent"],
                         "size": r["length"], "test_all": hm,
                         "test_half": host_metrics({h: fl[h] for h in test_half}, labels), "selection": None,
                         "planted_recovered": (bool(psiminer_planted(r["antecedent"], planted)
                                                    and hm["f1"] > flag_all_f1(hm) + MARGIN)
                                               if planted else None)})

    out = {"params": vars(a),
           "counts": {"fit": counts(fit_names, labels), "selection": counts(sel_names, labels),
                      "test_all": counts(held, labels), "test_half": counts(test_half_names, labels)},
           "n_anchor_seconds": len(cand),
           "candidates": [{"anchor": c["anchor"], "count": c["count"], "selection_f1": c["sel"]["f1"]}
                          for c in cands],
           "methods": rows}
    json.dump(out, open(os.path.join(a.mine_dir, "results", "anchor_trainsel_L%d.json" % a.lags), "w"), indent=1)
    print("counts %s; %d candidates" % (json.dumps(out["counts"]), len(cands)))
    for r in rows:
        print("%-46s selF1 %-6s allF1 %.3f halfF1 %.3f planted %-5s %s" % (
            r["method"], "%.3f" % r["selection"]["f1"] if r["selection"] else "-", r["test_all"]["f1"],
            r["test_half"]["f1"], r.get("planted_recovered"), r["query"][:70]))


if __name__ == "__main__":
    main()
