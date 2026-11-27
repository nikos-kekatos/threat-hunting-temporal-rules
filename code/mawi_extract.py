#!/usr/bin/env python3
"""Per-host, per-second feature traces from a MAWI pcap.gz labelled by MAWILab.

Pass 1 streams the trace once, matches every packet against the MAWILab rules
(anomalous, suspicious, notice) and counts packets per source address.
Host selection then takes every source with enough packets matched by
'anomalous' rules, plus volume-matched benign sources (no packet matched by any
MAWILab rule, including 'notice'). Pass 2 streams the trace again and writes one
CSV per selected host with one row per one-second bin.

Standard library only, so it runs without a virtualenv.

usage:
  mawi_extract.py PCAP_GZ LABELS_CSV NOTICE_CSV OUTDIR [--max-packets N]
                  [--min-pkts 50] [--min-anom-frac 0.2] [--benign-per-anom 3]
"""
import argparse
import collections
import csv
import gzip
import hashlib
import io
import json
import math
import os
import socket
import struct
import sys
import time

COLUMNS = ["t", "pkts", "bytes", "ndst", "ndport", "syn", "synack", "rst", "fin",
           "tcp", "udp", "icmp", "small", "anom", "susp"]


def ip_bytes(s):
    s = s.strip()
    if not s:
        return None
    fam = socket.AF_INET6 if ":" in s else socket.AF_INET
    return socket.inet_pton(fam, s)


def load_rules(path, default_label=None, first=1):
    """MAWILab CSV rows -> list of (src, sport, dst, dport, taxonomy, label).

    The header lists anomalyID first, but in the v1.1 files the data rows of
    *_anomalous_suspicious.csv start with anomalyID (first=1) while the rows of
    *_notice.csv start with srcIP (first=0). Fields used positionally: srcIP,
    srcPort, dstIP, dstPort, taxonomy from `first`, label last. Empty fields
    are wildcards.
    """
    rules = []
    with open(path) as fh:
        rd = csv.reader(fh)
        next(rd)
        for row in rd:
            if len(row) < first + 5:
                continue
            src, sport, dst, dport, tax = row[first:first + 5]
            label = row[-1].strip() if default_label is None else default_label
            rules.append((ip_bytes(src), int(sport) if sport.strip() else None,
                          ip_bytes(dst), int(dport) if dport.strip() else None,
                          tax.strip(), label))
    return rules


class Matcher:
    def __init__(self, rules):
        self.by_src = collections.defaultdict(list)
        self.by_dst = collections.defaultdict(list)
        self.wild = []
        for r in rules:
            if r[0] is not None:
                self.by_src[r[0]].append(r)
            elif r[2] is not None:
                self.by_dst[r[2]].append(r)
            else:
                self.wild.append(r)

    def match(self, src, sport, dst, dport):
        """Return the set of labels of all rules that match this packet."""
        out = None
        for cand in (self.by_src.get(src), self.by_dst.get(dst), self.wild):
            if not cand:
                continue
            for (rs, rsp, rd, rdp, tax, lab) in cand:
                if rs is not None and rs != src:
                    continue
                if rd is not None and rd != dst:
                    continue
                if rsp is not None and rsp != sport:
                    continue
                if rdp is not None and rdp != dport:
                    continue
                if out is None:
                    out = {}
                out[lab] = tax
        return out


def packets(path, max_packets=None):
    """Yield (ts, src, dst, proto, sport, dport, flags, iplen) for IPv4/IPv6."""
    raw = gzip.open(path, "rb")
    f = io.BufferedReader(raw, buffer_size=1 << 22)
    gh = f.read(24)
    magic = struct.unpack("<I", gh[:4])[0]
    if magic == 0xa1b2c3d4:
        endian, nano = "<", False
    elif magic == 0xd4c3b2a1:
        endian, nano = ">", False
    elif magic == 0xa1b23c4d:
        endian, nano = "<", True
    else:
        raise SystemExit("unsupported pcap magic %x" % magic)
    linktype = struct.unpack(endian + "I", gh[20:24])[0]
    if linktype != 1:
        raise SystemExit("expected Ethernet linktype 1, got %d" % linktype)
    rec = struct.Struct(endian + "IIII")
    div = 1e9 if nano else 1e6
    n = 0
    read = f.read
    while True:
        try:
            ph = read(16)
            if len(ph) < 16:
                break
            ts, tf, incl, _orig = rec.unpack(ph)
            d = read(incl)
        except EOFError:
            # truncated gzip (a partial download used for testing): stop cleanly
            print("warning: truncated gzip after %d packets" % n, file=sys.stderr)
            break
        if len(d) < incl:
            break
        n += 1
        if max_packets and n > max_packets:
            break
        off = 14
        et = d[12:14]
        while et == b"\x81\x00" or et == b"\x88\xa8":
            et = d[off + 2:off + 4]
            off += 4
        if et == b"\x08\x00":
            if len(d) < off + 20:
                continue
            ihl = (d[off] & 0x0F) * 4
            iplen = (d[off + 2] << 8) | d[off + 3]
            frag = ((d[off + 6] & 0x1F) << 8) | d[off + 7]
            proto = d[off + 9]
            src = d[off + 12:off + 16]
            dst = d[off + 16:off + 20]
            l4 = off + ihl
            if frag:
                proto = -1
        elif et == b"\x86\xdd":
            if len(d) < off + 40:
                continue
            iplen = ((d[off + 4] << 8) | d[off + 5]) + 40
            proto = d[off + 6]
            src = d[off + 8:off + 24]
            dst = d[off + 24:off + 40]
            l4 = off + 40
        else:
            continue
        sport = dport = None
        flags = 0
        if proto == 6 or proto == 17:
            if len(d) >= l4 + 4:
                sport = (d[l4] << 8) | d[l4 + 1]
                dport = (d[l4 + 2] << 8) | d[l4 + 3]
            if proto == 6 and len(d) >= l4 + 14:
                flags = d[l4 + 13]
        yield ts + tf / div, src, dst, proto, sport, dport, flags, iplen
    raw.close()


def pass1(path, matcher, max_packets):
    stats = {}  # src -> [pkts, anom, susp, notice]
    tax = collections.defaultdict(collections.Counter)  # src -> taxonomy counts (anomalous)
    totals = collections.Counter()
    t0 = time.time()
    first_ts = last_ts = None
    for i, (ts, src, dst, proto, sport, dport, flags, iplen) in enumerate(packets(path, max_packets)):
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        s = stats.get(src)
        if s is None:
            s = stats[src] = [0, 0, 0, 0]
        s[0] += 1
        totals["packets"] += 1
        totals["v6" if len(src) == 16 else "v4"] += 1
        m = matcher.match(src, sport, dst, dport)
        if m:
            if "anomalous" in m:
                s[1] += 1
                tax[src][m["anomalous"]] += 1
                totals["anomalous"] += 1
            if "suspicious" in m:
                s[2] += 1
                totals["suspicious"] += 1
            if "notice" in m:
                s[3] += 1
                totals["notice"] += 1
        if i and i % 5_000_000 == 0:
            print("pass1 %d packets, %.0f s" % (i, time.time() - t0), file=sys.stderr, flush=True)
    totals["sources"] = len(stats)
    totals["duration_s"] = round((last_ts or 0) - (first_ts or 0), 3)
    return stats, tax, totals, first_ts


def stable_hash(b):
    return int.from_bytes(hashlib.sha1(b).digest()[:8], "big")


def select_hosts(stats, tax, min_pkts, min_anom_frac, benign_per_anom):
    anom = {}
    for src, (p, a, su, no) in stats.items():
        if p >= min_pkts and a / p >= min_anom_frac:
            anom[src] = tax[src].most_common(1)[0][0]
    # benign pool by log2 volume bin, deterministic order by hash
    pool = collections.defaultdict(list)
    for src, (p, a, su, no) in stats.items():
        if p >= min_pkts and a == 0 and su == 0 and no == 0:
            pool[int(math.log2(p))].append(src)
    for b in pool:
        pool[b].sort(key=stable_hash)
    used = collections.Counter()
    benign = {}
    for src in sorted(anom, key=stable_hash):
        b = int(math.log2(stats[src][0]))
        for _ in range(benign_per_anom):
            # nearest non-empty volume bin
            for delta in (0, -1, 1, -2, 2):
                lst = pool.get(b + delta, [])
                if used[b + delta] < len(lst):
                    benign[lst[used[b + delta]]] = "benign"
                    used[b + delta] += 1
                    break
    return anom, benign


def pass2(path, matcher, hosts, outdir, max_packets, t_origin):
    """Accumulate one-second bins for the selected hosts, then write CSVs."""
    bins = {h: {} for h in hosts}
    for (ts, src, dst, proto, sport, dport, flags, iplen) in packets(path, max_packets):
        hb = bins.get(src)
        if hb is None:
            continue
        k = int(ts - t_origin)
        b = hb.get(k)
        if b is None:
            b = hb[k] = [0, 0, set(), set(), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        b[0] += 1
        b[1] += iplen
        b[2].add(dst)
        if dport is not None:
            b[3].add(dport)
        if proto == 6:
            b[8] += 1
            if flags & 0x02 and not flags & 0x10:
                b[4] += 1
            elif flags & 0x02:
                b[5] += 1
            if flags & 0x04:
                b[6] += 1
            if flags & 0x01:
                b[7] += 1
        elif proto == 17:
            b[9] += 1
        elif proto == 1 or proto == 58:
            b[10] += 1
        if iplen <= 60:
            b[11] += 1
        m = matcher.match(src, sport, dst, dport)
        if m:
            if "anomalous" in m:
                b[12] += 1
            if "suspicious" in m:
                b[13] += 1
    os.makedirs(outdir, exist_ok=True)
    names = {}
    for h, hb in bins.items():
        name = "h" + hashlib.sha1(h).hexdigest()[:10]
        names[h] = name
        if not hb:
            continue
        lo, hi = min(hb), max(hb)
        with open(os.path.join(outdir, name + ".csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            for k in range(lo, hi + 1):
                b = hb.get(k)
                if b is None:
                    w.writerow([k] + [0] * (len(COLUMNS) - 1))
                else:
                    w.writerow([k, b[0], b[1], len(b[2]), len(b[3])] + b[4:14])
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("labels")
    ap.add_argument("notice")
    ap.add_argument("outdir")
    ap.add_argument("--max-packets", type=int, default=None)
    ap.add_argument("--min-pkts", type=int, default=50)
    ap.add_argument("--min-anom-frac", type=float, default=0.2)
    ap.add_argument("--benign-per-anom", type=int, default=3)
    a = ap.parse_args()

    rules = load_rules(a.labels) + load_rules(a.notice, default_label="notice", first=0)
    # Rules with no IP address (port-only, e.g. "all traffic from port 443") describe
    # traffic-wide shifts, not hosts; they would mark every HTTPS host anomalous and
    # empty the benign pool of HTTPS hosts. They are dropped and counted.
    ipless = [r for r in rules if r[0] is None and r[2] is None]
    rules = [r for r in rules if not (r[0] is None and r[2] is None)]
    matcher = Matcher(rules)
    stats, tax, totals, t_origin = pass1(a.pcap, matcher, a.max_packets)
    anom, benign = select_hosts(stats, tax, a.min_pkts, a.min_anom_frac, a.benign_per_anom)
    hosts = dict(anom)
    hosts.update(benign)
    names = pass2(a.pcap, matcher, hosts, os.path.join(a.outdir, "traces"), a.max_packets, t_origin)

    with open(os.path.join(a.outdir, "hosts.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["trace", "class", "taxonomy", "pkts", "anom_pkts", "susp_pkts", "notice_pkts", "v6"])
        for h, cls in sorted(hosts.items(), key=lambda kv: names[kv[0]]):
            p, an, su, no = stats[h]
            w.writerow([names[h], "anomalous" if h in anom else "benign", cls, p, an, su, no,
                        int(len(h) == 16)])
    totals["rules"] = len(rules)
    totals["rules_dropped_ipless"] = [list(map(str, r[1:])) for r in ipless]
    totals["hosts_anomalous"] = len(anom)
    totals["hosts_benign"] = len(benign)
    totals["params"] = {"min_pkts": a.min_pkts, "min_anom_frac": a.min_anom_frac,
                        "benign_per_anom": a.benign_per_anom, "max_packets": a.max_packets}
    with open(os.path.join(a.outdir, "summary.json"), "w") as fh:
        json.dump(totals, fh, indent=1, default=str)
    print(json.dumps(totals, indent=1, default=str))


if __name__ == "__main__":
    main()
