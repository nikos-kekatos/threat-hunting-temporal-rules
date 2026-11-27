"""Event-level precision for Table IV (review 2026-10-27, option B): from the pooled counts of
results_review_2026-10-21/SUMMARY.md (G=8 rows of both event-level sections), precision over B seconds =
matched episodes / (matched episodes + matched benign B seconds), with Wilson 95% intervals.
Output: results_stats_2026-10-27/event_precision.json"""
import json, math, os, re
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
def wilson(k, n, z=1.959964):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 4), round((c + h) / d, 4)]
out, sec = {}, None
for line in open(os.path.join(ROOT, "results_review_2026-10-21/SUMMARY.md")):
    if line.startswith("## Event-level recall"):
        sec = "three" if "three" in line else "one"
    m = re.match(r"\| 8 \| (\S+) \| (\S+) \|.*\| (\d+)/(\d+) \| (\d+)/(\d+) \|", line)
    if sec and m:
        meth, L, k, n, b, nb = m.group(1), m.group(2), *map(int, m.groups()[2:])
        out[f"{sec}|{meth}|L{L}"] = {"matched": k, "episodes": n, "benign_matched": b, "benign": nb,
            "event_precision": round(k / (k + b), 4) if k + b else None,
            "event_precision_ci": wilson(k, k + b) if k + b else None,
            "benign_rate": round(b / nb, 4)}
json.dump(out, open(os.path.join(ROOT, "results_stats_2026-10-27/event_precision.json"), "w"), indent=1)
for k, v in out.items(): print(k, v["event_precision"], v["event_precision_ci"], v["benign_rate"])
