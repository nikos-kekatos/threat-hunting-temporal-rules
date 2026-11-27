#!/usr/bin/env python3
"""Check that every compiled SQL hunt query returns the evaluator's host set.

Loads the held-out traces of MINE_DIR into an in-memory SQLite table `bins`,
compiles each ordered ANOM rule with compile_query.compile_sql, and compares the
returned hosts with the hosts on which evaluate.completions fires.

usage: verify_sql.py MINE_DIR OUT_JSON
"""
import csv
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile_query import compile_sql  # noqa: E402
from evaluate import completions, load_traces, parse_antecedent  # noqa: E402


def main():
    mine_dir, out_json = sys.argv[1], sys.argv[2]
    meta = json.load(open(os.path.join(mine_dir, "rules.json")))
    split = list(csv.DictReader(open(os.path.join(mine_dir, "split.csv"))))
    names = [s["trace"] for s in split if s["split"] == "test"]
    tr = load_traces(os.path.join(mine_dir, "mining", "test"), names)
    cols = list(next(iter(tr.values()))[0].keys())
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE bins(host TEXT, %s)" % ", ".join(c + " INTEGER" for c in cols))
    for n, rows in tr.items():
        db.executemany("INSERT INTO bins VALUES (%s)" % ",".join("?" * (len(cols) + 1)),
                       [[n] + [r[c] for c in cols] for r in rows])
    db.execute("CREATE INDEX ix ON bins(host, t)")
    res = []
    for r in meta["rules"].get("ordered") or []:
        if r["consequent"].strip() not in ("ANOM", "HANOM"):
            continue
        sql = compile_sql(r["antecedent"])
        sql_hosts = {x[0] for x in db.execute(sql)}
        c, g = parse_antecedent(r["antecedent"])
        py_hosts = {n for n, rows in tr.items() if any(completions(c, g, rows))}
        res.append({"antecedent": r["antecedent"], "sql": sql, "n_sql": len(sql_hosts),
                    "n_eval": len(py_hosts), "equal": sql_hosts == py_hosts})
    out = {"rules": len(res), "equal": sum(x["equal"] for x in res), "detail": res}
    json.dump(out, open(out_json, "w"), indent=1)
    print("SQL check: %d of %d rules return identical host sets" % (out["equal"], out["rules"]))


if __name__ == "__main__":
    main()
