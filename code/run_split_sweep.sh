#!/bin/bash
# Rerun mine + evaluate on all five split salts with one mining configuration, into its own
# results root (default results run untouched). Then SQL check, portability, aggregate.
#   usage: run_split_sweep.sh NAME [mine.py args...]
#   e.g.   run_split_sweep.sh b1 --bias 1
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
PSI=${PSIMINER:-psiMiner}
NAME=$1; shift
R=$HERE/../results_$NAME
PY=$HERE/.venv/bin/python
mkdir -p "$R"
for ex in extract extract_day2; do [ -e "$R/$ex" ] || ln -s ../results/$ex "$R/$ex"; done
for salt in s0 s1 s2 s3 s4; do
  ( $PY "$HERE/mine.py" "$R/extract" "$R/mine_$salt" --psiminer "$PSI" --split-salt "$salt" "$@" 2> "$R/mine_$salt.log" \
    && $PY "$HERE/evaluate.py" "$R/mine_$salt" > "$R/eval_$salt.txt" ) &
done
wait
$PY "$HERE/verify_sql.py" "$R/mine_s0" "$R/sql_check.json"
$PY "$HERE/portability.py" "$R/mine_s0" "$R/extract_day2" "$R/portability.json"
$PY "$HERE/aggregate.py" "$R"
echo "$@" > "$R/CONFIG.txt"
