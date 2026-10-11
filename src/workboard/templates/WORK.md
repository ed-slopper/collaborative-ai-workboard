# WORK.md: the board for {{title}}

How to use it: [`AGENTS.md`](AGENTS.md). Change it with the `board` command, not by hand.

Columns:
- **ID**: stable, one letter per section, never reused. A row that is split gets a letter or digit added (`F3` → `F3a`).
- **Area**: a person, `unowned`, `any`, or `humans` (a decision for a person, not for an agent).
- **Needs**: rows that must be in Done first.
- **Who**: empty = open, or `person/agent (date)`.

## P0 Foundations

| ID | Task | Area | Needs | Who | Notes |
|---|---|---|---|---|---|
| F1 | Replace these example rows with the real first tasks of the project | any | | | |
| F2 | Decide what "done" means for a row here (tests pass, reviewed, measured?) and write it in AGENTS.md | humans | | | |

## P1 Build

| ID | Task | Area | Needs | Who | Notes |
|---|---|---|---|---|---|
| B1 | The first real piece of work | any | F1 | | |

## P2 Finish

| ID | Task | Area | Needs | Who | Notes |
|---|---|---|---|---|---|
| X1 | Everything above is done and checked | any | B1 | | |

## Done

| ID | Task | Section | Who | Date | Commit |
|---|---|---|---|---|---|

## Changes to the board

- {{date}} board created with `board init`.
