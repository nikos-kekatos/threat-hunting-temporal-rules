#!/usr/bin/env python3
"""Compile a mined antecedent into a SQL hunt query over a per-second table.

Table schema assumed: bins(host, t, pkts, ndst, ndport, syn_pct, synack, rst,
udp_pct, icmp, small_pct, bpp), one row per host and second (the columns of
mine.DERIVED without the label). A sequence 'A ##[lo:hi] B' becomes a self-join
on host with b.t - a.t BETWEEN lo AND hi. The query returns the hosts to inspect.

usage: compile_query.py "DST_MANY && SYN_DOM ##[0:1] !SYNACK"
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mine import PREDICATES  # noqa: E402
from evaluate import parse_antecedent  # noqa: E402

SQL_COND = {name: text for name, text, _ in PREDICATES}


def literal_sql(lit, alias):
    neg = lit.startswith("!")
    name = lit.lstrip("!").strip()
    col, op_val = SQL_COND[name].split(">=") if ">=" in SQL_COND[name] else (None, None)
    cond = "%s.%s >= %s" % (alias, col.strip(), op_val.strip())
    return "NOT (%s)" % cond if neg else cond


def compile_sql(antecedent):
    conjs, gaps = parse_antecedent(antecedent)
    aliases = ["s%d" % i for i in range(len(conjs))]
    where = []
    for conj, al in zip(conjs, aliases):
        for lit in [x.strip() for x in conj.split("&&") if x.strip()]:
            where.append(literal_sql(lit, al))
    for i, (lo, hi) in enumerate(gaps):
        a, b = aliases[i], aliases[i + 1]
        lo_k, hi_k = int(math.ceil(lo - 1e-9)), int(math.floor(hi + 1e-9))
        where.append("%s.host = %s.host" % (b, a))
        where.append("%s.t - %s.t BETWEEN %d AND %d" % (b, a, lo_k, hi_k))
    frm = ", ".join("bins %s" % al for al in aliases)
    return "SELECT DISTINCT s0.host\nFROM %s\nWHERE %s;" % (frm, "\n  AND ".join(where))


if __name__ == "__main__":
    print(compile_sql(sys.argv[1]))
