#!/bin/bash
# Segmented download of one MAWI trace (the server limits each connection to ~130 KB/s).
# usage: fetch_parallel.sh URL OUTFILE SIZE_BYTES [NPARTS]
set -u
URL=$1; OUT=$2; SIZE=$3; N=${4:-32}
PARTS=$OUT.parts; mkdir -p "$PARTS"
CHUNK=$(( (SIZE + N - 1) / N ))
for i in $(seq 0 $((N-1))); do
  s=$((i*CHUNK)); e=$((s+CHUNK-1)); [ $e -ge $SIZE ] && e=$((SIZE-1))
  ( until [ -f "$PARTS/p$i" ] && [ $(stat -f %z "$PARTS/p$i") -eq $((e-s+1)) ]; do
      have=0; [ -f "$PARTS/p$i" ] && have=$(stat -f %z "$PARTS/p$i")
      curl -s --retry 5 -r $((s+have))-$e "$URL" >> "$PARTS/p$i" || /bin/sleep 5
    done ) &
done
wait
for i in $(seq 0 $((N-1))); do cat "$PARTS/p$i"; done > "$OUT"
[ $(stat -f %z "$OUT") -eq $SIZE ] && gzip -t "$OUT" && echo "OK $OUT" && rm -r "$PARTS"
