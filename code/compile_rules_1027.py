"""SQL for the tree, RIPPER and Anchors outputs (review 2026-10-27; exploratory, after the freeze).

The models of compare_xai.py are refitted with the same data, seeds and settings (host view: tree d3, RIPPER;
bin view with lags 0..L: tree d3, RIPPER), and the modal anchor is read from results/xai_L{L}.json. Each output is
compiled to SQL over the table bins(host, t, ...) with one row per host and second:
  * a lagged literal P_lagk becomes a LEFT JOIN of the copy b_k on (host, t - k); P holds when the copy exists and
    satisfies the threshold of Table I, and !P holds when the copy is missing or does not satisfy it (the zero
    padding of compare_xai.bin_matrix); a tree leaf or a RIPPER rule is a conjunction, the query the UNION;
  * a host-view rule is a condition on one row of aggregates per host (active seconds, max and mean of each
    feature over active seconds, as evaluate.host_features); tree paths are threshold conjunctions, and RIPPER's
    bins are reproduced with the digitize rule of wittgenstein's BinTransformer.
The hosts returned by each query are compared with the hosts flagged by the Python model on the held-out traces,
and each query is timed (median of REPS) in SQLite on disk.
usage: code/.venv/bin/python code/compile_rules_1027.py NAME MINE_DIR [--lags 3] [--reps 3] [--db PATH]
Output: results_stats_2026-10-27/sql_rules/NAME.json
"""
import argparse
import csv
import json
import os
import sqlite3
import statistics
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mine import PREDICATES, DERIVED  # noqa: E402
from evaluate import host_features, feature_names, AGG_COLS, load_traces  # noqa: E402
from compare_xai import bin_matrix, lag_names, bin_train, tree_literals, LAG_RE  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
COND = {n: c for n, c, _ in PREDICATES}


def pred_sql(name, alias):
    col, val = COND[name].split(">=")
    return f"{alias}.{col.strip()} >= {val.strip()}"


def conj_sql(lits):
    """lits: [(lagged name, positive)] -> SELECT over s0 with LEFT JOINs"""
    lags = sorted({int(LAG_RE.match(f).group(2)) for f, _ in lits})
    joins = "".join(f" LEFT JOIN bins b{k} ON b{k}.host = s0.host AND b{k}.t = s0.t - {k}" for k in lags if k > 0)
    where = []
    for f, pos in lits:
        p, k = LAG_RE.match(f).group(1), int(LAG_RE.match(f).group(2))
        al = "s0" if k == 0 else f"b{k}"
        c = pred_sql(p, al)
        if k == 0:
            where.append(c if pos else f"NOT ({c})")
        else:
            where.append(f"({al}.host IS NOT NULL AND {c})" if pos else f"({al}.host IS NULL OR NOT ({c}))")
    return f"SELECT DISTINCT s0.host FROM bins s0{joins} WHERE " + (" AND ".join(where) or "1")


def union(groups):
    return "\nUNION\n".join(conj_sql(g) for g in groups) if groups else "SELECT host FROM bins WHERE 0"


def host_tree_paths(clf, names):
    t = clf.tree_
    out = []

    def walk(n, path):
        if t.children_left[n] == -1:
            if np.argmax(t.value[n][0]) == 1:
                out.append(path)
            return
        f, th = names[t.feature[n]], float(t.threshold[n])
        walk(t.children_left[n], path + [f"{f} <= {th!r}"])
        walk(t.children_right[n], path + [f"{f} > {th!r}"])
    walk(0, [])
    return out


def ripper_host_sql_conds(rip):
    bt = rip.bin_transformer_
    rules = []
    for r in rip.ruleset_.rules:
        cs = []
        for c in r.conds:
            f, v = c.feature, str(c.val)
            if hasattr(bt, "thresholds_") and f in bt.thresholds_:
                th = list(bt.thresholds_[f]); bins = list(bt.bins_[f]); k = bins.index(v)
                dig = "(" + " + ".join(f"({f} >= {x!r})" for x in th) + ")"
                cs.append(f"MIN(MAX({dig}, 1), {len(bins)}) - 1 = {k}")
            elif f in getattr(bt, "bins_", {}):
                iv = bt._strs_to_intervals(bt.bins_[f], f)[list(bt.bins_[f]).index(v)]
                lo_op = ">=" if iv.closed in ("left", "both") else ">"
                hi_op = "<=" if iv.closed in ("right", "both") else "<"
                parts = []
                if np.isfinite(iv.left):
                    parts.append(f"{f} {lo_op} {float(iv.left)!r}")
                if np.isfinite(iv.right):
                    parts.append(f"{f} {hi_op} {float(iv.right)!r}")
                cs.append("(" + (" AND ".join(parts) or "1") + ")")
            else:
                cs.append(f"{f} = {float(v)!r}")
        rules.append(cs)
    return rules


def host_query(paths):
    agg = ", ".join(f"MAX({c}) AS max_{c}, AVG(CAST({c} AS REAL)) AS mean_{c}" for c in AGG_COLS)
    view = f"SELECT host, COUNT(*) AS active_s, {agg} FROM bins WHERE pkts > 0 GROUP BY host"
    cond = " OR ".join("(" + " AND ".join(p) + ")" for p in paths) or "0"
    return f"SELECT host FROM ({view}) WHERE {cond}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name"); ap.add_argument("mine_dir")
    ap.add_argument("--lags", type=int, default=3); ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--max-neg-bins", type=int, default=50000)
    ap.add_argument("--db", default=None)
    a = ap.parse_args()
    from sklearn.tree import DecisionTreeClassifier
    import wittgenstein as lw
    md = a.mine_dir
    split = list(csv.DictReader(open(os.path.join(md, "split.csv"))))
    lab = {s["trace"]: s["class"] == "anomalous" for s in split}
    tr = [s["trace"] for s in split if s["split"] == "train"]
    te = [s["trace"] for s in split if s["split"] == "test"]
    train = load_traces(os.path.join(md, "mining", "ordered"), tr)
    fn = feature_names(); names = lag_names(a.lags)
    # host view, as compare_xai.host_view
    Xh = np.array([host_features(r) for r in train.values()], float); yh = np.array([int(lab[h]) for h in train])
    htree = DecisionTreeClassifier(max_depth=3, random_state=0).fit(Xh, yh)
    hrip = lw.RIPPER(random_state=a.seed)
    hrip.fit(pd.DataFrame(Xh, columns=fn).assign(y=yh), class_feat="y", pos_class=1)
    # bin view, as compare_xai.bin_view
    Xb, yb = bin_train(train, a.lags, a.max_neg_bins, a.seed)
    btree = DecisionTreeClassifier(max_depth=3, random_state=0).fit(Xb, yb)
    df = pd.DataFrame(Xb.astype(str), columns=names); df["y"] = yb
    brip = lw.RIPPER(random_state=a.seed); brip.fit(df, class_feat="y", pos_class=1)
    brip_groups = [[(c.feature, str(c.val) in ("1", "True")) for c in r.conds] for r in brip.ruleset_.rules]
    ref = json.load(open(os.path.join(md, "results", f"xai_L{a.lags}.json")))
    anc = next((m for m in ref["methods"] if m.get("method") == "anchors" and "explanation" in m), None)
    anc_groups = [[(x.strip().lstrip("!").strip(), not x.strip().startswith("!")) for x in anc["explanation"].split("&&")]] if anc else None
    idx = {n: i for i, n in enumerate(names)}

    def conj_pred(groups):
        def pr(X):
            out = np.zeros(len(X), bool)
            for g in groups:
                m = np.ones(len(X), bool)
                for f, pos in g:
                    m &= X[:, idx[f]] == int(pos)
                out |= m
            return out
        return pr
    queries = {"tree_d3|host": host_query(host_tree_paths(htree, fn)),
               "ripper|host": host_query(ripper_host_sql_conds(hrip)),
               "tree_d3|bin": union(tree_literals(btree, names)),
               "ripper|bin": union(brip_groups)}
    preds = {"tree_d3|bin": lambda X: btree.predict(X) == 1, "ripper|bin": conj_pred(brip_groups)}
    if anc_groups:
        queries["anchors|bin"] = union(anc_groups); preds["anchors|bin"] = conj_pred(anc_groups)
    # Python flags on the held-out hosts, one host at a time; SQLite table on disk
    dbp = a.db or os.path.join(ROOT, "results_stats_2026-10-27", "sql_rules", a.name + ".sqlite")
    os.makedirs(os.path.dirname(dbp), exist_ok=True)
    if os.path.exists(dbp):
        os.remove(dbp)
    db = sqlite3.connect(dbp)
    db.execute("CREATE TABLE bins(host TEXT, %s)" % ", ".join(c + " INTEGER" for c in DERIVED))
    flags = {k: set() for k in queries}; HX = []
    t0 = time.perf_counter(); nrows = 0
    for h in te:
        rows = []
        with open(os.path.join(md, "mining", "test", h + ".csv")) as fh:
            for r in csv.DictReader(fh):
                rows.append({k: int(v) for k, v in r.items()})
        db.executemany("INSERT INTO bins VALUES (%s)" % ",".join("?" * (len(DERIVED) + 1)),
                       [[h] + [r[c] for c in DERIVED] for r in rows])
        nrows += len(rows)
        HX.append(host_features(rows))
        X = bin_matrix(rows, a.lags)
        for k, pr in preds.items():
            if pr(X).any():
                flags[k].add(h)
    db.commit(); db.execute("CREATE INDEX ix ON bins(host, t)"); db.commit()
    load_s = time.perf_counter() - t0
    HX = np.array(HX, float)
    flags["tree_d3|host"] = {h for h, p in zip(te, htree.predict(HX)) if p == 1}
    flags["ripper|host"] = {h for h, p in zip(te, hrip.predict(pd.DataFrame(HX, columns=fn))) if p}
    res = {}
    for k, q in queries.items():
        ts = []
        for _ in range(a.reps):
            t1 = time.perf_counter(); got = {x[0] for x in db.execute(q)}; ts.append(time.perf_counter() - t1)
        f1 = None
        y = np.array([lab[h] for h in te]); p = np.array([h in got for h in te])
        tp = int((y & p).sum()); fp = int((~y & p).sum()); fn_ = int((y & ~p).sum())
        f1 = round(2 * tp / (2 * tp + fp + fn_), 4) if tp else 0.0
        ref_f1 = next((m["host"]["f1"] for m in ref["methods"] if "host" in m and f"{m['method']}|{m['view']}" == k), None)
        res[k] = {"same_hosts_as_python": got == flags[k], "hosts_sql": len(got), "hosts_python": len(flags[k]),
                  "f1_sql": f1, "f1_xai": ref_f1, "median_s": round(statistics.median(ts), 3), "sql": q}
        print(a.name, k, res[k]["same_hosts_as_python"], len(got), len(flags[k]), f1, ref_f1, res[k]["median_s"], flush=True)
    out = {"name": a.name, "mine_dir": os.path.relpath(md, ROOT), "lags": a.lags, "rows": nrows, "hosts": len(te),
           "load_s": round(load_s, 1), "queries": res}
    json.dump(out, open(os.path.join(ROOT, "results_stats_2026-10-27", "sql_rules", a.name + ".json"), "w"), indent=1)
    db.close(); os.remove(dbp)


if __name__ == "__main__":
    main()
