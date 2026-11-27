#!/usr/bin/env python3
"""Aggregate anchor_trainsel.py results (corrections guide 2026-10-22, item 4.1).

Reads results_xai_v2/gap1-G_s*/mine_b1/results/anchor_trainsel_L{3,8}.json,
results_xai/noise*_s*/mine_b1/results/anchor_trainsel_L3.json and results_dc/mine_s*/results/anchor_trainsel_L3.json
and writes results_corrections_2026-10-22/SUMMARY.md with mean +- s.d. over seeds or splits, the planted-order
count and the per-split host counts (fitting / selection / held-out / test half).
"""
import glob
import json
import os
import re
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "results_corrections_2026-10-22")


def ms(xs):
    if not xs:
        return "-"
    return "%.3f +- %.3f" % (statistics.mean(xs), statistics.stdev(xs) if len(xs) > 1 else 0.0)


def section(pattern, title, cfg_re):
    groups = {}
    for p in sorted(glob.glob(pattern)):
        L = re.search(r"anchor_trainsel_L(\d+)", p).group(1)
        cfg = re.search(cfg_re, p).group(1)
        groups.setdefault((cfg, L), []).append(json.load(open(p)))
    out = ["## " + title, "",
           "Counts per run: fit / selection (training partition) / held-out / test half, hosts (anomalous).", "",
           "| config | L | method | selection F1 | held-out F1 | test-half F1 | planted | runs | query (first run) |",
           "|---|---|---|---|---|---|---|---|---|"]
    counts = set()
    for (cfg, L), runs in sorted(groups.items(), key=lambda kv: (kv[0][0], int(kv[0][1]))):
        for r in runs:
            c = r["counts"]
            counts.add(" / ".join("%d (%d)" % (c[k]["hosts"], c[k]["anomalous"])
                                  for k in ("fit", "selection", "test_all", "test_half")))
        for m in [x["method"] for x in runs[0]["methods"]]:
            rows = [next(x for x in r["methods"] if x["method"] == m) for r in runs
                    if any(x["method"] == m for x in r["methods"])]
            sel = [x["selection"]["f1"] for x in rows if x.get("selection")]
            pl = [x.get("planted_recovered") for x in rows]
            pls = "%d/%d" % (sum(bool(v) for v in pl), len(pl)) if any(v is not None for v in pl) else "-"
            out.append("| %s | L%s | %s | %s | %s | %s | %s | %d | %s |" % (
                cfg, L, m, ms(sel), ms([x["test_all"]["f1"] for x in rows]),
                ms([x["test_half"]["f1"] for x in rows]), pls, len(rows), rows[0]["query"][:80]))
    out += ["", "Host counts seen: " + "; ".join(sorted(counts)), ""]
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    L = ["# Corrections 2026-10-22: Anchors selected inside the training partition (code/anchor_trainsel.py)", "",
         "Fit half: GBM training and anchor candidates. Selection half: selection by host F1. Both halves are",
         "training hosts. Held-out F1: all held-out hosts (the test partition of the main tables), read only after",
         "the queries are frozen. Test-half F1: the test half of anchor_frozen.py, for comparison. PSI-Miner row:",
         "rules mined on all training hosts, rule selected on the selection half (overlaps the mining hosts).", ""]
    L += section(os.path.join(ROOT, "results_xai_v2", "gap1-*_s*", "mine_b1", "results", "anchor_trainsel_L*.json"),
                 "Delay sweep (results_xai_v2)", r"(gap1-\d+)_s")
    L += section(os.path.join(ROOT, "results_xai", "noise*_s*", "mine_b1", "results", "anchor_trainsel_L3.json"),
                 "Stray events (results_xai)", r"(noise[0-9.]+)_s")
    L += section(os.path.join(ROOT, "results_dc", "mine_s*", "results", "anchor_trainsel_L3.json"),
                 "MAWI five splits (results_dc)", r"results_(dc)/")
    open(os.path.join(OUT, "SUMMARY.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
