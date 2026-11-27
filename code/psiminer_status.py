#!/usr/bin/env python3
"""Per-configuration PSI-Miner run status (corrections guide 2026-10-22, item 4.6).

Scans every mine directory (one with rules.json) under the ch8 folder, excluding backups, and writes
results_corrections_2026-10-22/psiminer_runs.csv with: miner binary and source commit, bias,
vocabulary workaround (constant predicates dropped before mining), predicates dropped, exit status
recorded by mine.py, whether the miner log contains its completion line, and the number of rules with
consequent ANOM. A run counts as completed only when the log has "Completed PSI-Mining"; a missing
completion line with a partial assertion file is a crash, not an empty result.

usage: psiminer_status.py   (no arguments; paths are relative to this file)
"""
import csv
import hashlib
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "results_corrections_2026-10-22")


def miner_info(path):
    src = os.path.dirname(os.path.dirname(path))
    try:
        commit = subprocess.run(["git", "-C", src, "log", "-1", "--format=%H %ad"], capture_output=True,
                                text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", src, "status", "--short", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()
    except OSError:
        commit, dirty = "unknown", "unknown"
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else "missing"
    return commit, ("tracked sources modified" if dirty else "tracked sources unmodified"), sha


def main():
    os.makedirs(OUT, exist_ok=True)
    rows, binaries = [], {}
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = sorted(d for d in dn if not d.startswith("backups") and d not in (".venv", "mining", "logs"))
        if "rules.json" not in fn:
            continue
        meta = json.load(open(os.path.join(dp, "rules.json")))
        p = meta.get("params", {})
        r = meta.get("rules", {})
        log = os.path.join(dp, "mining", "ordered", "hunt.conf.log")
        completed = os.path.exists(log) and "Completed PSI-Mining" in open(log, errors="replace").read()
        ordered = r.get("ordered")
        n_anom = sum(1 for x in ordered if x["consequent"].strip() == "ANOM") if isinstance(ordered, list) else ""
        crashed = r.get("ordered_crashed", "")
        status = "completed" if completed else ("crashed (exit %s)" % crashed if crashed != "" else
                                               "crashed (no completion line)" if os.path.exists(log) else "no log")
        b = p.get("psiminer", "")
        if b and b not in binaries:
            binaries[b] = miner_info(b)
        rows.append({"run": os.path.relpath(dp, ROOT), "bias": p.get("bias", ""),
                     "workaround_drop_constant": p.get("drop_constant", False),
                     "dropped": " ".join(meta.get("dropped", [])),
                     "train_per_class": json.dumps(meta.get("train_counts", {})),
                     "exit_recorded": crashed, "log_completed": completed, "status": status,
                     "anom_rules": n_anom, "miner": b})
    rows.sort(key=lambda x: x["run"])
    with open(os.path.join(OUT, "psiminer_runs.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(OUT, "psiminer_binary.txt"), "w") as fh:
        for b, (c, d, s) in binaries.items():
            fh.write("binary %s\nsource commit %s (github.com/antoniobruto/PSIMiner)\n%s\nsha256 %s\n"
                     "source-level indexing fix (ignorePredicate(j) -> j+1): NOT applied; all runs use the "
                     "unmodified binary, MAWI runs with drop_constant=True use the vocabulary workaround\n\n"
                     % (b, c, d, s))
    for x in rows:
        print("%-40s bias %-2s wk %-5s %-28s ANOM rules %s" % (x["run"], x["bias"], x["workaround_drop_constant"],
                                                               x["status"], x["anom_rules"]))


if __name__ == "__main__":
    main()
