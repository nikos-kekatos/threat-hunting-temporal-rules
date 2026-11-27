#!/usr/bin/env python3
"""Positive control: a synthetic extract directory in which only event order separates the classes.

Every host has a 60 s trace of low background traffic and K episodes, each made of one A second
(SYN-dominant, SYN_DOM) and one B second (many destination ports, DPORT_MANY), with the same packet
and byte counts. Anomalous hosts: A at t, B at t+GAP, ANOM set in the B second. Benign hosts: B at t,
A at t+GAP, no ANOM. Per-host aggregates (counts, maxima, means) have the same distribution in both
classes, so a tree on aggregates sits at chance and any rule that separates the classes must use
order. --noise adds the same rate of stray A and B seconds to every host. --gap-max G draws each
episode's gap uniformly from [gap, G] (default: fixed gap). --spacing S puts episode starts S seconds
apart (default G + 3); with S >= 2G + 3 no A of one episode is followed by the B of the next within G + 3 s,
so in benign hosts no A-then-B pair occurs at any delay up to G + 3 (red team 2026-10-20).

The output has the layout of mawi_extract.py (hosts.csv, traces/*.csv) and goes through the
unchanged mine.py and evaluate.py.

usage: synth_control.py OUTDIR [--hosts-per-class 300] [--episodes 3] [--gap 2] [--noise 0]
                               [--length 60] [--seed 1] [--gap-max G]
"""
import argparse
import csv
import os
import random

COLS = ["t", "pkts", "bytes", "ndst", "ndport", "syn", "synack", "rst", "fin", "tcp", "udp",
        "icmp", "small", "anom", "susp"]


def background(rng, t):
    p = rng.randint(2, 6)
    return dict(t=t, pkts=p, bytes=p * rng.randint(200, 600), ndst=1, ndport=1, syn=0, synack=0,
                rst=0, fin=0, tcp=p, udp=0, icmp=0, small=rng.randint(0, p), anom=0, susp=0)


def event(kind, t, anom):
    # A and B have the same packet and byte counts; they differ in SYN share and port count only.
    r = dict(t=t, pkts=12, bytes=12 * 60, ndst=1, ndport=1, syn=0, synack=0, rst=0, fin=0, tcp=12,
             udp=0, icmp=0, small=12, anom=1 if anom else 0, susp=0)
    if kind == "A":
        r["syn"] = 12
    else:
        r["ndport"] = 20
    return r


def host_trace(rng, positive, a):
    rows = {t: background(rng, t) for t in range(a.length)}
    gmax = max(a.gap, a.gap_max or a.gap)
    slots = list(range(1, a.length - gmax - 1, a.spacing or gmax + 3))
    for t in rng.sample(slots, a.episodes):
        g = rng.randint(a.gap, gmax) if gmax > a.gap else a.gap
        first, second = ("A", "B") if positive else ("B", "A")
        rows[t] = event(first, t, False)
        rows[t + g] = event(second, t + g, positive)
    if a.noise:
        busy = {t for t, r in rows.items() if r["pkts"] == 12}
        for t in range(a.length):
            if t not in busy and rng.random() < a.noise:
                rows[t] = event(rng.choice("AB"), t, False)
    return [rows[t] for t in sorted(rows)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--hosts-per-class", type=int, default=300)
    ap.add_argument("--episodes", type=int, default=3)
    ap.add_argument("--gap", type=int, default=2)
    ap.add_argument("--noise", type=float, default=0.0)
    ap.add_argument("--length", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--gap-max", type=int, default=0, help="draw each gap from [gap, gap-max]")
    ap.add_argument("--spacing", type=int, default=0, help="seconds between episode starts (default gap-max + 3)")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    td = os.path.join(a.outdir, "traces")
    os.makedirs(td, exist_ok=True)
    with open(os.path.join(a.outdir, "hosts.csv"), "w", newline="") as hf:
        hw = csv.writer(hf)
        hw.writerow(["trace", "class", "taxonomy", "pkts", "anom_pkts", "susp_pkts", "notice_pkts", "v6"])
        for i in range(2 * a.hosts_per_class):
            positive = i % 2 == 0
            name = "s%05d" % i
            rows = host_trace(rng, positive, a)
            with open(os.path.join(td, name + ".csv"), "w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(COLS)
                for r in rows:
                    w.writerow([r[c] for c in COLS])
            hw.writerow([name, "anomalous" if positive else "benign",
                         "AthenB" if positive else "benign", sum(r["pkts"] for r in rows),
                         sum(r["pkts"] for r in rows if r["anom"]), 0, 0, 0])


if __name__ == "__main__":
    main()
