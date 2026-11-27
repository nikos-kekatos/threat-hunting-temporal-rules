"""Exhaustive two-step temporal rule baseline (review 2026-10-27, option B follow-up; exploratory, after the freeze).

Candidate rule  A ##[lo:hi] B : the host has a second t with predicate A and a second t' with predicate B,
lo <= t' - t <= hi, for A != B among the Table I predicates except ACTIVE/ANOM/HANOM and 1 <= lo <= hi <= DMAX.
Every candidate is scored by host F1 on the training hosts of a split; the best one (ties: narrower window,
then higher training precision) is frozen and scored on the held-out hosts, on row-permuted copies of their
traces (values shuffled over the host's own seconds, as evaluate.permuted) and in reversed order (B ##[lo:hi] A).
Planted check (synthetic): selected rule is SYN_DOM ##[lo:hi] DPORT_MANY with [lo,hi] inside the planted range
and held-out F1 above flag-all + 0.05 (MARGIN of compare_xai.py).
Traces are read one host at a time; per host only a 12 x 12 x DMAX Boolean tensor is kept.
usage: code/.venv/bin/python code/pair_miner_1027.py NAME MINE_DIR [--planted LO-HI] [--dmax 8]
Output: results_stats_2026-10-27/pair_miner/NAME.json
"""
import argparse
import csv
import json
import math
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mine import PREDICATES  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PREDS = [(n, f) for n, _, f in PREDICATES if n not in ("ACTIVE", "ANOM", "HANOM")]
NAMES = [n for n, _ in PREDS]
MARGIN = 0.05


def read_host(path):
    with open(path) as fh:
        return [{k: int(v) for k, v in r.items()} for r in csv.DictReader(fh)]


def tensor(rows, dmax):
    """M[a, b, d-1] = exists t: A(t) and B(t + d)"""
    T = max(r["t"] for r in rows) + dmax + 2 if rows else dmax + 2
    P = np.zeros((len(PREDS), T), np.uint8)
    for r in rows:
        for i, (_, f) in enumerate(PREDS):
            if f(r):
                P[i, r["t"]] = 1
    M = np.zeros((len(PREDS), len(PREDS), dmax), bool)
    for d in range(1, dmax + 1):
        M[:, :, d - 1] = (P[:, :T - d].astype(np.int32) @ P[:, d:].T.astype(np.int32)) > 0
    return M


def permute(rows, rng):
    vals = [{k: v for k, v in r.items() if k != "t"} for r in rows]
    rng.shuffle(vals)
    return [dict(t=r["t"], **v) for r, v in zip(rows, vals)]


def windows(dmax):
    return [(lo, hi) for lo in range(1, dmax + 1) for hi in range(lo, dmax + 1)]


def fire(M, a, b, lo, hi):
    """M: (hosts, 12, 12, dmax) -> host flags"""
    return M[:, a, b, lo - 1:hi].any(axis=1)


def metrics(y, p):
    tp = int(np.sum(y & p)); fp = int(np.sum(~y & p)); fn = int(np.sum(y & ~p)); tn = int(np.sum(~y & ~p))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), "precision_ci": wilson(tp, tp + fp), "recall_ci": wilson(tp, tp + fn)}


def wilson(k, n, z=1.959964):
    if n == 0:
        return None
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]


def boot_f1(y, p, B=2000, seed=20261027):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(y), size=(B, len(y)), dtype=np.int32)
    f = []
    for i in idx:
        yy, pp = y[i], p[i]
        tp = np.sum(yy & pp); fp = np.sum(~yy & pp); fn = np.sum(yy & ~pp)
        f.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return [round(float(np.percentile(f, 2.5)), 4), round(float(np.percentile(f, 97.5)), 4)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("mine_dir")
    ap.add_argument("--planted", default="", help="LO-HI planted delay range (synthetic)")
    ap.add_argument("--dmax", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    md = a.mine_dir
    split = list(csv.DictReader(open(os.path.join(md, "split.csv"))))
    lab = {s["trace"]: s["class"] == "anomalous" for s in split}
    tr = [s["trace"] for s in split if s["split"] == "train"]
    te = [s["trace"] for s in split if s["split"] == "test"]
    rng = random.Random(a.seed)
    Mtr = np.array([tensor(read_host(os.path.join(md, "mining", "ordered", h + ".csv")), a.dmax) for h in tr])
    Mte, Mpe = [], []
    for h in sorted(te):
        rows = read_host(os.path.join(md, "mining", "test", h + ".csv"))
        Mte.append(tensor(rows, a.dmax)); Mpe.append(tensor(permute(rows, rng), a.dmax))
    te = sorted(te)
    Mte, Mpe = np.array(Mte), np.array(Mpe)
    ytr = np.array([lab[h] for h in tr]); yte = np.array([lab[h] for h in te])
    cands = []
    for i in range(len(NAMES)):
        for j in range(len(NAMES)):
            if i == j:
                continue
            for lo, hi in windows(a.dmax):
                m = metrics(ytr, fire(Mtr, i, j, lo, hi))
                cands.append((m["f1"], -(hi - lo), m["precision"], i, j, lo, hi))
    cands.sort(reverse=True)
    f1tr, _, _, i, j, lo, hi = cands[0]
    rule = f"{NAMES[i]} ##[{lo}:{hi}] {NAMES[j]}"
    p = fire(Mte, i, j, lo, hi)
    test = metrics(yte, p)
    test["f1_ci"] = boot_f1(yte, p)
    base = float(yte.mean())
    flag_all = round(2 * base / (1 + base), 4)
    out = {"name": a.name, "mine_dir": os.path.relpath(md, ROOT), "dmax": a.dmax, "candidates": len(cands),
           "n_train": len(tr), "n_test": len(te), "base_rate": round(base, 4), "flag_all_f1": flag_all,
           "rule": rule, "size": "2 literals", "train_f1": f1tr, "test": test,
           "test_permuted": metrics(yte, fire(Mpe, i, j, lo, hi)),
           "test_reversed": metrics(yte, fire(Mte, j, i, lo, hi)),
           "top5_train": [{"rule": f"{NAMES[c[3]]} ##[{c[5]}:{c[6]}] {NAMES[c[4]]}", "train_f1": c[0]} for c in cands[:5]]}
    if a.planted:
        plo, _, phi = a.planted.partition("-")
        plo, phi = int(plo), int(phi or plo)
        out["planted"] = [plo, phi]
        out["planted_recovered"] = bool(NAMES[i] == "SYN_DOM" and NAMES[j] == "DPORT_MANY" and lo <= phi and hi >= plo
                                        and test["f1"] > flag_all + MARGIN)
    od = os.path.join(ROOT, "results_stats_2026-10-27", "pair_miner")
    os.makedirs(od, exist_ok=True)
    json.dump(out, open(os.path.join(od, a.name + ".json"), "w"), indent=1)
    print(a.name, rule, "train", f1tr, "test", test["f1"], test["f1_ci"], "perm", out["test_permuted"]["f1"],
          "rev", out["test_reversed"]["f1"], "flag-all", flag_all, out.get("planted_recovered", ""), flush=True)


if __name__ == "__main__":
    main()
