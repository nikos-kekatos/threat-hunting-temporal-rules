#!/usr/bin/env python3
"""Prepare per-host traces for PSIMiner, run it, and parse the mined rules.

Input: the output directory of mawi_extract.py (hosts.csv, traces/*.csv).
Steps:
  1. split hosts 50/50 into train and test, stratified by class, by a stable
     hash of the trace name (the split is reproducible and independent of order);
  2. derive the mining columns (percentages, bytes per packet, ANOM target);
  3. write a PSIMiner config over the train traces, and a second config over
     row-permuted copies of the same traces (the joint-row permutation control:
     each row keeps its values, the order of rows inside a trace is destroyed);
  4. run PSIMiner on both and parse the assertion lists into rules.json.

usage: mine.py EXTRACT_DIR OUTDIR --psiminer PATH [--max-train-per-class N]
               [--seq-length 4] [--delay-res 1] [--depth 4] [--seed 1]
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import subprocess
import sys

DERIVED = ["t", "pkts", "ndst", "ndport", "syn_pct", "synack", "rst", "udp_pct",
           "icmp", "small_pct", "bpp", "anom", "hanom"]

# Predicate vocabulary: (name, PSIMiner predicate text, python test on a derived row).
# Thresholds are fixed before mining and are the same for every run.
PREDICATES = [
    ("ACTIVE",      "pkts>=1",        lambda r: r["pkts"] >= 1),
    ("PKTS_HI",     "pkts>=20",       lambda r: r["pkts"] >= 20),
    ("DST_MANY",    "ndst>=10",       lambda r: r["ndst"] >= 10),
    ("DST_VMANY",   "ndst>=100",      lambda r: r["ndst"] >= 100),
    ("DPORT_MANY",  "ndport>=10",     lambda r: r["ndport"] >= 10),
    ("DPORT_VMANY", "ndport>=100",    lambda r: r["ndport"] >= 100),
    ("SYN_DOM",     "syn_pct>=50",    lambda r: r["syn_pct"] >= 50),
    ("SYNACK",      "synack>=1",      lambda r: r["synack"] >= 1),
    ("RST",         "rst>=1",         lambda r: r["rst"] >= 1),
    ("UDP_DOM",     "udp_pct>=50",    lambda r: r["udp_pct"] >= 50),
    ("ICMP",        "icmp>=1",        lambda r: r["icmp"] >= 1),
    ("SMALL_DOM",   "small_pct>=80",  lambda r: r["small_pct"] >= 80),
    ("BPP_LARGE",   "bpp>=1000",      lambda r: r["bpp"] >= 1000),
    ("ANOM",        "anom>=1",        lambda r: r["anom"] >= 1),
    ("HANOM",       "hanom>=1",       lambda r: r["hanom"] >= 1),
]
# Target predicates. ANOM: the second contains a packet matched by a MAWILab
# 'anomalous' rule. HANOM: the host is a MAWILab-anomalous host and is active in
# that second (the host-level label propagated to its active seconds).
TARGETS = ("ANOM", "HANOM")
TARGET = "ANOM"


def stable_unit(name):
    return int(hashlib.sha1(name.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def derive(path, host_anomalous=False):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            p = int(r["pkts"])
            tcp = int(r["tcp"])
            rows.append({
                "t": int(r["t"]),
                "pkts": p,
                "ndst": int(r["ndst"]),
                "ndport": int(r["ndport"]),
                "syn_pct": round(100 * int(r["syn"]) / tcp) if tcp else 0,
                "synack": int(r["synack"]),
                "rst": int(r["rst"]),
                "udp_pct": round(100 * int(r["udp"]) / p) if p else 0,
                "icmp": int(r["icmp"]),
                "small_pct": round(100 * int(r["small"]) / p) if p else 0,
                "bpp": round(int(r["bytes"]) / p) if p else 0,
                "anom": int(r["anom"]),
                "hanom": 1 if host_anomalous and p >= 1 else 0,
            })
    return rows


def write_rows(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(DERIVED)
        for r in rows:
            w.writerow([r[c] for c in DERIVED])


def permute(rows, rng):
    """Joint-row permutation: shuffle the value rows, keep the time column."""
    vals = [{k: v for k, v in r.items() if k != "t"} for r in rows]
    rng.shuffle(vals)
    return [dict(t=r["t"], **v) for r, v in zip(rows, vals)]


def vocabulary(target, drop=()):
    """Predicates offered to the miner: all features except `drop`, plus the chosen target only."""
    return [p for p in PREDICATES if (p[0] not in TARGETS or p[0] == target) and p[0] not in drop]


def active_only(rows):
    """Event-indexed trace: keep the seconds with traffic and renumber t = 0, 1, ..."""
    return [dict(r, t=i) for i, r in enumerate(r for r in rows if r["pkts"] >= 1)]


def write_conf(path, trace_files, seq_length, delay_res, depth, target, learn_mode=0, drop=()):
    lines = [
        "seqLength=%d" % seq_length,
        "delayRes=%s" % delay_res,
        "traceCount=%d" % len(trace_files),
        "traceFile=" + ", ".join(trace_files),
        "bestPredCount=10",
        "tmin=1",
        "tmax=13",
        "learnMode=%d" % learn_mode,
        "strict=0",
        "objective=1",
        "useOverlap=1",
        "depth=%d" % depth,
        "",
        "start 2",
        "",
    ]
    for i, c in enumerate(DERIVED[1:], start=2):
        lines.append("%s %d 1" % (c, i))
    lines += ["", "begin", ""]
    vocab = vocabulary(target, drop)
    lines += [p[1] for p in vocab]
    lines += ["", "end", ""]
    for i, p in enumerate(vocab, start=1):
        lines.append("%s = (%d)" % (p[0], i))
    tgt = [p[0] for p in vocab].index(target) + 1
    lines += ["", "targets", "begin", "(%d)" % tgt, "end", ""]
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
RULE_RE = re.compile(r"^(.*?)\|=>\s*##\[\s*(" + NUM + r")\s*:\s*(" + NUM + r")\s*\]\s*(.+)$")


def parse_assertions(path):
    rules = []
    cur = None
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            m = RULE_RE.match(line)
            if m:
                cur = {"antecedent": m.group(1).strip(), "lo": float(m.group(2)),
                       "hi": float(m.group(3)), "consequent": m.group(4).strip()}
                rules.append(cur)
            elif line.startswith("SUPPORT") and cur is not None:
                cur["support"] = float(re.findall(NUM, line)[0])
            elif line.startswith("CORRELATION") and cur is not None:
                cur["correlation"] = float(re.findall(NUM, line)[0])
    return rules


def run_psiminer(binary, workdir, conf, bias=0):
    # PSIMiner writes <conf-stem>-assertions.txt next to the config; it is run from workdir.
    # bias is PSIMiner's explanation bias: +1 explains the true target, -1 the negated one, 0 both.
    cmd = [binary, conf] + ([str(bias)] if bias else [])
    with open(os.path.join(workdir, conf + ".log"), "w") as log:
        rc = subprocess.run(cmd, cwd=workdir, stdout=log, stderr=subprocess.STDOUT,
                            check=False).returncode
    if rc != 0:
        # a crash leaves a partial or empty assertion list; never read it as "no rules"
        print("PSIMiner exited with status %d in %s" % (rc, workdir), file=sys.stderr)
        return {"crashed": rc}
    stem = os.path.splitext(conf)[0]
    cand = os.path.join(workdir, stem + "-assertions.txt")
    return parse_assertions(cand) if os.path.exists(cand) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("extract_dir")
    ap.add_argument("outdir")
    ap.add_argument("--psiminer", required=True)
    ap.add_argument("--max-train-per-class", type=int, default=150)
    ap.add_argument("--seq-length", type=int, default=4)
    ap.add_argument("--delay-res", default="1")
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--target", default="ANOM", choices=TARGETS)
    ap.add_argument("--bias", type=int, default=0, choices=(-1, 0, 1),
                    help="PSIMiner explanation bias (+1 = explain the true target)")
    ap.add_argument("--learn-mode", type=int, default=0,
                    help="PSIMiner learnMode (0 = given predicates only; >0 also learns thresholds)")
    ap.add_argument("--active-only", action="store_true",
                    help="drop silent seconds from train and test traces (event-indexed time)")
    ap.add_argument("--drop", default="", help="comma-separated predicates left out of the vocabulary")
    ap.add_argument("--split-salt", default="", help="prefix hashed with the trace name; one salt per repeated split")
    ap.add_argument("--drop-constant", action="store_true",
                    help="leave out predicates that are constant over all train traces (works around the "
                         "PSIMiner ignorePredicate(j) off-by-one, which skips the predicate after a constant one)")
    a = ap.parse_args()

    hosts = list(csv.DictReader(open(os.path.join(a.extract_dir, "hosts.csv"))))
    tracedir = os.path.join(a.extract_dir, "traces")
    hosts = [h for h in hosts if os.path.exists(os.path.join(tracedir, h["trace"] + ".csv"))]
    for h in hosts:
        h["split"] = "train" if stable_unit(a.split_salt + h["trace"]) < 0.5 else "test"

    mdir = os.path.join(a.outdir, "mining")
    for sub in ("ordered", "permuted", "test"):
        os.makedirs(os.path.join(mdir, sub), exist_ok=True)
    rng = random.Random(a.seed)
    train = {"anomalous": [], "benign": []}
    seen = {p[0]: set() for p in PREDICATES}
    for h in sorted(hosts, key=lambda h: stable_unit(h["trace"] + "/order")):
        rows = derive(os.path.join(tracedir, h["trace"] + ".csv"), h["class"] == "anomalous")
        if a.active_only:
            rows = active_only(rows)
        if h["split"] == "test":
            write_rows(os.path.join(mdir, "test", h["trace"] + ".csv"), rows)
            continue
        if len(train[h["class"]]) >= a.max_train_per_class:
            h["split"] = "train-unused"
            continue
        train[h["class"]].append(h["trace"])
        for p in PREDICATES:
            if len(seen[p[0]]) < 2:
                seen[p[0]].update(p[2](r) for r in rows)
        write_rows(os.path.join(mdir, "ordered", h["trace"] + ".csv"), rows)
        write_rows(os.path.join(mdir, "permuted", h["trace"] + ".csv"), permute(rows, rng))

    drop = tuple(x for x in a.drop.split(",") if x)
    constant = [p[0] for p in PREDICATES if p[0] not in TARGETS and len(seen[p[0]]) < 2]
    if a.drop_constant:
        drop += tuple(c for c in constant if c not in drop)
    print("constant over train: %s; dropped: %s" % (",".join(constant) or "none", ",".join(drop) or "none"),
          file=sys.stderr)
    names = sorted(train["anomalous"] + train["benign"])
    files = [n + ".csv" for n in names]
    results = {}
    for sub in ("ordered", "permuted"):
        d = os.path.join(mdir, sub)
        if os.path.exists(a.psiminer):
            link = os.path.join(d, "psiMiner")
            if not os.path.exists(link):
                os.symlink(os.path.abspath(a.psiminer), link)
        write_conf(os.path.join(d, "hunt.conf"), files, a.seq_length, a.delay_res, a.depth, a.target,
                   a.learn_mode, drop)
        rules = run_psiminer("./psiMiner", d, "hunt.conf", a.bias)
        results[sub] = rules
        if isinstance(rules, dict):
            print("%s: PSIMiner CRASHED (exit %d), no rule set" % (sub, rules["crashed"]), file=sys.stderr)
            results[sub + "_crashed"] = rules["crashed"]
            rules = None
            results[sub] = None
        else:
            print("%s: %s rules" % (sub, "no" if rules is None else len(rules)), file=sys.stderr)

    with open(os.path.join(a.outdir, "split.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["trace", "class", "taxonomy", "split", "pkts"])
        for h in hosts:
            w.writerow([h["trace"], h["class"], h["taxonomy"], h["split"], h["pkts"]])
    json.dump({"params": vars(a), "train_counts": {k: len(v) for k, v in train.items()},
               "predicates": [[p[0], p[1]] for p in PREDICATES], "constant_train": constant,
               "dropped": list(drop), "rules": results},
              open(os.path.join(a.outdir, "rules.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
