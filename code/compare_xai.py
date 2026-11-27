#!/usr/bin/env python3
"""Compare PSIMiner's temporal rules with other explanation methods, all scored as hunt queries.

Input: the output directory of mine.py (split.csv, mining/{ordered,test}/), after evaluate.py has
written results/hunt_eval.json (the PSIMiner row is read from it).
Two views of the same train/test hosts:
  * host view: per-host aggregates (evaluate.host_features), label = host class;
  * bin view: one row per second, the non-target predicates at lags 0..L (P_lagk = P held k s
    earlier), label = ANOM in that second; a host is flagged when any of its seconds is predicted
    positive, as for a mined rule.
Methods: decision tree (depth 3) and RIPPER on both views, gradient boosting + SHAP on both views,
Anchors on the bin-view boosting model. Every method gets host P/R/F1 on the held-out hosts, the
same score on row-permuted test traces (order destroyed, rows kept), and an explanation size.
With --planted A,B,GAP (synthetic control) each explanation is checked for the planted order:
A at lag GAP+k and B at lag k, both non-negated (GAP may be a range lo-hi).

usage: compare_xai.py MINE_DIR [--lags 3] [--seed 1] [--max-neg-bins 50000]
                               [--planted SYN_DOM,DPORT_MANY,2] [--shap-k 3] [--anchors 20]
                               [--out xai_compare.json]
"""
import argparse
import collections
import csv
import json
import os
import random
import re
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mine import PREDICATES, TARGETS  # noqa: E402
from evaluate import host_features, feature_names, host_metrics, load_traces, permuted  # noqa: E402

warnings.filterwarnings("ignore")
FEAT_PREDS = [p for p in PREDICATES if p[0] not in TARGETS]
LAG_RE = re.compile(r"^(\w+)_lag(\d+)$")


def bin_matrix(rows, lags):
    """Predicate truth values at lags 0..lags for every second; columns follow lag_names()."""
    base = np.array([[p[2](r) for p in FEAT_PREDS] for r in rows], dtype=np.int8)
    n = len(rows)
    cols = []
    for k in range(lags + 1):
        sh = np.zeros_like(base)
        if k < n:
            sh[k:] = base[:n - k]
        cols.append(sh)
    return np.hstack(cols)


def lag_names(lags):
    return ["%s_lag%d" % (p[0], k) for k in range(lags + 1) for p in FEAT_PREDS]


def bin_labels(rows):
    return np.array([1 if r["anom"] >= 1 else 0 for r in rows], dtype=np.int8)


_BIN_CACHE = {}


def flags_from_bins(traces, lags, predict):
    # lagged matrices are built once per trace set and lag budget, then reused by every method
    key = (id(traces), lags)
    if key not in _BIN_CACHE:
        _BIN_CACHE[key] = {h: bin_matrix(rows, lags) for h, rows in traces.items()}
    return {h: bool(predict(X).any()) for h, X in _BIN_CACHE[key].items()}


def planted_ok(groups, planted):
    """groups: list of literal groups, one per rule, leaf path, anchor or SHAP ranking; each a list of
    (feature, positive). True if ONE group has A_lag(k+g) and B_lagk, both positive, lo <= g <= hi."""
    if not planted:
        return None
    return any(_planted_one(g, planted) for g in groups)


def _planted_one(literals, planted):
    a, b, lo, hi = planted
    pos = {f for f, s in literals if s}
    for f in pos:
        m = LAG_RE.match(f)
        if m and m.group(1) == b and any("%s_lag%d" % (a, int(m.group(2)) + g) in pos
                                          for g in range(lo, hi + 1)):
            return True
    return False


def flag_all_f1(hm):
    """F1 of flagging every held-out host, from a host_metrics dict (base rate of the held-out hosts)."""
    n = hm["tp"] + hm["fp"] + hm["fn"] + hm["tn"]
    base = (hm["tp"] + hm["fn"]) / n
    return 2 * base / (1 + base)


MARGIN = 0.05   # a recovery counts only if the query beats flagging every host by this F1 margin


def row(name, view, flags, pflags, labels, size, explanation, groups=None, planted=None):
    out = {"method": name, "view": view, "host": host_metrics(flags, labels),
           "host_permuted": host_metrics(pflags, labels), "size": size, "explanation": explanation}
    if not planted:
        out["planted_recovered"] = None
    elif view != "bin":
        out["planted_recovered"] = False
    else:
        out["planted_recovered"] = bool(planted_ok(groups or [], planted)
                                        and out["host"]["f1"] > flag_all_f1(out["host"]) + MARGIN)
    return out


# ---------- host view ----------

def host_view(train, test, test_perm, labels, a, planted):
    from sklearn.tree import DecisionTreeClassifier, export_text
    from sklearn.ensemble import GradientBoostingClassifier
    import shap
    import wittgenstein as lw

    fn = feature_names()
    Xtr = np.array([host_features(r) for r in train.values()], dtype=float)
    ytr = np.array([int(labels[h]) for h in train])
    Xte = np.array([host_features(r) for r in test.values()], dtype=float)
    Xpe = np.array([host_features(test_perm[h]) for h in test], dtype=float)
    hosts = list(test)
    out = []

    clf = DecisionTreeClassifier(max_depth=3, random_state=0).fit(Xtr, ytr)
    f = lambda X: dict(zip(hosts, map(bool, clf.predict(X))))
    out.append(row("tree_d3", "host", f(Xte), f(Xpe), labels, "%d leaves" % clf.get_n_leaves(),
                   export_text(clf, feature_names=fn), planted=planted))

    rip = lw.RIPPER(random_state=a.seed)
    rip.fit(pd.DataFrame(Xtr, columns=fn).assign(y=ytr), class_feat="y", pos_class=1)
    f = lambda X: dict(zip(hosts, map(bool, rip.predict(pd.DataFrame(X, columns=fn)))))
    nconds = sum(len(r.conds) for r in rip.ruleset_.rules)
    out.append(row("ripper", "host", f(Xte), f(Xpe), labels,
                   "%d rules, %d conds" % (len(rip.ruleset_.rules), nconds), str(rip.ruleset_),
                   planted=planted))

    gbm = GradientBoostingClassifier(random_state=a.seed).fit(Xtr, ytr)
    f = lambda X: dict(zip(hosts, map(bool, gbm.predict(X))))
    sv = shap.TreeExplainer(gbm).shap_values(Xtr)     # attributions on training hosts, as in the bin view
    imp = np.abs(sv).mean(axis=0)
    top = [fn[i] for i in np.argsort(-imp)[:a.shap_k]]
    out.append(row("gbm+shap", "host", f(Xte), f(Xpe), labels,
                   "top-%d of %d features" % (a.shap_k, len(fn)), ", ".join(top), planted=planted))
    return out


# ---------- bin view ----------

def bin_train(train, lags, max_neg, seed):
    X = np.vstack([bin_matrix(r, lags) for r in train.values()])
    y = np.concatenate([bin_labels(r) for r in train.values()])
    neg = np.where(y == 0)[0]
    if len(neg) > max_neg:
        keep = np.sort(np.concatenate([np.where(y == 1)[0],
                                       np.random.default_rng(seed).choice(neg, max_neg, replace=False)]))
        X, y = X[keep], y[keep]
    return X, y


def tree_literals(clf, names):
    """One literal group per root-to-leaf path of a leaf predicting ANOM."""
    t = clf.tree_
    lits = []

    def walk(n, path):
        if t.children_left[n] == -1:
            if np.argmax(t.value[n][0]) == 1:
                lits.append(path)
            return
        f = names[t.feature[n]]
        walk(t.children_left[n], path + [(f, False)])   # x <= 0.5: predicate false
        walk(t.children_right[n], path + [(f, True)])

    walk(0, [])
    return lits


def ripper_literals(rs):
    """One literal group per rule."""
    return [[(c.feature, str(c.val) in ("1", "True")) for c in r.conds] for r in rs.rules]


def ripper_predictor(rs, names):
    idx = {n: i for i, n in enumerate(names)}
    rules = [[(idx[c.feature], int(str(c.val) in ("1", "True"))) for c in r.conds] for r in rs.rules]

    def predict(X):
        out = np.zeros(len(X), dtype=bool)
        for conds in rules:
            m = np.ones(len(X), dtype=bool)
            for j, v in conds:
                m &= X[:, j] == v
            out |= m
        return out
    return predict


def bin_view(train, test, test_perm, labels, a, planted):
    from sklearn.tree import DecisionTreeClassifier, export_text
    from sklearn.ensemble import GradientBoostingClassifier
    import shap
    import wittgenstein as lw

    names = lag_names(a.lags)
    Xtr, ytr = bin_train(train, a.lags, a.max_neg_bins, a.seed)
    out = []
    if ytr.sum() == 0:
        return [{"method": "bin view", "skipped": "no ANOM seconds in train"}]

    clf = DecisionTreeClassifier(max_depth=3, random_state=0).fit(Xtr, ytr)
    pr = lambda X: clf.predict(X) == 1
    out.append(row("tree_d3", "bin", flags_from_bins(test, a.lags, pr), flags_from_bins(test_perm, a.lags, pr),
                   labels, "%d leaves" % clf.get_n_leaves(), export_text(clf, feature_names=names),
                   tree_literals(clf, names), planted))

    df = pd.DataFrame(Xtr.astype(str), columns=names)
    df["y"] = ytr
    rip = lw.RIPPER(random_state=a.seed)
    rip.fit(df, class_feat="y", pos_class=1)
    pr = ripper_predictor(rip.ruleset_, names)
    nconds = sum(len(r.conds) for r in rip.ruleset_.rules)
    out.append(row("ripper", "bin", flags_from_bins(test, a.lags, pr), flags_from_bins(test_perm, a.lags, pr),
                   labels, "%d rules, %d conds" % (len(rip.ruleset_.rules), nconds), str(rip.ruleset_),
                   ripper_literals(rip.ruleset_), planted))

    gbm = GradientBoostingClassifier(random_state=a.seed).fit(Xtr, ytr)
    pr = lambda X: gbm.predict(X) == 1
    rng = np.random.default_rng(a.seed)
    Xs = Xtr[rng.choice(len(Xtr), min(2000, len(Xtr)), replace=False)]
    imp = np.abs(shap.TreeExplainer(gbm).shap_values(Xs)).mean(axis=0)
    top = [names[i] for i in np.argsort(-imp)[:a.shap_k]]
    out.append(row("gbm+shap", "bin", flags_from_bins(test, a.lags, pr), flags_from_bins(test_perm, a.lags, pr),
                   labels, "top-%d of %d features" % (a.shap_k, len(names)), ", ".join(top),
                   [[(f, True) for f in top]], planted))

    if a.anchors:
        out.append(anchors_row(gbm, Xtr, names, train, test, test_perm, labels, a, planted))
    return out


def anchors_row(gbm, Xtr, names, train, test, test_perm, labels, a, planted):
    """Anchors for the first positive-predicted second of up to N anomalous TRAINING hosts; the modal
    anchor becomes the hunt query and is scored on the held-out hosts."""
    from anchor import anchor_tabular
    np.random.seed(a.seed)
    ex = anchor_tabular.AnchorTabularExplainer(["0", "1"], names, Xtr,
                                               {i: ["0", "1"] for i in range(len(names))})
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
    anchors = collections.Counter()
    for x in cand:
        e = ex.explain_instance(x, predict, threshold=0.95)
        lits = []
        for n in e.names():                       # e.g. 'SYN_DOM_lag2 = 1'
            f, _, v = n.partition(" = ")
            lits.append((f.strip(), v.strip() == "1"))
        anchors[tuple(sorted(lits))] += 1
    if not anchors:
        return {"method": "anchors", "view": "bin", "skipped": "no positive test seconds"}
    modal, count = anchors.most_common(1)[0]
    idx = {n: i for i, n in enumerate(names)}
    conds = [(idx[f], int(s)) for f, s in modal]

    def pr(X):
        m = np.ones(len(X), dtype=bool)
        for j, v in conds:
            m &= X[:, j] == v
        return m
    text = " && ".join(("" if s else "!") + f for f, s in modal)
    r = row("anchors", "bin", flags_from_bins(test, a.lags, pr), flags_from_bins(test_perm, a.lags, pr),
            labels, "%d literals (modal of %d anchors, %d distinct)" % (len(modal), len(cand), len(anchors)),
            text, [list(modal)], planted)
    r["modal_share"] = round(count / len(cand), 3)
    return r


# ---------- PSIMiner ----------

def train_f1(rule, train, labels):
    """Host-level F1 of a mined rule on the training hosts (selection without the test hosts)."""
    from evaluate import parse_antecedent, score_rule
    conjs, gaps = parse_antecedent(rule["antecedent"])
    flags, _, _ = score_rule(conjs, gaps, rule["lo"], rule["hi"], train, rule["consequent"].strip())
    return host_metrics(flags, labels)["f1"]


def psiminer_rows(mine_dir, planted, train=None, labels=None):
    path = os.path.join(mine_dir, "results", "hunt_eval.json")
    if not os.path.exists(path):
        return [{"method": "psiminer", "skipped": "run evaluate.py first"}]
    ev = json.load(open(path))
    meta = json.load(open(os.path.join(mine_dir, "rules.json")))
    if meta["rules"].get("ordered_crashed"):
        return [{"method": "psiminer", "view": "temporal",
                 "skipped": "PSIMiner crashed (exit %d)" % meta["rules"]["ordered_crashed"]}]
    rules = [r for r in ev["rules"]["ordered"] if r["consequent"].strip() == "ANOM"]
    out = []
    # two selections, neither uses the test hosts: PSIMiner's own CORRELATION score, and host F1 on the
    # training hosts (the data every other method is fitted on)
    best = max(rules, key=lambda r: r.get("correlation", 0.0), default=None)
    sel = [("psiminer_best", best)]
    if train is not None:
        sel.append(("psiminer_trainsel", max(rules, key=lambda r: train_f1(r, train, labels), default=None)))
    for label, r in sel:
        if r is None:
            out.append({"method": label, "view": "temporal", "skipped": "no ANOM rules mined"})
            continue
        out.append({"method": label, "view": "temporal", "host": r["host"],
                    "host_permuted": r["host_permuted"], "size": "%d literals" % r["length"],
                    "explanation": r["antecedent"] + " |=> ##[%g:%g] ANOM" % (r["lo"], r["hi"]),
                    "planted_recovered": (bool(psiminer_planted(r["antecedent"], planted)
                                               and r["host"]["f1"] > flag_all_f1(r["host"]) + MARGIN)
                                          if planted else None)})
    out.append({"method": "psiminer_playbook", "view": "temporal", "host": ev["playbook_ordered"],
                "size": "%d rules" % len(rules), "explanation": "union of all ANOM rules",
                "planted_recovered": (any(psiminer_planted(r["antecedent"], planted) for r in rules)
                                      if planted else None)})
    return out


def psiminer_planted(ante, planted):
    if not planted:
        return None
    a, b = planted[:2]
    steps = [s.strip() for s in re.split(r"##\[[^\]]*\]", ante)]
    pos = [{x.strip() for x in s.split("&&") if x.strip() and not x.strip().startswith("!")} for s in steps]
    ia = [i for i, s in enumerate(pos) if a in s]
    ib = [i for i, s in enumerate(pos) if b in s]
    return any(i < j for i in ia for j in ib)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mine_dir")
    ap.add_argument("--lags", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-neg-bins", type=int, default=50000)
    ap.add_argument("--planted", default="", help="A,B,GAP: planted rule A then B GAP seconds later")
    ap.add_argument("--shap-k", type=int, default=3)
    ap.add_argument("--anchors", type=int, default=20, help="test seconds to anchor (0 = skip Anchors)")
    ap.add_argument("--out", default="xai_compare.json", help="file name under MINE_DIR/results")
    a = ap.parse_args()
    planted = None
    if a.planted:
        x, y, g = a.planted.split(",")
        lo, _, hi = g.partition("-")
        planted = (x, y, int(lo), int(hi or lo))

    split = list(csv.DictReader(open(os.path.join(a.mine_dir, "split.csv"))))
    labels = {s["trace"]: s["class"] == "anomalous" for s in split}
    test = load_traces(os.path.join(a.mine_dir, "mining", "test"),
                       [s["trace"] for s in split if s["split"] == "test"])
    train = load_traces(os.path.join(a.mine_dir, "mining", "ordered"),
                        [s["trace"] for s in split if s["split"] == "train"])
    test_perm = permuted(test, a.seed)

    rows = psiminer_rows(a.mine_dir, planted, train, labels)
    rows += host_view(train, test, test_perm, labels, a, planted)
    rows += bin_view(train, test, test_perm, labels, a, planted)
    base = sum(labels[h] for h in test) / len(test)
    report = {"params": vars(a), "n_test": len(test), "base_rate": round(base, 4), "methods": rows}
    os.makedirs(os.path.join(a.mine_dir, "results"), exist_ok=True)
    json.dump(report, open(os.path.join(a.mine_dir, "results", a.out), "w"), indent=1)

    print("test hosts %d, base rate %.3f" % (len(test), base))
    print("%-18s %-8s %6s %6s %6s %8s  %-8s %s" % ("method", "view", "P", "R", "F1", "F1perm", "planted", "size"))
    for r in rows:
        if "skipped" in r:
            print("%-18s %-8s skipped: %s" % (r["method"], r.get("view", ""), r["skipped"]))
            continue
        hp = r.get("host_permuted")
        print("%-18s %-8s %6.3f %6.3f %6.3f %8s  %-8s %s" % (
            r["method"], r["view"], r["host"]["precision"], r["host"]["recall"], r["host"]["f1"],
            "%.3f" % hp["f1"] if hp else "-", r["planted_recovered"], r["size"]))


if __name__ == "__main__":
    main()
