#!/bin/bash
# Full ch8 experiment. Outputs in ../results/. Each stage logs to ../results/*.log.
#   extract (day 1 = 2024-11-19, day 2 = 2024-06-23 if present)
#   mine + evaluate for five split salts (main split = salt "s0")
#   SQL compilation check and portability on the main split, then aggregate.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
M=${MAWI_DIR:-data/mawi/2024}
PSI=${PSIMINER:-psiMiner}
R=$HERE/../results
PY=$HERE/.venv/bin/python
mkdir -p "$R"
if [ ! -f "$R/extract/summary.json" ]; then
  $PY "$HERE/mawi_extract.py" "$M/202411191400.pcap.gz" "$M/20241119_anomalous_suspicious.csv" \
      "$M/20241119_notice.csv" "$R/extract" > "$R/extract.out" 2> "$R/extract.log"
fi
for salt in s0 s1 s2 s3 s4; do
  if [ ! -f "$R/mine_$salt/results/hunt_eval.json" ]; then
    $PY "$HERE/mine.py" "$R/extract" "$R/mine_$salt" --psiminer "$PSI" --split-salt "$salt" 2> "$R/mine_$salt.log"
    $PY "$HERE/evaluate.py" "$R/mine_$salt" > "$R/eval_$salt.txt"
  fi
done
$PY "$HERE/verify_sql.py" "$R/mine_s0" "$R/sql_check.json"
if [ -f "$M/202406231400.pcap.gz" ]; then
  if [ ! -f "$R/extract_day2/summary.json" ]; then
    $PY "$HERE/mawi_extract.py" "$M/202406231400.pcap.gz" "$M/20240623_anomalous_suspicious.csv" \
        "$M/20240623_notice.csv" "$R/extract_day2" > "$R/extract_day2.out" 2> "$R/extract_day2.log"
  fi
  $PY "$HERE/portability.py" "$R/mine_s0" "$R/extract_day2" "$R/portability.json"
fi
$PY "$HERE/aggregate.py" "$R"
