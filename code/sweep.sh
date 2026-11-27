#!/bin/bash
# Mining-configuration sweep on split s0. usage: sweep.sh "TARGET DEPTH SEQ LEARN MAXTRAIN BIAS [extra mine.py args]" ...
HERE=$(cd "$(dirname "$0")" && pwd); R=$HERE/../results/sweep; mkdir -p "$R"
PSI=${PSIMINER:-psiMiner}
for cfg in "$@"; do
  read -r tg d n lm mt b extra <<< "$cfg"; lm=${lm:-0}; mt=${mt:-150}; b=${b:-0}
  name=${tg}_d${d}_n${n}_l${lm}_m${mt}_b${b}$(echo "$extra" | tr -d ' -' | tr ',=' '__')
  ( /usr/bin/time -p "$HERE/.venv/bin/python" "$HERE/mine.py" "$HERE/../results/extract" "$R/$name" \
      --psiminer "$PSI" --split-salt s0 --target "$tg" --depth "$d" --seq-length "$n" --learn-mode "$lm" --max-train-per-class "$mt" --bias "$b" $extra > "$R/$name.log" 2>&1 ) &
done
wait
for cfg in "$@"; do
  read -r tg d n lm mt b extra <<< "$cfg"; lm=${lm:-0}; mt=${mt:-150}; b=${b:-0}; name=${tg}_d${d}_n${n}_l${lm}_m${mt}_b${b}$(echo "$extra" | tr -d ' -' | tr ',=' '__')
  "$HERE/.venv/bin/python" -c "
import json; m=json.load(open('$R/$name/rules.json'))
print('$name', {k: len(v or []) for k, v in m['rules'].items()})
for r in (m['rules']['ordered'] or []): print('   ', r['antecedent'], '=>', r['consequent'], r.get('support'), r.get('correlation'))"
  grep real "$R/$name.log"
done
