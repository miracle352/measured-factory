#!/bin/bash
# usage: run.sh <label> [host|isolated] [extra pytest args]   (run only after the coordinator sends a revision)
set -e
L=$1; MODE=${2:-host}; shift 2 || true
REPO=/mnt/c/Users/IYANUOLUWA/band-work/result
SRC=$HOME/hack/$L
rm -rf $SRC; mkdir -p $SRC
(cd $REPO && git archive HEAD stage-1 stage-2 stage-3) | tar -x -C $SRC
H=$HOME/hack/sf-buildathon-2026
T=$H/challenges/dossier/test
mkdir -p $T/exam_s3 && cp $REPO/factory/stage-3/probes/{conftest.py,probe_api.py,probe_ui.py} $T/exam_s3/
cd $H && . .venv/bin/activate
TP=$T
if [ "$MODE" = isolated ]; then TP=/work/challenges/dossier/test; export SHOTS=/out/shots; else export SHOTS=$REPO/factory/stage-3/screens; fi
rm -rf $HOME/hack/checks/$L
timeout 3400 python -m harness run --track dossier --build $SRC/stage-3 --previous-build $SRC/${PREV:-stage-2} \
  --implementation-stage 3 --stages 3 --mode $MODE --out $HOME/hack/checks/$L \
  $TP/exam_s3/probe_api.py $TP/exam_s3/probe_ui.py "$@" 2>&1 | tail -20
if [ "$MODE" = isolated ] && [ -d $HOME/hack/checks/$L/shots ]; then mkdir -p $REPO/factory/stage-3/screens; cp $HOME/hack/checks/$L/shots/*.png $REPO/factory/stage-3/screens/; fi
