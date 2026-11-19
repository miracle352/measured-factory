# Measured Factory

**What it built:** Dossier, a company research service. Give it a company's domain and it
researches the web under a fixed budget and writes a dossier: legal name, headquarters,
CEO, year founded, headcount, total funding, executives and investors. Every value comes
with the pages that support it. When sources disagree it marks the field contested and
shows every candidate instead of quietly picking one. It keeps each value's history, so you
can ask what was true on a given date, and it researches whole batches of companies under
one shared budget.

**How it was built:** four Claude seats in Band Desktop built the Dossier track, all four stages, from the spec
alone. No human wrote or edited product code. I sent seven messages in total: four to
start a stage, two when seats went quiet, one after the Claude usage limit paused the band.

The factory is built around one fact about this buildathon: most of the graded tests are
hidden (only 57%, 6%, 4% and 8% of the tests for stages 1-4 ship). Passing the shipped
checks proves little. So the factory writes its own tests from the spec, with a seat that
never sees the builders' code, and measures cost before it chooses how to spend it.

**Demo video (3 min):** on the HackerSquad submission page.

## Results

| Stage | Dispatch to accepted | Ledger rows | Rows the examiner added | Product defects caught by the examiner | Max spend per build |
|---|---|---|---|---|---|
| 1 | 28 min | 73 | 2 | 0 | 47 of 80 units |
| 2 | 32 min | 70 | 11 | 1 | 72 of 80 |
| 3 | 76 min | 73 | 3 | 0 | 72 of 80 |
| 4 | 60 min + 11 min after a 7 h usage-limit pause | 65 | 5 | 3 | capped at 80 |

- Final isolated check: supplied checks for stages 1-4 pass, `claimed stage: 4`.
- Examiner's own probes at the final revision: 50 of 50, plus 16 of 16 on a corpus it built itself.
- 802 tool calls and 115 messages across the four rooms. 83 commits, every one by a seat
  (builder-a 28, builder-b 19, coordinator 18, examiner 18). My 6 commits only add room
  logs, setup and the live runs.

## Benchmarks

### 1. Shipped checks vs the examiner

At revision `4695fb1` the supplied checks for stages 1-4 all passed. The same build was
broken: a crafted company with many canonical originals made one build bill **92 units
against the 80-unit cap**, while the dossier reported 80. The examiner's spec-only probe
`test_l01_origins_originals_and_hops` failed it (room 4, 18:05). builder-a found the cause
(an extract answered with an in-band 404 is billed, but was treated as a free refusal and
retried) and fixed it in `32129f9`. The examiner accepted at `3a05d10`.

The examiner caught four product defects across the run:

| Stage | Defect | Fix |
|---|---|---|
| 2 | a contested item on screen without its field identifier | `85638d8` |
| 4 | a restart mid-build billed 204 units against a 150-unit batch budget | `00d4835` |
| 4 | one build billed 92 units against the 80 cap | `32129f9` |
| 4 | screen wording: a self-contradicting corroboration line, a raw field key on /contested | `d7ff845` |

### 2. Cost per correct fact

Before writing the build, builder-a measured four ways to gather facts on the test corpus
(12 company/epoch runs each, raw numbers in `factory/stage-1/measure-raw.md`):

| Strategy | Units | Correct | Missed | Units per correct |
|---|---|---|---|---|
| **A** lite search + extract + research + follow-ups (chosen) | 511 | 70 | 0 | **7.30** |
| B deep search + research | 690 | 70 | 0 | 9.86 |
| C lite search + extract, no research | 208 | 62 | 8 | 3.35 |
| D fast search + research, no extract | 360 | 46 | 24 | 7.83 |

C is cheaper but misses fields that only research reaches. In stage 2 the same method
compared rendered and plain extracts (12.97 vs 7.84 units per correct); rendered was kept
because the spec defines page text as browser text.

### 3. The live web, through Nimble

Stage 4 built against the real web with my Nimble key, on companies nobody prepared for
(`live-runs/`, `dossier-runway.com.json`):

| Company | Spent | Known | Contested | Unknown |
|---|---|---|---|---|
| linear.app | 78 / 80 | 2 | 3 | 1 |
| vercel.com | 79 / 80 | 2 | 2 | 2 |
| supabase.com | 80 / 80 | 2 | 2 | 2 |
| runway.com | 80 / 80 | 0 | 0 | 6 |

Every build stayed inside 80 units. Where sources agree the field is `known` with its
citations; where they disagree it is `contested` and every candidate is shown with its
source. runway.com spent its budget and got no candidate value for any field, so the
dossier says `unknown` rather than guessing. Contested is not always right: linear.app's
selected CEO is wrong, and the other candidates are on the same screen.

## How it works

Full write-up in [`FACTORY.md`](FACTORY.md). In short:

1. **Ledger first.** The coordinator turns the spec into numbered rows, one per testable
   statement, including what the shipped checks never test.
2. **A blind second reading.** The examiner reads the spec alone and writes its own list.
   Anything the ledger missed becomes work (21 rows over four stages).
3. **Small numbered work items.** At most 8 ledger rows per commit, every commit message
   starts with its row IDs, so any line of code traces to a requirement.
4. **Review as items land.** Probes come from the spec text only, and a failure is
   reproduced twice before a builder hears about it.
5. **Measure what costs money** before choosing a strategy.
6. **Close.** Isolated check, screenshots at 375 px and 1280 px, one verdict, rulings
   recorded so later stages never re-decide a question.

### BAND's four signals

- **A dependent handoff:** a builder's item goes to the examiner; the examiner's verdict
  goes back through the coordinator to the owning builder; the fix goes back to the examiner.
- **A roster decided at runtime:** the coordinator splits each stage into work items and
  assigns them to builders from the ledger, so the split is different every stage.
- **A boundary:** every seat runs as its own agent with its own context; the examiner works
  from the spec and its probes, never from the builders' reasoning.
- **A verdict that can be blocked:** in stages 2 and 4 the examiner's CHANGES NEEDED held
  acceptance until the fix was re-checked.

## The seven human messages

| Time (Lagos) | Message | Why |
|---|---|---|
| 18 Nov 01:10 | dispatch stage 1 | start |
| 08:39 | dispatch stage 2 | start |
| 12:03 | dispatch stage 3 | start |
| 12:29 | "no seat has posted since 12:16" | a seat ended its turn while promising more work |
| 13:02 | "no seat has posted since 12:32" | the same, plus a wait loop that matched its own command |
| 17:05 | dispatch stage 4 | start; the stage-3 stalls became two rules in this dispatch |
| 19 Nov 01:03 | resume | the Claude usage limit stopped every seat at 18:05 |

The two rules added after stage 3: "Run every check in the foreground and wait for it to
finish before ending your turn" and "Your turn ends when you send a message". Stage 4 had
no stall.

## Reading this repository

| Path | What it is |
|---|---|
| `FACTORY.md` | the factory: seats, setup, results, costs, what failed |
| `mandates/` | the four seat mandates; they say nothing about this track |
| `room-1.json` ... `room-4.json` | each stage's room, downloaded from Band unchanged |
| `stage-1/` ... `stage-4/` | one complete, buildable service per stage (Dockerfile, RUN.md, source) |
| `factory/` | ledgers, examiner lists, probes, screenshots, measurements, rulings |
| `live-runs/`, `dossier-runway.com.json` | builds against the live web through Nimble |

Each `stage-N/RUN.md` has the command that builds and starts that stage.
