"""The `board` command."""
from __future__ import annotations

import argparse
import os
import sys

from . import __version__, chart
from .board import STATUS_LABEL, Board, BoardError, today
from .config import FILE, Config, load
from .gitops import Git

TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")


# ------------------------------------------------------------------ helpers
def _board(cfg: Config, text: str | None = None) -> Board:
    if text is None:
        try:
            with open(cfg.board_path, encoding="utf-8") as f:
                text = f.read()
        except FileNotFoundError:
            raise BoardError(f"no {cfg.board} in {cfg.root}; run `board init` first")
    return Board(text, cfg.decision_areas, cfg.done_heading, cfg.log_heading)


def _write(cfg: Config, board: Board) -> None:
    with open(cfg.board_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(board.text)


def _git(cfg: Config) -> Git:
    return Git(cfg.root, cfg.remote, cfg.branch)


def _who(cfg: Config, args) -> str:
    who = getattr(args, "who", None) or os.environ.get("WORKBOARD_WHO") or cfg.who
    if not who:
        git = _git(cfg)
        who = git.out("config", "user.name", check=False) if git.is_repo() else ""
    if not who:
        raise BoardError("who are you? pass --who person/agent or set WORKBOARD_WHO")
    return who


def _shared(cfg: Config) -> bool:
    """True when board changes go straight to a remote that others also use."""
    git = _git(cfg)
    return git.is_repo() and git.has_remote()


def _change(cfg: Config, change, local_message: str):
    """Run a board change: on the remote board when there is one, else on the file."""
    git = _git(cfg)
    if _shared(cfg):
        return git.publish_board_change(cfg.board, change)
    board = _board(cfg)
    new_text, message, result = change(board.text)
    with open(cfg.board_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_text)
    if git.is_repo():
        git.run("add", cfg.board)
        git.run("commit", "--quiet", "-m", message or local_message, "--", cfg.board)
    return result


def _bar(done: int, total: int, width: int = 10) -> str:
    filled = round(width * done / total) if total else 0
    return "#" * filled + "." * (width - filled)


# ----------------------------------------------------------------- commands
def cmd_init(cfg: Config, args) -> int:
    made = []
    for src, dest in (("WORK.md", cfg.board), ("AGENTS.md", "AGENTS.md"), (FILE, FILE),
                      ("board.yml", ".github/workflows/board.yml")):
        target = os.path.join(cfg.root, dest)
        if os.path.exists(target):
            print(f"kept     {dest} (already there)")
            continue
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        with open(os.path.join(TEMPLATES, src), encoding="utf-8") as f:
            text = f.read().replace("{{title}}", cfg.title).replace("{{date}}", today())
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        made.append(dest)
        print(f"created  {dest}")
    if made:
        print("\nNext: put your real rows in the board, then `board status`.")
    return 0


def cmd_status(cfg: Config, args) -> int:
    b = _board(cfg)
    c, total = b.counts(), len(b.rows)
    pct = 100 * c["done"] / total if total else 0
    print(f"{cfg.board}: {pct:.1f}% done ({c['done']} of {total} rows)\n")
    width = max((len(f"{s.key} {s.name}") for s in b.sections), default=10)
    for s in b.sections:
        rows = b.rows_in(s.key)
        d = sum(1 for r in rows if r.done)
        label = s.key if s.key == s.name else f"{s.key} {s.name}"
        print(f"  {label:<{width}}  {_bar(d, len(rows))}  {d:>3} of {len(rows):<3}")
    print(f"\n  in progress {c['progress']} · ready {c['ready']} · waiting {c['blocked']} "
          f"· decisions {c['decision']}")
    for r in b.open_rows:
        if b.status(r) == "progress":
            print(f"    {r.id:<6} {r.who}")
    git = _git(cfg)
    if git.is_repo() and (pending := git.journal()):
        print(f"\n  finished here, not landed yet: {', '.join(e['id'] for e in pending)}"
              "  (`board land`)")
    return 0


def cmd_next(cfg: Config, args) -> int:
    b = _board(cfg)
    person = (args.person or "").split("/")[0] or None
    rows = b.ready(person)[: args.count]
    if not rows:
        print("nothing is ready to start")
        return 0
    for r in rows:
        task = r.task if len(r.task) <= 96 else r.task[:95] + "…"
        print(f"{r.id:<6} {r.section:<4} {task}")
    return 0


def cmd_show(cfg: Config, args) -> int:
    b = _board(cfg)
    r = b.find(args.id)
    print(f"{r.id}  [{STATUS_LABEL[b.status(r)]}]  section {r.get('section') or r.section}")
    print(f"\n{r.task}\n")
    for name in ("area", "needs", "who", "date", "commit", "notes"):
        if r.get(name):
            print(f"{name.capitalize():<7} {r.get(name)}")
    if not r.done and (blk := b.blockers(r)):
        print(f"Waiting on {', '.join(blk)}")
    return 0


def cmd_claim(cfg: Config, args) -> int:
    who, date = _who(cfg, args), today()

    def change(text):
        b = _board(cfg, text)
        taken, skipped = [], []
        for rid in args.ids:
            try:
                b.claim(rid, who, date, force=args.force)
                taken.append(rid)
            except BoardError as e:
                skipped.append(str(e))
        if not taken:
            raise BoardError("nothing claimed: " + "; ".join(skipped))
        b.log(f"claim {', '.join(taken)}.", who, date)
        return b.text, f"claim {', '.join(taken)}", (taken, skipped)

    taken, skipped = _change(cfg, change, "claim")
    print(f"claimed {', '.join(taken)} for {who}")
    for s in skipped:
        print(f"skipped: {s}")
    if _shared(cfg):
        print("The claim is on the remote board. Your work stays local until `board land`.")
    return 0


def cmd_release(cfg: Config, args) -> int:
    who = _who(cfg, args)

    def change(text):
        b = _board(cfg, text)
        b.release(args.id, args.note or "")
        b.log(f"{args.id} released" + (f": {args.note}" if args.note else "."), who)
        return b.text, f"release {args.id}", None

    _change(cfg, change, "release")
    git = _git(cfg)
    if git.is_repo():
        git.save_journal([e for e in git.journal() if e["id"] != args.id])
    print(f"released {args.id}")
    return 0


def cmd_add(cfg: Config, args) -> int:
    who = _who(cfg, args)

    def change(text):
        b = _board(cfg, text)
        section = args.section
        notes = args.notes or ""
        if args.gap_of:
            section = section or b.find(args.gap_of).section
            notes = f"Gap of {args.gap_of}" + (f". {notes}" if notes else "")
        if not section:
            raise BoardError("which section? pass --section or --gap-of")
        rid = b.add(section, args.task, args.area, args.needs or "", notes)
        b.log(f"added {rid}" + (f" (gap of {args.gap_of})." if args.gap_of else "."), who)
        return b.text, f"board: add {rid}", rid

    print(f"added {_change(cfg, change, 'add')}")
    return 0


def cmd_commit(cfg: Config, args) -> int:
    """`git commit` with the row written into the message, so `land` can find it."""
    git = _git(cfg)
    _board(cfg).find(args.id)
    p = git.run("commit", "-m", f"{args.id}: {args.message}", "--trailer", f"Row: {args.id}",
                *args.git_args, check=False)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    return p.returncode


def cmd_done(cfg: Config, args) -> int:
    git = _git(cfg)
    if not git.is_repo():
        raise BoardError("`board done` needs a git repository")
    b = _board(cfg)
    row = b.find(args.id)
    if row.done:
        raise BoardError(f"{args.id} is already done")
    if not row.who:
        raise BoardError(f"{args.id} is not claimed; `board claim {args.id}` first")
    commit = args.commit or git.row_commit(args.id, git.upstream if git.has_remote() else None)
    if not commit and not args.no_commit:
        raise BoardError(f"no commit found for {args.id}. Commit the work with "
                         f"`board commit {args.id} -m ...`, or pass --commit HASH, or --no-commit "
                         "if the row has no code (a decision, a note)")
    entries = [e for e in git.journal() if e["id"] != args.id]
    entries.append({"id": args.id, "summary": args.summary or "", "gaps": args.gap or [],
                    "commit": args.commit or "", "no_commit": bool(args.no_commit)})
    git.save_journal(entries)
    print(f"{args.id} finished here ({len(entries)} waiting to land). Publish with `board land`.")
    return 0


def cmd_pending(cfg: Config, args) -> int:
    entries = _git(cfg).journal()
    if not entries:
        print("nothing waiting to land")
    for e in entries:
        gaps = f"  +{len(e['gaps'])} gap rows" if e["gaps"] else ""
        print(f"{e['id']:<6} {e['summary'] or '(task text unchanged)'}{gaps}")
    return 0


def cmd_land(cfg: Config, args) -> int:
    """Publish everything finished here in one push: the work commits, then one
    board commit that moves every finished row to Done with its real hash."""
    git = _git(cfg)
    entries = git.journal()
    if not entries:
        print("nothing waiting to land; `board done ID` marks a finished row")
        return 0
    if git.dirty():
        raise BoardError("there are uncommitted changes; commit or stash them, then land again")
    shared = git.has_remote()
    ids = [e["id"] for e in entries]
    added: list[str] = []
    for attempt in range(1, args.tries + 1):
        base = None
        if shared:
            git.fetch()
            base = git.upstream
            p = git.run("rebase", "--quiet", base, check=False)
            if p.returncode:
                raise BoardError("your commits conflict with what is on the remote now. Resolve the "
                                 "conflict, `git rebase --continue`, then `board land` again.\n"
                                 + (p.stderr or p.stdout).strip())
        b = _board(cfg)
        added, owner = [], ""
        for e in entries:
            row = b.find(e["id"])
            if row.done:
                continue  # someone already recorded it
            commit = e["commit"] or (git.row_commit(e["id"], base) or "")
            if not commit and not e["no_commit"]:
                raise BoardError(f"no commit found for {e['id']}")
            owner = owner or row.who.split(" (")[0]
            b.finish(e["id"], commit, summary=e["summary"] or None)
            for gap in e["gaps"]:
                added.append(b.add(row.section, gap, notes=f"Gap of {e['id']}"))
        note = f"{', '.join(ids)} done"
        if added:
            note += f"; added {', '.join(added)} (gaps)"
        b.log(note + ".", owner or _who(cfg, args))
        _write(cfg, b)
        git.run("add", cfg.board)
        git.run("commit", "--quiet", "-m", f"done {', '.join(ids)}", "--", cfg.board)
        if not shared:
            break
        p = git.run("push", "--quiet", git.remote, f"HEAD:refs/heads/{git.branch}", check=False)
        if p.returncode == 0:
            break
        git.run("reset", "--quiet", "--hard", "HEAD~1")  # drop the board commit and try again
        if attempt == args.tries:
            raise BoardError(f"the remote kept moving; gave up after {args.tries} tries. "
                             "Nothing was lost: run `board land` again.")
    git.save_journal([])
    where = f"pushed to {git.upstream}" if shared else "committed locally (no remote)"
    print(f"landed {', '.join(ids)}: {where}")
    if added:
        print(f"new rows from gaps: {', '.join(added)}")
    return 0


def cmd_check(cfg: Config, args) -> int:
    errors, warnings = _board(cfg).check(cfg.stale_days)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error:   {e}")
    if not errors and not warnings:
        print("the board is consistent")
    return 1 if errors or (args.strict and warnings) else 0


def cmd_chart(cfg: Config, args) -> int:
    git = _git(cfg)
    commit = git.head() if git.is_repo() and git.run("rev-parse", "HEAD", check=False).returncode == 0 else ""
    html = chart.render(_board(cfg), cfg, commit)
    out = args.output or os.path.join(cfg.root, "board.html")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"wrote {out}")
    return 0


# --------------------------------------------------------------------- main
def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="board", description="A WORK.md board for people and AI agents.")
    p.add_argument("--version", action="version", version=f"collaborative-ai-workboard {__version__}")
    p.add_argument("-C", dest="dir", default=".", help="run as if started in this folder")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, "Create WORK.md, AGENTS.md, workboard.toml and a CI check in this project.")
    add("status", cmd_status, "Show how far the board is, section by section.")
    sp = add("next", cmd_next, "List rows that can be started now, in board order.")
    sp.add_argument("-n", "--count", type=int, default=10)
    sp.add_argument("--person", help="only rows this person may take (their Area, `any` or `unowned`)")
    add("show", cmd_show, "Show one row in full.").add_argument("id")
    sp = add("claim", cmd_claim, "Claim one or more rows and publish the claim at once.")
    sp.add_argument("ids", nargs="+", metavar="ID")
    sp.add_argument("--who", help="person/agent, e.g. sam/claude")
    sp.add_argument("--force", action="store_true", help="claim even if a need is still open")
    sp = add("commit", cmd_commit, "git commit, with the row recorded in the message.")
    sp.add_argument("id")
    sp.add_argument("-m", "--message", required=True)
    sp.add_argument("git_args", nargs="*", help="extra arguments for git commit, after `--`")
    sp = add("done", cmd_done, "Mark a claimed row as finished here. Nothing is pushed until `board land`.")
    sp.add_argument("id")
    sp.add_argument("--summary", help="what was done, for the Done table (default: the task text)")
    sp.add_argument("--gap", action="append", help="a follow-up row to add when this lands (repeatable)")
    sp.add_argument("--commit", help="the commit that finished it (default: found from the messages)")
    sp.add_argument("--no-commit", action="store_true", help="the row has no code")
    add("pending", cmd_pending, "List rows finished here that are not landed yet.")
    sp = add("land", cmd_land, "Publish all finished rows in one push and move them to Done.")
    sp.add_argument("--tries", type=int, default=5)
    sp.add_argument("--who")
    sp = add("release", cmd_release, "Give a claimed row back.")
    sp.add_argument("id")
    sp.add_argument("--note", help="what is finished and what is left")
    sp.add_argument("--who")
    sp = add("add", cmd_add, "Add a row.")
    sp.add_argument("task")
    sp.add_argument("--section")
    sp.add_argument("--gap-of", metavar="ID", help="a gap found while doing this row")
    sp.add_argument("--area", default="any")
    sp.add_argument("--needs")
    sp.add_argument("--notes")
    sp.add_argument("--who")
    sp = add("check", cmd_check, "Check the board for mistakes (for CI).")
    sp.add_argument("--strict", action="store_true", help="warnings also fail")
    sp = add("chart", cmd_chart, "Write the board as one interactive HTML page.")
    sp.add_argument("-o", "--output")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.fn(load(args.dir), args)
    except BoardError as e:
        print(f"board: {e}", file=sys.stderr)
        return 2

