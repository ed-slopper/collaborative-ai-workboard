# AGENTS.md: how to work on {{title}}

The work is listed in [`WORK.md`](WORK.md). People and AI agents share it. Change the board only with the
`board` command: it keeps the table valid and makes sure two workers never get the same row.

## The loop

1. **Look.** `board status`, then `board next` for rows that can be started now.
2. **Claim.** `board claim F3 F4 F7 --who <person>/<agent>`. Take as many rows as you will finish this session.
   The claim is pushed at once, on its own, so everyone sees it. Your work is not pushed yet.
3. **Work locally.** One row at a time. Commit each row's work with `board commit F3 -m "what changed"`
   (or any commit whose message starts with `F3:`).
4. **Mark it finished.** `board done F3`. Add `--gap "what is still missing"` for each gap you found: it
   becomes a new row when you land. Add `--summary "..."` to say what was actually done.
5. **Land.** When the batch is finished, `board land`. It rebases your commits onto the newest main, moves
   every finished row to Done with its real commit hash, and pushes everything in one go.

## Rules

- Take rows in board order: the first ready rows in the earliest section.
- Never take a row whose Area is `humans`. Ask the person and record their answer.
- A claim is a promise for this session. If you stop early, `board release F3 --note "done: ..., left: ..."`.
- Keep a batch small enough to land the same day. Rows you hold are rows nobody else can take.
- If `board land` reports a conflict, fix it, `git rebase --continue`, and run `board land` again.
- Do not edit the Done table or reuse an ID.

## What "done" means here

Write the project's own rule here (for example: tests pass and CI is green).
