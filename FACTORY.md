# Factory

Four coding-agent seats in Band Desktop build the track one stage at a time, with no
human input between dispatches. I send one message per stage; the seats plan, build,
review and accept the work themselves. Everything they decide is in the room logs
(`room-1.json` and on) and in `factory/`.

## Seats

| Seat | Harness | Model | Effort | Owns |
|---|---|---|---|---|
| coordinator | Claude Code | claude-sonnet-5-5 | medium | requirements ledger, work split, handoffs, measurements, acceptance, final report |
| builder-a | Claude Code | claude-sonnet-5-5 | medium | the work items the coordinator assigns |
| builder-b | Claude Code | claude-sonnet-5-5 | medium | the work items the coordinator assigns |
| examiner | Claude Code | claude-sonnet-5-5 | medium | its own requirement list, spec-only probes, screenshots, the verdict |

The rules for each seat are in `mandates/`. They describe how the factory works and
say nothing about this track, so the same four files work for any spec.

## How a stage runs

1. **Ledger first.** The coordinator reads the stage spec and writes
   `factory/stage-N/ledger.md`: every testable statement, numbered `R-01`, `R-02`…,
   with its section, owner and how it will be checked. Statements the shipped checks
   never test go in too. Only a small share of each stage's tests ship (6% for stage 2),
   so the ledger is how the band aims at the rest.
2. **A second, blind reading.** At the same time the examiner gets the spec only, no
   ledger, and writes its own list (`exam-list.md`). The coordinator merges the two;
   anything the examiner found and the ledger missed becomes new work.
3. **Small numbered work items.** Ledger rows are grouped into items of at most eight
   rows (W-1, W-2…), split so the two builders never edit the same file at once. Every
   commit message starts with the ledger IDs it covers, so any line of code traces back
   to a requirement and to the room message that assigned it.
4. **Review while building.** Items go to the examiner as they land. The examiner tests
   them with probes written from the spec text alone, never from the implementation,
   and confirms each failure twice (re-reads the spec, reruns the probe) before
   reporting it, so builders only get real failures.
5. **Measure what costs money.** When a spec prices outside calls, a builder writes a
   measurement script that runs the service against the local stand-ins and reports
   cost per correct result. At least two approaches are compared before one is chosen.
6. **Close.** The examiner runs the supplied checks in isolated mode, screenshots every
   screen at 375px and 1280px, and gives one verdict. The coordinator records time,
   review rounds, catches and cost in `factory/measurements.md`, records every decision
   on an unclear spec point in `factory/rulings.md`, and posts the accepted revision.
   Later stages read the rulings so the same question is never decided twice.

Accepted stage folders are never edited again. Each stage starts as a copy of the
previous one.

## Results

| Stage | Dispatch → accepted | Ledger rows | Added by examiner's blind list | Product defects caught in review | Max spend per build | Isolated check |
|---|---|---|---|---|---|---|
| 1 | 28 min | 73 | 2 | 0 | 47 of 80 units | claimed stage 1 |
| 2 | 32 min | 70 | 11 | 1 | 72 of 80 units | claimed stage 2 |
| 3 | 76 min (2 nudges) | 73 | 3 | 0 | 72 of 80 units | claimed stage 3 |
| 4 | 60 min, paused 7 h by the usage limit, then 11 min | 65 | 5 | 3 | capped at 80 | claimed stage 4 |

The blind second reading pays off most: 21 requirements over four stages that the
coordinator's ledger missed and the band then built.

The stage-2 catch is a good example of review changing the work. The builders' mandate
says people should never see internal field keys on screen. The spec for one screen
requires the field identifier to be shown. The examiner's probe, written from the spec,
failed; builder-a fixed it in `85638d8`; the examiner re-ran everything and accepted.

Stage 4 is the clearest case for an examiner that writes its own tests. At `4695fb1` the
supplied checks for stages 1-4 all passed, but the examiner's crafted corpus made one
build bill 92 units against the 80 cap while the dossier reported 80. The cause was an
extract answered with an in-band 404: the spec bills it, the build treated it as a free
refusal and retried it. builder-a fixed it in `32129f9` and the examiner accepted at
`3a05d10`. Earlier in the same stage the examiner killed the service mid-batch and found
a restart billed 204 units against a 150-unit batch budget (fixed in `00d4835`).

### Research cost

Measured on the local stand-in corpus (raw numbers in `factory/stage-N/measure-raw.md`):

| Stage | Strategy | Units | Correct | Units per correct |
|---|---|---|---|---|
| 1 | search + extract + research + follow-ups (chosen) | 511 | 70 | 7.30 |
| 1 | deep search + research | 690 | 70 | 9.86 |
| 1 | search + extract, no research | 208 | 62 | 3.35 |
| 1 | fast search + research, no extract | 360 | 46 | 7.83 |
| 2 | rendered extract (chosen) | 804 | 62 | 12.97 |
| 2 | plain extract | 486 | 62 | 7.84 |

The cheapest options were rejected on purpose, and the reasons are recorded: dropping
research loses fields that only research reaches, and plain extract is cheaper on the
stand-ins but the spec defines page text as browser text, which plain text may not match
on unseen pages.

## Setup (to reproduce)

- Windows 11, 16 GB RAM. Docker Desktop and the check harness run in WSL2 (Ubuntu 24.04);
  `.wslconfig` caps WSL at 11 GB with 8 GB swap.
- Band Desktop (Pro) with Claude Code on Windows, signed in to one Claude Pro account
  shared by all four seats.
- Each seat: runtime Claude Code, model and effort as above, permission mode Auto,
  working directory = the result repo, instructions: `Before every task, read and follow
  mandates/<seat>.md in your working directory.`
- `.claude/settings.json` in the repo blocks the account's unrelated connectors and both
  ask-the-human tools for every seat. That cut each seat from 214 tools to 37, which saves
  context on every turn and makes asking a human impossible.
- Seats run in PowerShell and reach Linux through `wsl -d Ubuntu-24.04 -- bash -lc '...'`.
- One room per stage, dispatched only after the Claude usage window resets. A stage uses
  about 60% of a Pro session; starting low means no seat stops mid-stage. Stage 4 was bigger and still hit the limit
  (see below).

## Cost

| Item | Cost |
|---|---|
| Model use | one Claude Pro subscription; about 60% of a 5-hour session per stage |
| Band | Pro (event code) |
| Research providers | local stand-ins during the build; four live builds (runway.com, linear.app, vercel.com, supabase.com) with my own Nimble key, at most 80 units each |

## What I tried that failed

- **A free model for the examiner.** It was the plan (a different model family reviewing
  Claude's work), but the free tier hit its quota on the first task of the first
  practice run. Moved to Claude.
- **Haiku as examiner.** Cheaper, but across a full practice stage every failure it
  reported was a bug in its own probes. Moved to Sonnet and added the confirm-twice rule.
- **Review only at the end.** In practice runs the examiner found nothing because it only
  saw finished work. Reviewing items as they land is what produced real catches.
- **"About eight rows per commit".** Builders ignored the soft wording. With a hard limit
  some builders then made small marker commits while the code itself went in one larger
  commit. The coordinator records every case in `factory/stage-N/deviations.md` instead
  of hiding it; the honest fix would be smaller files, not more commits.
- **Double-quoted WSL commands.** PowerShell expanded `$(...)` before Ubuntu saw it.
  Mandates now require single quotes.
- **Acknowledgement chatter.** Seats replied to thanks and receipts, wasting turns and
  delivery time. Mandates now say to reply only when asked to act, and use the no-reply tool.
- **Band daemon on Windows.** It went offline twice under load ("All pipe instances are
  busy"). Seats kept committing; restarting Band before each dispatch avoided it.
- **Seats ending their turn while promising work (stage 3).** Twice a seat said it would
  run a check and report, then ended its turn; nothing runs until someone messages it, so
  the room went quiet and I had to nudge. The examiner's wait loop also matched its own
  `pgrep` command and never finished. The stage-4 dispatch adds two rules: run every check
  in the foreground and wait for it, and your turn ends when you send a message. Stage 4
  had no stall from a seat.
- **One Claude Pro account for four seats.** Stage 4 hit the 5-hour usage limit at 18:05,
  right after the examiner's CHANGES NEEDED verdict, and every seat stopped. One message
  after the reset at 01:03 resumed it; the fix and acceptance took 11 more minutes.

## How the factory catches a bad result

- Two independent readings of the spec, merged, so a requirement missed by one seat is
  usually caught by the other.
- Probes written from the spec only, so the examiner cannot inherit a builder's
  misreading by reading its code.
- Failures must be tied to a quoted requirement and reproduced twice before they reach
  a builder.
- Every screen is screenshotted in every named state at two widths.
- The final check runs in isolated mode, the way judges run it.
- Accepted folders are frozen; a later stage cannot break an earlier one.
