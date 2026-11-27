#!/usr/bin/env python3
"""Measure the execution cost of compiled hunt queries (added 2026-10-26).

Loads the held-out per-second traces of one mining directory into an SQLite
table `bins` (index on host, t), compiles each antecedent with
compile_query.compile_sql, and times each query (median of REPS runs).
Reports rows, hosts, self-join copies, literals, hosts returned and seconds.

Queries are timed in range form (see range_form); --check also runs the
compile_query output and asserts the same host set (use on small tables only,
because the subtraction form cannot use the index).

usage: query_cost.py MINE_DIR OUT_JSON [REPS] [--check]
"""
import csv
import json
import os
import platform
import re
import sqlite3
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile_query import compile_sql  # noqa: E402
from evaluate import parse_antecedent  # noqa: E402

GAP = re.compile(r"(s\d+)\.t - (s\d+)\.t BETWEEN (\d+) AND (\d+)")


def range_form(sql):
    """Same query with each delay written as a range on the later copy's t,
    which lets SQLite use the (host, t) index. Semantics unchanged."""
    return GAP.sub(lambda m: "%s.t BETWEEN %s.t + %s AND %s.t + %s" %
                   (m.group(1), m.group(2), m.group(3), m.group(2), m.group(4)), sql)

QUERIES = [
    ("analyst H2 (same second)", "DPORT_MANY && SYN_DOM"),
    ("clean-control rule", "SYN_DOM ##[1:2] DPORT_MANY"),
    ("delay-sweep rule", "SYN_DOM ##[0:3] !SYN_DOM ##[0:2] !SYN_DOM ##[0:1] DPORT_MANY"),
]


def main():
    mine_dir, out_json = sys.argv[1], sys.argv[2]
    reps = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    check_naive = len(sys.argv) > 4 and sys.argv[4] == "--check"
    split = list(csv.DictReader(open(os.path.join(mine_dir, "split.csv"))))
    names = [s["trace"] for s in split if s["split"] == "test"]
    tdir = os.path.join(mine_dir, "mining", "test")
    db = sqlite3.connect(":memory:")
    cols = None
    t0 = time.perf_counter()
    nrows = 0
    for n in names:
        with open(os.path.join(tdir, n + ".csv")) as fh:
            rd = csv.reader(fh)
            hdr = next(rd)
            if cols is None:
                cols = hdr
                db.execute("CREATE TABLE bins(host TEXT, %s)" % ", ".join(c + " INTEGER" for c in cols))
            rows = [[n] + [int(v) for v in r] for r in rd]
            db.executemany("INSERT INTO bins VALUES (%s)" % ",".join("?" * (len(cols) + 1)), rows)
            nrows += len(rows)
    db.execute("CREATE INDEX ix ON bins(host, t)")
    load_s = time.perf_counter() - t0
    res = []
    for label, ant in QUERIES:
        sql_naive = compile_sql(ant)
        sql = range_form(sql_naive)
        if check_naive:
            same = {x[0] for x in db.execute(sql_naive)} == {x[0] for x in db.execute(sql)}
        else:
            same = None
        conjs, _ = parse_antecedent(ant)
        lits = sum(len([x for x in c.split("&&") if x.strip()]) for c in conjs)
        times = []
        hosts = None
        for _ in range(reps):
            t1 = time.perf_counter()
            hosts = {x[0] for x in db.execute(sql)}
            times.append(time.perf_counter() - t1)
        res.append({"label": label, "antecedent": ant, "sql": sql, "copies": len(conjs),
                    "literals": lits, "same_hosts_as_compiler_output": same, "hosts_returned": len(hosts),
                    "seconds_median": round(statistics.median(times), 3),
                    "seconds_all": [round(x, 3) for x in times]})
        print("same=%s " % same, end="")
        print("%-28s copies=%d literals=%d hosts=%d median=%.3fs" %
              (label, len(conjs), lits, len(hosts), statistics.median(times)))
    out = {"mine_dir": os.path.relpath(mine_dir), "hosts": len(names), "rows": nrows,
           "load_seconds": round(load_s, 1), "reps": reps, "sqlite": sqlite3.sqlite_version,
           "python": platform.python_version(), "machine": platform.machine(), "queries": res}
    json.dump(out, open(out_json, "w"), indent=1)
    print("rows %d hosts %d load %.1fs" % (nrows, len(names), load_s))


if __name__ == "__main__":
    main()
