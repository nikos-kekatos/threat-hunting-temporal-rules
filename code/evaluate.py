#!/usr/bin/env python3
"""Evaluate mined rules as hunt queries on held-out hosts, with controls and a tree baseline.

Input: the output directory of mine.py (rules.json, split.csv, mining/{ordered,test}/).
For every mined rule whose consequent is ANOM:
  * host level (the hunting view): a held-out host is flagged when the rule's
    antecedent completes in at least one of its one-second bins; precision and
    recall against the MAWILab class, with Wilson 95% intervals;
  * bin level: confidence = share of antecedent completions followed by an ANOM
    bin inside the rule's window;
  * window-collapse control: the same literals as one same-second conjunction
    with window [0,0]; window gain = confidence(rule) - confidence(collapsed);
  * permutation control: the rule re-scored on row-permuted copies of the test
    traces (seeded), which keeps every row and destroys order.
The union of all ANOM rules is scored as one hunt playbook. A depth-limited
decision tree on per-host aggregates (scikit-learn, train split) is the baseline.

usage: evaluate.py MINE_DIR [--seed 1] [--tree-depth 3]
"""
import argparse
import csv
import json
import math
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mine import PREDICATES, DERIVED, NUM, TARGETS  # noqa: E402

PRED = {p[0]: p[2] for p in PREDICATES}
SEP = re.compile(r"##\[\s*(" + NUM + r")\s*:\s*(" + NUM + r")\s*\]")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def literal_mask(conj, rows):
    lits = [x.strip() for x in conj.split("&&") if x.strip()]
    out = []
    for r in rows:
        ok = True
        for lit in lits:
            neg = lit.startswith("!")
            name = lit.lstrip("!").strip()
            v = PRED[name](r)
            if v == neg:
                ok = False
                break
        out.append(ok)
    return out


def parse_antecedent(s):
    """'A && B ##[0:1] C' -> ([conj0, conj1, ...], [(lo, hi), ...])."""
    parts = SEP.split(s)
    conjs = [parts[0]]
    gaps = []
    for i in range(1, len(parts), 3):
        gaps.append((float(parts[i]), float(parts[i + 1])))
        conjs.append(parts[i + 2])
    return conjs, gaps


def completions(conjs, gaps, rows):
    """Boolean mask of bins at which the antecedent sequence completes."""
    cur = literal_mask(conjs[0], rows)
    n = len(rows)
    for (lo, hi), conj in zip(gaps, conjs[1:]):
        nxt = literal_mask(conj, rows)
        pre = [0] * (n + 1)
        for i in range(n):
            pre[i + 1] = pre[i] + (1 if cur[i] else 0)
        lo_k, hi_k = int(math.ceil(lo - 1e-9)), int(math.floor(hi + 1e-9))
        new = []
        for t in range(n):
            a, b = t - hi_k, t - lo_k
            a, b = max(a, 0), min(b, n - 1)
            new.append(nxt[t] and b >= a and pre[b + 1] - pre[a] > 0)
        cur = new
    return cur


def score_rule(conjs, gaps, lo, hi, traces, target="ANOM"):
    """Return host flags and (hits, completions) for bin-level confidence."""
    flags = {}
    hits = comps = 0
    lo_k, hi_k = int(math.ceil(lo - 1e-9)), int(math.floor(hi + 1e-9))
    for name, rows in traces.items():
        m = completions(conjs, gaps, rows)
        flags[name] = any(m)
        anom = [PRED[target](r) for r in rows]
        n = len(rows)
        for t in range(n):
            if m[t]:
                comps += 1
                if any(anom[k] for k in range(max(0, t + lo_k), min(n, t + hi_k + 1))):
                    hits += 1
    return flags, hits, comps


def host_metrics(flags, labels):
    tp = sum(1 for h, f in flags.items() if f and labels[h])
    fp = sum(1 for h, f in flags.items() if f and not labels[h])
    fn = sum(1 for h, f in flags.items() if not f and labels[h])
    tn = sum(1 for h, f in flags.items() if not f and not labels[h])
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(prec, 4), "precision_ci": [round(x, 4) for x in wilson(tp, tp + fp)],
            "recall": round(rec, 4), "recall_ci": [round(x, 4) for x in wilson(tp, tp + fn)],
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0}


def load_traces(d, names):
    out = {}
    for n in names:
        rows = []
        with open(os.path.join(d, n + ".csv")) as fh:
            for r in csv.DictReader(fh):
                rows.append({k: int(v) for k, v in r.items()})
        out[n] = rows
    return out


def permuted(traces, seed):
    rng = random.Random(seed)
    out = {}
    for n in sorted(traces):
        rows = traces[n]
        vals = [{k: v for k, v in r.items() if k != "t"} for r in rows]
        rng.shuffle(vals)
        out[n] = [dict(t=r["t"], **v) for r, v in zip(rows, vals)]
    return out


# Analyst hypotheses written before looking at the data, in the same predicate
# vocabulary as the mined rules: textbook signatures of the MAWILab anomaly classes.
EXPERT = [
    ("H1 network scan",  "DST_MANY && SYN_DOM"),
    ("H2 port scan",     "DPORT_MANY && SYN_DOM"),
    ("H3 SYN flood",     "PKTS_HI && SYN_DOM && SMALL_DOM"),
    ("H4 ICMP sweep",    "ICMP && DST_MANY"),
    ("H5 UDP scan",      "UDP_DOM && DPORT_MANY"),
    ("H6 rejected conn", "RST && PKTS_HI"),
]

AGG_COLS = [c for c in DERIVED if c not in ("t", "anom", "hanom")]  # labels, not features


def host_features(rows):
    act = [r for r in rows if r["pkts"] > 0] or rows
    f = [len(act)]
    for c in AGG_COLS:
        vals = [r[c] for r in act]
        f += [max(vals), sum(vals) / len(vals)]
    return f


def feature_names():
    names = ["active_s"]
    for c in AGG_COLS:
        names += ["max_" + c, "mean_" + c]
    return names


def tree_baseline(train, test, labels, depth):
    try:
        from sklearn.tree import DecisionTreeClassifier, export_text
    except ImportError:
        return {"skipped": "scikit-learn not installed"}
    Xtr = [host_features(r) for r in train.values()]
    ytr = [int(labels[h]) for h in train]
    clf = DecisionTreeClassifier(max_depth=depth, random_state=0).fit(Xtr, ytr)
    pred = clf.predict([host_features(r) for r in test.values()])
    flags = {h: bool(p) for h, p in zip(test, pred)}
    out = host_metrics(flags, labels)
    out["leaves"] = int(clf.get_n_leaves())
    out["tree"] = export_text(clf, feature_names=feature_names())
    out["flags"] = flags
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mine_dir")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tree-depth", type=int, default=3)
    a = ap.parse_args()

    meta = json.load(open(os.path.join(a.mine_dir, "rules.json")))
    split = list(csv.DictReader(open(os.path.join(a.mine_dir, "split.csv"))))
    labels = {s["trace"]: s["class"] == "anomalous" for s in split}
    tax = {s["trace"]: s["taxonomy"] for s in split}
    test_names = [s["trace"] for s in split if s["split"] == "test"]
    train_names = [s["trace"] for s in split if s["split"] == "train"]
    test = load_traces(os.path.join(a.mine_dir, "mining", "test"), test_names)
    test_perm = permuted(test, a.seed)
    train = load_traces(os.path.join(a.mine_dir, "mining", "ordered"), train_names)

    report = {"n_test": len(test), "n_test_anomalous": sum(labels[h] for h in test),
              "n_train": len(train), "rules": {}}
    for variant in ("ordered", "permuted"):
        rules = meta["rules"].get(variant) or []
        out = []
        playbook = {h: False for h in test}
        for r in rules:
            tgt = r["consequent"].strip()
            if tgt not in TARGETS:
                continue
            conjs, gaps = parse_antecedent(r["antecedent"])
            flags, hits, comps = score_rule(conjs, gaps, r["lo"], r["hi"], test, tgt)
            pflags, phits, pcomps = score_rule(conjs, gaps, r["lo"], r["hi"], test_perm, tgt)
            collapsed = [" && ".join(c.strip() for c in conjs)]
            _, chits, ccomps = score_rule(collapsed, [], 0, 0, test, tgt)
            conf = hits / comps if comps else 0.0
            cconf = chits / ccomps if ccomps else 0.0
            for h, f in flags.items():
                playbook[h] = playbook[h] or f
            out.append({
                **r,
                "length": sum(len([x for x in c.split("&&") if x.strip()]) for c in conjs),
                "steps": len(conjs),
                "host": host_metrics(flags, labels),
                "host_permuted": host_metrics(pflags, labels),
                "bin_confidence": round(conf, 4), "bin_completions": comps,
                "bin_confidence_permuted": round(phits / pcomps, 4) if pcomps else 0.0,
                "bin_confidence_collapsed": round(cconf, 4),
                "window_gain": round(conf - cconf, 4),
                "recall_by_taxonomy": {t: [sum(1 for h in test if labels[h] and tax[h] == t and flags[h]),
                                           sum(1 for h in test if labels[h] and tax[h] == t)]
                                       for t in sorted({tax[h] for h in test if labels[h]})},
            })
        report["rules"][variant] = out
        report["playbook_" + variant] = host_metrics(playbook, labels)
        if variant == "ordered":
            report["playbook_recall_by_taxonomy"] = {
                t: [sum(1 for h in test if labels[h] and tax[h] == t and playbook[h]),
                    sum(1 for h in test if labels[h] and tax[h] == t)]
                for t in sorted({tax[h] for h in test if labels[h]})}
    expert = []
    eplay = {h: False for h in test}
    for name, ante in EXPERT:
        flags, hits, comps = score_rule([ante], [], 0, 0, test, "ANOM")
        for h, f in flags.items():
            eplay[h] = eplay[h] or f
        expert.append({"name": name, "antecedent": ante, "host": host_metrics(flags, labels),
                       "bin_confidence": round(hits / comps, 4) if comps else 0.0,
                       "bin_completions": comps})
    report["expert"] = expert
    report["playbook_expert"] = host_metrics(eplay, labels)
    report["playbook_expert_recall_by_taxonomy"] = {
        t: [sum(1 for h in test if labels[h] and tax[h] == t and eplay[h]),
            sum(1 for h in test if labels[h] and tax[h] == t)]
        for t in sorted({tax[h] for h in test if labels[h]})}
    report["test_by_taxonomy"] = {t: sum(1 for h in test if tax[h] == t)
                                  for t in sorted({tax[h] for h in test})}
    tb = tree_baseline(train, test, labels, a.tree_depth)
    tflags = tb.pop("flags", None)
    if tflags is not None:
        report["tree_recall_by_taxonomy"] = {
            t: [sum(1 for h in test if labels[h] and tax[h] == t and tflags[h]),
                sum(1 for h in test if labels[h] and tax[h] == t)]
            for t in sorted({tax[h] for h in test if labels[h]})}
    tb["depth"] = a.tree_depth
    report["tree_baseline"] = tb

    os.makedirs(os.path.join(a.mine_dir, "results"), exist_ok=True)
    json.dump(report, open(os.path.join(a.mine_dir, "results", "hunt_eval.json"), "w"), indent=1)
    # compact console summary
    print("test hosts %d (%d anomalous), train hosts %d" %
          (report["n_test"], report["n_test_anomalous"], report["n_train"]))
    for v in ("ordered", "permuted"):
        print("== %s: %d ANOM rules; playbook %s" % (v, len(report["rules"][v]),
                                                   report["playbook_" + v]))
        for r in report["rules"][v]:
            print("  %-70s P=%.3f R=%.3f conf=%.3f perm=%.3f coll=%.3f gain=%+.3f" % (
                r["antecedent"][:70] + " ##[%g:%g]" % (r["lo"], r["hi"]), r["host"]["precision"],
                r["host"]["recall"], r["bin_confidence"], r["bin_confidence_permuted"],
                r["bin_confidence_collapsed"], r["window_gain"]))
    for e in expert:
        print("  expert %-18s P=%.3f R=%.3f conf=%.3f" % (e["name"], e["host"]["precision"],
                                                       e["host"]["recall"], e["bin_confidence"]))
    print("expert playbook", report["playbook_expert"])
    if "tree" in tb:
        print("tree: P=%.3f R=%.3f leaves=%d" % (tb["precision"], tb["recall"], tb["leaves"]))


if __name__ == "__main__":
    main()
