#!/usr/bin/env python3
"""Score rules mined on one day against all hosts of another labelled day.

Inputs: MINE_DIR (mine.py output for the mining day: rules.json, split.csv,
mining/ordered/ for the tree's training hosts) and EXTRACT_DIR of the other day
(mawi_extract.py output). Every host of the other day is a test host. Reports the
same host-level metrics as evaluate.py for each ordered ANOM rule, the rule
playbook, the expert hypotheses and the decision tree trained on the mining day.

usage: portability.py MINE_DIR OTHER_EXTRACT_DIR OUT_JSON [--tree-depth 3]
"""
import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mine import active_only, derive  # noqa: E402
from evaluate import (EXPERT, host_metrics, load_traces, parse_antecedent,  # noqa: E402
                      score_rule, tree_baseline)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mine_dir")
    ap.add_argument("other_extract_dir")
    ap.add_argument("out_json")
    ap.add_argument("--tree-depth", type=int, default=3)
    a = ap.parse_args()

    meta = json.load(open(os.path.join(a.mine_dir, "rules.json")))
    hosts = list(csv.DictReader(open(os.path.join(a.other_extract_dir, "hosts.csv"))))
    tdir = os.path.join(a.other_extract_dir, "traces")
    hosts = [h for h in hosts if os.path.exists(os.path.join(tdir, h["trace"] + ".csv"))]
    test = {h["trace"]: derive(os.path.join(tdir, h["trace"] + ".csv"), h["class"] == "anomalous") for h in hosts}
    if meta.get("params", {}).get("active_only"):  # same trace transform as the mining day
        test = {k: active_only(v) for k, v in test.items()}
    labels = {h["trace"]: h["class"] == "anomalous" for h in hosts}
    tax = {h["trace"]: h["taxonomy"] for h in hosts}

    split = list(csv.DictReader(open(os.path.join(a.mine_dir, "split.csv"))))
    train_names = [s["trace"] for s in split if s["split"] == "train"]
    train = load_traces(os.path.join(a.mine_dir, "mining", "ordered"), train_names)
    train_labels = {s["trace"]: s["class"] == "anomalous" for s in split}
    labels_all = dict(train_labels)
    labels_all.update(labels)

    def by_tax(flags):
        return {t: [sum(1 for h in test if labels[h] and tax[h] == t and flags[h]),
                    sum(1 for h in test if labels[h] and tax[h] == t)]
                for t in sorted({tax[h] for h in test if labels[h]})}

    out = {"n_test": len(test), "n_test_anomalous": sum(labels.values()), "rules": []}
    play = {h: False for h in test}
    for r in meta["rules"].get("ordered") or []:
        if r["consequent"].strip() not in ("ANOM", "HANOM"):
            continue
        conjs, gaps = parse_antecedent(r["antecedent"])
        flags, hits, comps = score_rule(conjs, gaps, r["lo"], r["hi"], test, r["consequent"].strip())
        for h, f in flags.items():
            play[h] = play[h] or f
        out["rules"].append({"antecedent": r["antecedent"], "lo": r["lo"], "hi": r["hi"],
                             "host": host_metrics(flags, labels),
                             "bin_confidence": round(hits / comps, 4) if comps else 0.0})
    out["playbook"] = host_metrics(play, labels)
    out["playbook_recall_by_taxonomy"] = by_tax(play)
    eplay = {h: False for h in test}
    out["expert"] = []
    for name, ante in EXPERT:
        flags, _, _ = score_rule([ante], [], 0, 0, test)
        for h, f in flags.items():
            eplay[h] = eplay[h] or f
        out["expert"].append({"name": name, "host": host_metrics(flags, labels)})
    out["playbook_expert"] = host_metrics(eplay, labels)
    tb = tree_baseline(train, test, labels_all, a.tree_depth)
    if "flags" in tb:
        out["tree_recall_by_taxonomy"] = by_tax(tb.pop("flags"))
    out["tree_baseline"] = tb
    out["test_by_taxonomy"] = {t: sum(1 for h in test if tax[h] == t) for t in sorted(set(tax.values()))}
    json.dump(out, open(a.out_json, "w"), indent=1)
    print("portability: %d hosts (%d anomalous)" % (out["n_test"], out["n_test_anomalous"]))
    print(" playbook", out["playbook"])
    print(" expert  ", out["playbook_expert"])
    if "precision" in tb:
        print(" tree     P=%.3f R=%.3f" % (tb["precision"], tb["recall"]))


if __name__ == "__main__":
    main()
