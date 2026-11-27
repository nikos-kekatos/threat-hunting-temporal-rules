"""Score the MAWI rules of the fixed PSI-Miner (results_fix_*/mine_s*) on held-out hosts (2026-10-27; exploratory).

Rule selection as compare_xai.psiminer_rows: target ANOM rules; 'own score' = highest PSI-Miner CORRELATION,
'trainsel' = highest host F1 on the training hosts (evaluate.score_rule). Held-out scoring through the SQL
compiler (compile_query.compile_sql in the range form of query_cost.py), which returns the evaluator's host set
(21/21 rules, query_cost --check), over an on-disk SQLite table, so that the 8.5 million held-out host-seconds are
never held in memory. The order control uses a second table with each held-out trace row-permuted exactly as
evaluate.permuted (random.Random(seed), hosts in sorted order). The playbook is the union of all ANOM rules.
usage: code/.venv/bin/python code/psiminer_mawi_1027.py MINE_DIR OUT_JSON
"""
import csv
import json
import os
import random
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evaluate import load_traces, host_metrics, parse_antecedent, score_rule  # noqa: E402
from compile_query import compile_sql  # noqa: E402
from query_cost import range_form  # noqa: E402
from mine import DERIVED  # noqa: E402


def boot_f1(y, p, B=2000, seed=20261027):
    rng = np.random.default_rng(seed)
    f = []
    for i in rng.integers(0, len(y), size=(B, len(y)), dtype=np.int32):
        yy, pp = y[i], p[i]
        tp = np.sum(yy & pp); fp = np.sum(~yy & pp); fn = np.sum(yy & ~pp)
        f.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return [round(float(np.percentile(f, 2.5)), 4), round(float(np.percentile(f, 97.5)), 4)]


def main():
    md, out_json = sys.argv[1], sys.argv[2]
    seed = 1
    meta = json.load(open(os.path.join(md, "rules.json")))
    split = list(csv.DictReader(open(os.path.join(md, "split.csv"))))
    lab = {s["trace"]: s["class"] == "anomalous" for s in split}
    tr = [s["trace"] for s in split if s["split"] == "train"]
    te = sorted(s["trace"] for s in split if s["split"] == "test")
    res = {"mine_dir": md, "crashed": meta["rules"].get("ordered_crashed"), "n_test": len(te)}
    rules = [r for r in (meta["rules"].get("ordered") or []) if r["consequent"].strip() == "ANOM"]
    res["anom_rules"] = len(rules)
    if not rules:
        json.dump(res, open(out_json, "w"), indent=1); print(res); return
    train = load_traces(os.path.join(md, "mining", "ordered"), tr)
    for r in rules:
        conjs, gaps = parse_antecedent(r["antecedent"])
        flags, _, _ = score_rule(conjs, gaps, r["lo"], r["hi"], train, "ANOM")
        r["train"] = host_metrics(flags, lab)
    db_path = out_json + ".sqlite"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = sqlite3.connect(db_path)
    cols = ", ".join(c + " INTEGER" for c in DERIVED)
    db.execute(f"CREATE TABLE bins(host TEXT, {cols})"); db.execute(f"CREATE TABLE bins_perm(host TEXT, {cols})")
    rng = random.Random(seed)
    ph = ",".join("?" * (len(DERIVED) + 1))
    for h in te:
        with open(os.path.join(md, "mining", "test", h + ".csv")) as fh:
            rows = [{k: int(v) for k, v in r.items()} for r in csv.DictReader(fh)]
        db.executemany(f"INSERT INTO bins VALUES ({ph})", [[h] + [r[c] for c in DERIVED] for r in rows])
        vals = [{k: v for k, v in r.items() if k != "t"} for r in rows]
        rng.shuffle(vals)
        prow = [dict(t=r["t"], **v) for r, v in zip(rows, vals)]
        db.executemany(f"INSERT INTO bins_perm VALUES ({ph})", [[h] + [r[c] for c in DERIVED] for r in prow])
    db.commit()
    db.execute("CREATE INDEX ix ON bins(host, t)"); db.execute("CREATE INDEX ixp ON bins_perm(host, t)"); db.commit()
    y = np.array([lab[h] for h in te])

    def hosts(rule, table):
        q = range_form(compile_sql(rule["antecedent"])).rstrip(";").replace("bins ", table + " ")
        return {x[0] for x in db.execute(q)}

    def score(hs):
        p = np.array([h in hs for h in te])
        return host_metrics({h: bool(v) for h, v in zip(te, p)}, lab), p

    for r in rules:
        r["test"], _ = score(hosts(r, "bins"))
    own = max(rules, key=lambda r: r.get("correlation", 0.0))
    sel = max(rules, key=lambda r: r["train"]["f1"])
    for name, r in (("own_score", own), ("trainsel", sel)):
        m, p = score(hosts(r, "bins"))
        mp, _ = score(hosts(r, "bins_perm"))
        res[name] = {"rule": r["antecedent"] + " |=> ##[%g:%g] ANOM" % (r["lo"], r["hi"]),
                     "literals": sum(len([x for x in c.split("&&") if x.strip()]) for c in parse_antecedent(r["antecedent"])[0]),
                     "train_f1": r["train"]["f1"], "test": m, "test_f1_ci": boot_f1(y, p), "test_permuted": mp}
    allh = set().union(*(hosts(r, "bins") for r in rules))
    res["playbook"], _ = score(allh)
    res["rules"] = [{"rule": r["antecedent"], "train_f1": r["train"]["f1"], "test_f1": r["test"]["f1"],
                     "correlation": r.get("correlation")} for r in rules]
    db.close(); os.remove(db_path)
    json.dump(res, open(out_json, "w"), indent=1)
    print(os.path.basename(md), len(rules), "trainsel", res["trainsel"]["rule"], res["trainsel"]["test"]["f1"],
          res["trainsel"]["test_f1_ci"], "perm", res["trainsel"]["test_permuted"]["f1"], "playbook", res["playbook"]["f1"], flush=True)


if __name__ == "__main__":
    main()
