#!/bin/bash
# usage: rig.sh <label> [pytest args...]   (run in WSL; host mode: own mock web + stage-4 + stage-3 containers)
# Builds stage-4 and stage-3 from `git archive HEAD`, serves the crafted corpus from gen_corpus.py.
set -e
L=$1; shift || true
REPO=/mnt/c/Users/IYANUOLUWA/band-work/result
W=$HOME/hack/$L
rm -rf $W; mkdir -p $W/src $W/corpus $W/control
(cd $REPO && git archive HEAD stage-1 stage-2 stage-3 stage-4) | tar -x -C $W/src
echo "revision: $(cd $REPO && git rev-parse HEAD)"
python3 $REPO/factory/stage-4/probes/custom/gen_corpus.py $W/corpus
H=$HOME/hack/sf-buildathon-2026
T=$H/challenges/dossier/test
mkdir -p $T/exam_s4c && cp $REPO/factory/stage-4/probes/custom/probe_custom.py $REPO/factory/stage-4/probes/conftest.py $T/exam_s4c/
NET=ex4net-$L; WEB=ex4web-$L; SVC=ex4svc-$L; PRV=ex4prv-$L; P1=ex4p1-$L; P2=ex4p2-$L
cleanup() { docker rm -f $WEB $SVC $PRV $P1 $P2 >/dev/null 2>&1 || true; docker network rm $NET >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup
docker build -q -t ex4-svc-$L $W/src/stage-4 >/dev/null
docker build -q -t ex4-prv-$L $W/src/stage-3 >/dev/null
docker build -q -t ex4-p1-$L $W/src/stage-1 >/dev/null
docker build -q -t ex4-p2-$L $W/src/stage-2 >/dev/null
docker network create $NET >/dev/null
port() { python3 -c 'import random;print(random.randint(20000,39000))'; }
PW=$(port); PS=$(port); PP=$(port); Q1=$(port); Q2=$(port)
docker run -d --name $WEB --network $NET -e MOCK_ADMIN_TOKEN=tok -v $W/corpus:/data/corpus:ro -p 127.0.0.1:$PW:8080 df-dossier-mockweb >/dev/null
envs() { for p in nimble tavily kernel browserbase; do U=$(echo $p | tr a-z A-Z); echo -e "-e ${U}_API_KEY=mock-$p -e ${U}_BASE_URL=http://$WEB:8080/$p"; done | tr '\n' ' '; }
docker run -d --name $SVC --network $NET -e PORT=8000 $(envs) -p 127.0.0.1:$PS:8000 ex4-svc-$L >/dev/null
docker run -d --name $PRV --network $NET -e PORT=8000 $(envs) -p 127.0.0.1:$PP:8000 ex4-prv-$L >/dev/null
docker run -d --name $P1 --network $NET -e PORT=8000 $(envs) -p 127.0.0.1:$Q1:8000 ex4-p1-$L >/dev/null
docker run -d --name $P2 --network $NET -e PORT=8000 $(envs) -p 127.0.0.1:$Q2:8000 ex4-p2-$L >/dev/null
for u in $PS $PP $Q1 $Q2; do for i in $(seq 1 60); do curl -sf http://127.0.0.1:$u/health >/dev/null && break; sleep 1; done; done
for i in $(seq 1 30); do curl -sf http://127.0.0.1:$PW/_mock/health >/dev/null && break; sleep 1; done
cd $H && . .venv/bin/activate
python -m pytest $T/exam_s4c/probe_custom.py --base-url http://127.0.0.1:$PS -p harness.plugin --rootdir $T -q \
  --web-url http://127.0.0.1:$PW --web-admin-token tok --web-corpus $W/corpus --control-dir $W/control \
  --previous-base-url http://127.0.0.1:$PP --implementation-stage 4 "$@" 2>&1 | tail -150
for q in $Q1 $Q2; do
python -m pytest $T/exam_s4c/probe_custom.py --base-url http://127.0.0.1:$PS -p harness.plugin --rootdir $T -q -k m03   --web-url http://127.0.0.1:$PW --web-admin-token tok --web-corpus $W/corpus --control-dir $W/control   --previous-base-url http://127.0.0.1:$q --implementation-stage 4 2>&1 | tail -30 | sed "s/^/[prev:$q] /"
done
