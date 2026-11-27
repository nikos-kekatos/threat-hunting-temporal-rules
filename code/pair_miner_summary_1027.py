"""Summary of results_stats_2026-10-27/pair_miner/*.json -> PAIR_MINER.md and pair_miner_summary.json"""
import glob, json, os, re, statistics as st
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
D = os.path.join(ROOT, "results_stats_2026-10-27", "pair_miner")
rs = [json.load(open(f)) for f in sorted(glob.glob(D + "/*.json"))]
groups = {}
for r in rs:
    groups.setdefault(re.sub(r"_s\d+$", "", r["name"]), []).append(r)
out, L = {}, ["# Exhaustive two-step rules (code/pair_miner_1027.py)", "",
              "| config | n | rules | test F1 mean (sd) | P mean | F1 perm. mean | F1 reversed mean | planted |", "|---|---|---|---|---|---|---|---|"]
for g, xs in sorted(groups.items()):
    f = [x["test"]["f1"] for x in xs]
    o = {"n": len(xs), "rules": sorted({x["rule"] for x in xs}), "candidates": xs[0]["candidates"],
         "f1_mean": round(st.mean(f), 4), "f1_sd": round(st.stdev(f), 4) if len(f) > 1 else 0.0,
         "precision_mean": round(st.mean(x["test"]["precision"] for x in xs), 4),
         "f1_perm_mean": round(st.mean(x["test_permuted"]["f1"] for x in xs), 4),
         "f1_rev_mean": round(st.mean(x["test_reversed"]["f1"] for x in xs), 4),
         "perm_loss_max": round(max(x["test"]["f1"] - x["test_permuted"]["f1"] for x in xs), 4),
         "perm_loss_min": round(min(x["test"]["f1"] - x["test_permuted"]["f1"] for x in xs), 4),
         "flag_all_mean": round(st.mean(x["flag_all_f1"] for x in xs), 4),
         "f1_ci": [x["test"]["f1_ci"] for x in xs],
         "planted": sum(bool(x.get("planted_recovered")) for x in xs) if "planted" in xs[0] else None}
    out[g] = o
    L.append(f"| {g} | {o['n']} | {'; '.join(o['rules'])} | {o['f1_mean']} ({o['f1_sd']}) | {o['precision_mean']} | {o['f1_perm_mean']} | {o['f1_rev_mean']} | {o['planted']} |")
json.dump(out, open(os.path.join(ROOT, "results_stats_2026-10-27", "pair_miner_summary.json"), "w"), indent=1)
open(os.path.join(ROOT, "results_stats_2026-10-27", "PAIR_MINER.md"), "w").write("\n".join(L) + "\n")
print("\n".join(L))
