#!/bin/bash
# usage: run.sh <label> [host|isolated] [extra pytest args]  (stage 4; run after a revision is sent)
set -e
L=$1; MODE=${2:-host}; shift 2 || true
REPO=/mnt/c/Users/IYANUOLUWA/band-work/result
SRC=$HOME/hack/$L
rm -rf $SRC; mkdir -p $SRC
(cd $REPO && git archive HEAD stage-3 stage-4) | tar -x -C $SRC
H=$HOME/hack/sf-buildathon-2026
T=$H/challenges/dossier/test
mkdir -p $T/exam_s4 && cp $REPO/factory/stage-4/probes/*.py $T/exam_s4/
cd $H && . .venv/bin/activate
TP=$T
if [ "$MODE" = isolated ]; then TP=/work/challenges/dossier/test; export SHOTS=/out/shots; else export SHOTS=$REPO/factory/stage-4/screens; fi
FILES=$(cd $T/exam_s4 && ls probe_*.py | sed "s#^#$TP/exam_s4/#")
rm -rf $HOME/hack/checks/$L
timeout 3400 python -m harness run --track dossier --build $SRC/stage-4 --previous-build $SRC/stage-3 \
  --implementation-stage 4 --stages 4 --mode $MODE --out $HOME/hack/checks/$L $FILES "$@" 2>&1 | tail -60
