# Ideas

What the first version does, and what could come next. The order is a suggestion, not a plan.

## In the first version

| Idea | Where |
|---|---|
| Claim several rows at once | `board claim A B C` |
| Work locally, then land the whole batch in one push | `board done`, `board land` |
| Claims go out alone, so local work is never pushed by accident | `Git.publish_board_change` |
| Two agents cannot hold the same row; the loser is told and keeps the rows it did get | `tests/test_flow.py` |
| The Done table gets the real commit hash at landing, with no follow-up commit | `board land` |
| Gaps found during a row become new rows when it lands | `board done --gap` |
| A check for CI: duplicate IDs, needs that point nowhere, malformed Done rows, stale claims | `board check` |
| The board as an interactive chart | `board chart` |

## Next, roughly by value

1. **Claims that expire.** A batch holds rows for longer than a single claim does. Give each claim a lease
   (say 24 hours), let `board land` and a new `board renew` extend it, and let `board check` or a scheduled
   CI job release claims whose lease ran out. Today `board check` only warns.
2. **Say which files a row will touch.** An optional `Touches` column (paths or globs). `board claim` would
   refuse a row whose files overlap with a row someone else holds. This is what makes a batch land without
   conflicts.
3. **A size for each row.** An optional `Size` column (S/M/L or points) so completion can be weighted by
   effort instead of counting every row as one.
4. **`board split ID`.** Split a row into parts with the same Area and Needs, and decide once what happens
   to the parent, so parents are not counted next to their parts.
5. **`board decide ID "answer"`.** Record a person's decision on a `humans` row: move it to Done, log who
   decided, and update rows that were waiting on it.
6. **Protected main.** `board land --pr` pushes a branch and opens a pull request instead of pushing to
   main, for repositories where agents may not push to main.
7. **Fewer conflicts by construction.** The change log is the line every board commit appends to. Either
   drop it in favour of `git log -- WORK.md`, or keep one file per row under `board/` and generate
   `WORK.md` from them.
8. **Publish the chart.** A GitHub Action that runs `board chart` on every push to main and puts it on
   GitHub Pages.
9. **Progress over time.** Read the board at each commit in `git log` and draw rows done per day.
10. **Several projects, one view.** `board status --all` over a list of repositories, and one chart.
11. **Tools instead of shell.** An MCP server exposing `next`, `claim`, `done`, `land`, so an agent calls
    the board as tools and cannot edit `WORK.md` by hand.
12. **Review before Done.** An optional `review` state between finished and Done, for projects where a
    second agent or a person checks the work.

## Open questions

- How big may a batch be? A row limit, a time limit, or left to the rules in `AGENTS.md`?
- Should a landing push all finished rows or nothing, or may it land the rows that rebase cleanly and keep
  the rest?
- One board per repository, or one board across several?
