# collaborative-ai-workboard

A work board that lives in your repository as one Markdown file, `WORK.md`, and a small command, `board`,
that people and AI agents use to share it.

It grew out of the board in the SSX Tricky Rust rewrite, where several agents work from one `WORK.md` at the
same time. This tool keeps that format and takes over the bookkeeping.

**Status: a first working version.** The core flow below is implemented and tested against a real git remote.
The ideas still open are in [docs/ideas.md](docs/ideas.md).

## The idea: claim a batch, work locally, land once

```
board claim E8g E8h E8i --who ann/claude    # 1. take several rows; only the claim is pushed
board commit E8g -m "ground probe, exact"   # 2. work locally, one commit (or more) per row
board done E8g --gap "steep-lip branch is untested"
board commit E8h -m "ground motion checked"
board done E8h
board land                                  # 3. one push: all the work, then one board commit
```

What each step guarantees:

- **Claims are published immediately and alone.** `board claim` builds a commit that changes only `WORK.md`
  on top of the newest remote main and pushes just that. Your unfinished commits stay on your machine. If
  another agent pushed first, the newest board is read again and the claim is re-applied, so two agents can
  never both hold a row. Rows someone else took in the meantime are skipped and reported.
- **Work stays local.** Nothing you commit is pushed until you land.
- **Landing is one push.** `board land` rebases your commits onto the newest main, moves every finished row to
  the Done table with the hash of the commit that did it, adds a row for every gap you reported, writes one
  line in the change log, and pushes. If main moved during the push, it starts over. There is no separate
  "write the commit hash on the board" commit.

## Install

Python 3.10 or newer and git. No other dependencies.

```
pip install git+https://github.com/OWNER/collaborative-ai-workboard     # once this repository is hosted
pip install -e .                                       # from a clone
```

## Start a board in a project

```
cd your-project
board init        # creates WORK.md, AGENTS.md, workboard.toml and a CI check; never overwrites
board status
```

`AGENTS.md` is the short set of rules an agent reads before it starts. Edit it to fit the project.

## Commands

| Command | What it does |
|---|---|
| `board status` | How far the board is, section by section, and who holds what |
| `board next [-n 10] [--person ann]` | Rows that can be started now, in board order |
| `board show ID` | One row in full, with what it is waiting on |
| `board claim ID... --who person/agent` | Claim rows and publish the claim |
| `board commit ID -m "..."` | `git commit` with the row recorded in the message |
| `board done ID [--summary ...] [--gap ...]` | Mark a row finished here; nothing is pushed |
| `board pending` | Rows finished here that are not landed yet |
| `board land` | Publish everything finished in one push |
| `board release ID --note "..."` | Give a row back |
| `board add "task" --section P1` / `--gap-of ID` | Add a row with the next free ID |
| `board check [--strict]` | Find mistakes in the board; exit code 1 on errors (for CI) |
| `board chart [-o board.html]` | The board as one interactive HTML page |

`--who` can also come from `WORKBOARD_WHO` or `who` in `workboard.toml`.

## The board format

```markdown
## P0 Foundations

| ID | Task | Area | Needs | Who | Notes |
|---|---|---|---|---|---|
| F1 | Name the functions | any | F3 | ann/claude (2026-10-10) | |

## Done

| ID | Task | Section | Who | Date | Commit |
|---|---|---|---|---|---|
| F3 | Ghidra connected | P0 | ann | 2026-10-10 | 406fa6b |

## Changes to the board

- 2026-10-10 ann: F3 done.
```

- Every `##` section with a table whose first column is `ID` is a section of the board. The first word of the
  heading is its key (`P0`).
- A row is **ready** when it is unclaimed and everything in Needs is in Done. Needs may list IDs, a range
  (`C1–C16`), or a row that was split (`F11` counts as done when `F11a` and `F11b` are).
- A row whose Area is `humans` is a decision for a person. Agents cannot claim it.
- Rows the tool does not touch keep their exact text.

## How a row is matched to its commit

`board land` looks through your unpushed commits for the newest one that either carries a `Row: ID` trailer
(`board commit` adds it) or has a subject starting with `ID:`. Rows with no code, such as a decision, are
finished with `board done ID --no-commit`.

## Tests

```
python -m unittest discover -s tests -v
```

`tests/test_flow.py` creates a bare remote and two clones, and runs two agents against it: a batch claim, a
race for the same row, local work, and a landing push onto a main that moved in the meantime.

## Licence

None chosen yet. Add one before publishing.
