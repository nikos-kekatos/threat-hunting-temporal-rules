"""MAWI host-view reanalysis for the 2026-10-27 external review (option B; exploratory, after the freeze).

For each split results_dc/mine_s{0..4}:
  1. host view as in compare_xai.host_view (tree d3, RIPPER, GBM; same seeds), retrained, with per-host flags kept;
     the F1 values are checked against results_dc/mine_s*/results/xai_L3.json;
  2. a predicate host view: active seconds and, for each Table I predicate except ACTIVE/ANOM/HANOM, the fraction
     of active seconds in which it holds (the information of the thresholded predicates without order or lags);
  3. paired bootstrap (2,000 resamples of held-out hosts, seed 20261027) of F1(GBM host) - F1(other) on the same
     resampled hosts;
  4. false-positive rate and expected precision / hosts inspected per anomalous host found at prevalence 1% and 5%,
     from the confusion counts of every method in xai_L3.json:
     P(pi) = R pi / (R pi + FPR (1 - pi)).
Traces are read one host at a time to keep memory low.
Output: results_stats_2026-10-27/host_reanalysis.json and HOST_REANALYSIS.md
usage: code/.venv/bin/python code/host_reanalysis_1027.py
"""
import csv
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evaluate import host_features, feature_names  # noqa: E402
from mine import PREDICATES  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(ROOT, "results_stats_2026-10-27")
PREDS = [(n, f) for n, _, f in PREDICATES if n not in ("ACTIVE", "ANOM", "HANOM")]
SEED = 1
B = 2000
PIS = (0.01, 0.05)


def read_host(path):
    with open(path) as fh:
        return [{k: int(v) for k, v in r.items()} for r in csv.DictReader(fh)]


def pred_features(rows):
    act = [r for r in rows if r["pkts"] > 0] or rows
    return [len(act)] + [sum(bool(f(r)) for r in act) / len(act) for _, f in PREDS]


def views(d, names):
    A, P = [], []
    for n in names:
        rows = read_host(os.path.join(d, n + ".csv"))
        A.append(host_features(rows))
        P.append(pred_features(rows))
    return np.array(A, float), np.array(P, float)


def f1(y, p):
    tp = np.sum(y & p); fp = np.sum(~y & p); fn = np.sum(y & ~p)
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def fit_all(Xtr, ytr, Xte, cols):
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.ensemble import GradientBoostingClassifier
    import wittgenstein as lw
    out = {}
    clf = DecisionTreeClassifier(max_depth=3, random_state=0).fit(Xtr, ytr)
    out["tree_d3"] = (clf.predict(Xte).astype(bool), "%d leaves" % clf.get_n_leaves())
    rip = lw.RIPPER(random_state=SEED)
    rip.fit(pd.DataFrame(Xtr, columns=cols).assign(y=ytr), class_feat="y", pos_class=1)
    nc = sum(len(r.conds) for r in rip.ruleset_.rules)
    out["ripper"] = (np.array(rip.predict(pd.DataFrame(Xte, columns=cols)), bool),
                     "%d rules, %d conds" % (len(rip.ruleset_.rules), nc))
    gbm = GradientBoostingClassifier(random_state=SEED).fit(Xtr, ytr)
    out["gbm"] = (gbm.predict(Xte).astype(bool), "%d features" % Xtr.shape[1])
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(20261027)
    res = {"splits": {}, "params": {"seed": SEED, "bootstrap": B, "bootstrap_seed": 20261027,
                                     "pred_features": ["active_s"] + ["frac_" + n for n, _ in PREDS]}}
    for k in range(5):
        md = os.path.join(ROOT, "results_dc", f"mine_s{k}")
        split = list(csv.DictReader(open(os.path.join(md, "split.csv"))))
        lab = {s["trace"]: s["class"] == "anomalous" for s in split}
        tr = [s["trace"] for s in split if s["split"] == "train"]
        te = [s["trace"] for s in split if s["split"] == "test"]
        Atr, Ptr = views(os.path.join(md, "mining", "ordered"), tr)
        Ate, Pte = views(os.path.join(md, "mining", "test"), te)
        ytr = np.array([lab[h] for h in tr], int)
        yte = np.array([lab[h] for h in te], bool)
        agg = fit_all(Atr, ytr, Ate, feature_names())
        prd = fit_all(Ptr, ytr, Pte, res["params"]["pred_features"])
        ref = {(m["method"], m.get("view")): m for m in json.load(open(os.path.join(md, "results", "xai_L3.json")))["methods"]}
        S = {"n_test": len(te), "anomalous": int(yte.sum()), "aggregate": {}, "predicate": {}}
        for name, (p, size) in agg.items():
            key = {"gbm": "gbm+shap"}.get(name, name)
            S["aggregate"][name] = {"f1": round(f1(yte, p), 4), "size": size,
                                    "f1_xai_L3": ref[(key, "host")]["host"]["f1"]}
        for name, (p, size) in prd.items():
            S["predicate"][name] = {"f1": round(f1(yte, p), 4), "size": size}
        # paired bootstrap of F1(GBM aggregate) - F1(other)
        g = agg["gbm"][0]
        others = {f"aggregate {n}": agg[n][0] for n in ("tree_d3", "ripper")}
        others.update({f"predicate {n}": prd[n][0] for n in prd})
        idx = rng.integers(0, len(te), size=(B, len(te)), dtype=np.int32)
        S["paired"] = {}
        for n, p in others.items():
            d = np.array([f1(yte[i], g[i]) - f1(yte[i], p[i]) for i in idx])
            S["paired"][n] = {"diff": round(f1(yte, g) - f1(yte, p), 4),
                              "ci95": [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]}
        # FPR and workload from the stored confusion counts
        S["workload"] = {}
        for (m, v), r in ref.items():
            if "host" not in r:
                continue
            h = r["host"]
            fpr = h["fp"] / (h["fp"] + h["tn"]); rec = h["recall"]
            w = {"fpr": round(fpr, 4), "recall": rec, "precision_sampled": h["precision"]}
            for pi in PIS:
                prec = rec * pi / (rec * pi + fpr * (1 - pi)) if rec > 0 else 0.0
                w[f"precision_at_{pi}"] = round(prec, 4)
                w[f"hosts_per_hit_at_{pi}"] = round(1 / prec, 1) if prec > 0 else None
            S["workload"][f"{m}|{v}"] = w
        res["splits"][f"s{k}"] = S
        print(k, json.dumps({a: S[a] for a in ("aggregate", "predicate", "paired")}), flush=True)
    # means over splits
    mean = lambda xs: (round(float(np.mean(xs)), 4), round(float(np.std(xs, ddof=1)), 4))
    sp = list(res["splits"].values())
    res["mean"] = {
        "aggregate": {n: mean([s["aggregate"][n]["f1"] for s in sp]) for n in sp[0]["aggregate"]},
        "predicate": {n: mean([s["predicate"][n]["f1"] for s in sp]) for n in sp[0]["predicate"]},
        "workload": {m: {c: mean([s["workload"][m][c] for s in sp]) for c in sp[0]["workload"][m]
                         if all(s["workload"][m][c] is not None for s in sp)} for m in sp[0]["workload"]},
        "paired_all_splits_ci_above_0": {n: sum(s["paired"][n]["ci95"][0] > 0 for s in sp) for n in sp[0]["paired"]},
    }
    json.dump(res, open(os.path.join(OUT, "host_reanalysis.json"), "w"), indent=1)
    L = ["# MAWI host-view reanalysis (code/host_reanalysis_1027.py)", "",
         "| split | view | tree F1 | RIPPER F1 | GBM F1 |", "|---|---|---|---|---|"]
    for k, s in res["splits"].items():
        for v in ("aggregate", "predicate"):
            L.append(f"| {k} | {v} | {s[v]['tree_d3']['f1']} | {s[v]['ripper']['f1']} | {s[v]['gbm']['f1']} |")
    L += ["", "Check against xai_L3.json (aggregate view): " + "; ".join(
        f"{k} " + ", ".join(f"{n} {x['f1']} vs {x['f1_xai_L3']}" for n, x in s["aggregate"].items())
        for k, s in res["splits"].items()), "",
          "Means over splits (mean, s.d.): " + json.dumps({a: res["mean"][a] for a in ("aggregate", "predicate")}), "",
          "## Paired bootstrap F1(GBM aggregate) - F1(other), 95% interval", ""]
    for k, s in res["splits"].items():
        L.append(f"- {k}: " + "; ".join(f"{n} {x['diff']} {x['ci95']}" for n, x in s["paired"].items()))
    L += ["", "Splits with lower bound > 0: " + json.dumps(res["mean"]["paired_all_splits_ci_above_0"]), "",
          "## FPR and workload (mean, s.d. over splits)", ""]
    for m, w in res["mean"]["workload"].items():
        L.append(f"- {m}: " + json.dumps(w))
    open(os.path.join(OUT, "HOST_REANALYSIS.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
