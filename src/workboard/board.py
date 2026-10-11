"""The board itself: read a WORK.md, answer questions about it, change it.

The Markdown file is the only source of truth. Every change is made line by
line, so rows the tool does not touch keep their exact text.
"""
from __future__ import annotations

import datetime
import os
import re
from collections import Counter
from dataclasses import dataclass, field

STATUSES = ("done", "progress", "ready", "decision", "blocked")
STATUS_LABEL = {
    "done": "done",
    "progress": "in progress",
    "ready": "ready to start",
    "decision": "needs a human decision",
    "blocked": "waiting on other rows",
}
OPEN_COLUMNS = ["ID", "Task", "Area", "Needs", "Who", "Notes"]
DONE_COLUMNS = ["ID", "Task", "Section", "Who", "Date", "Commit"]
_RANGE = re.compile(r"([A-Za-z]+)(\d+)\s*[–-]\s*([A-Za-z]*)(\d+)$")
_WHO = re.compile(r"^(.*?)\s*\((\d{4}-\d\d-\d\d)\)$")
_ID = re.compile(r"^([A-Za-z]+)(\d+)(.*)$")


class BoardError(Exception):
    """The board cannot do what was asked (row taken, unknown ID, ...)."""


def today() -> str:
    return os.environ.get("WORKBOARD_DATE") or datetime.date.today().isoformat()


def split_row(line: str) -> list[str] | None:
    """Split one Markdown table line into cells.

    A `|` inside backticks, or written as `\\|`, belongs to the cell.
    Returns None when the line is not a table row.
    """
    body = line.strip()
    if not body.startswith("|"):
        return None
    body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells, cur, in_code, i = [], "", False, 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and body[i + 1 : i + 2] == "|":
            cur += "\\|"
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    cells.append(cur.strip())
    return cells


def join_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c) and any(cells)


@dataclass
class Row:
    id: str
    cells: dict[str, str]
    line: int
    section: str  # section key; for done rows, the first key in its Section cell
    done: bool = False

    def get(self, name: str) -> str:
        return self.cells.get(name.lower(), "")

    @property
    def task(self) -> str:
        return self.get("task")

    @property
    def who(self) -> str:
        return self.get("who")

    @property
    def needs(self) -> list[str]:
        return [n.strip() for n in self.get("needs").split(",") if n.strip()]


@dataclass
class Section:
    key: str
    name: str
    heading: int
    columns: list[str] = field(default_factory=list)
    header_line: int = -1
    last_table_line: int = -1
    rows: list[Row] = field(default_factory=list)


class Board:
    def __init__(self, text: str, decision_areas=("humans",), done_heading="Done",
                 log_heading="Changes to the board"):
        self.decision_areas = {a.lower() for a in decision_areas}
        self.done_heading = done_heading
        self.log_heading = log_heading
        self.lines = text.split("\n")
        self._parse()

    # ---------------------------------------------------------------- reading
    def _parse(self) -> None:
        self.sections: list[Section] = []
        self.done = Section(self.done_heading, self.done_heading, -1)
        self.log_start = -1
        self.log_last = -1
        self.problems: list[str] = []
        current: Section | None = None
        mode = None  # 'tier' | 'done' | 'log' | None
        for i, line in enumerate(self.lines):
            m = re.match(r"##\s+(.+?)\s*$", line)
            if m:
                title = m.group(1)
                if title == self.done_heading:
                    mode, current = "done", self.done
                    self.done.heading = i
                elif title == self.log_heading:
                    mode, current = "log", None
                    self.log_start = self.log_last = i
                else:
                    parts = title.split(None, 1)
                    key, name = (parts[0], parts[1]) if len(parts) == 2 else (title, title)
                    current = Section(key, name, i)
                    mode = "tier"
                    self.sections.append(current)
                continue
            if mode == "log":
                if line.startswith("- "):
                    self.log_last = i
                continue
            if current is None:
                continue
            cells = split_row(line)
            if cells is None:
                continue
            if not current.columns:
                if cells and cells[0].strip().lower() == "id":
                    current.columns = [c.strip().lower() for c in cells]
                    current.header_line = current.last_table_line = i
                continue
            current.last_table_line = i
            if _is_separator(cells):
                continue
            if len(cells) > len(current.columns):
                self.problems.append(
                    f"line {i + 1}: row {cells[0]} has {len(cells)} cells, the table has "
                    f"{len(current.columns)} columns (a `|` outside backticks?)")
            cells = cells + [""] * (len(current.columns) - len(cells))
            data = dict(zip(current.columns, cells))
            rid = data.get("id", "")
            if not rid:
                continue
            if mode == "done":
                sec = re.split(r"[/,\s]", data.get("section", "").strip())[0]
                current.rows.append(Row(rid, data, i, sec, done=True))
            else:
                current.rows.append(Row(rid, data, i, current.key))
        # only sections that hold a board table are tiers
        self.sections = [s for s in self.sections if s.columns]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def open_rows(self) -> list[Row]:
        return [r for s in self.sections for r in s.rows]

    @property
    def done_rows(self) -> list[Row]:
        return list(self.done.rows)

    @property
    def rows(self) -> list[Row]:
        return self.open_rows + self.done_rows

    def find(self, rid: str) -> Row:
        for r in self.rows:
            if r.id == rid:
                return r
        raise BoardError(f"no row {rid} on the board")

    def section(self, key: str) -> Section:
        for s in self.sections:
            if s.key.lower() == key.lower() or s.name.lower() == key.lower():
                return s
        raise BoardError(f"no section {key}; the board has {', '.join(s.key for s in self.sections)}")

    # ------------------------------------------------------------ dependencies
    def _range_ids(self, token: str) -> list[str] | None:
        m = _RANGE.match(token)
        if not m:
            return None
        prefix, lo, hi = m.group(1), int(m.group(2)), int(m.group(4))
        out = []
        for r in self.rows:
            im = _ID.match(r.id)
            if im and im.group(1) == prefix and lo <= int(im.group(2)) <= hi:
                out.append(r.id)
        return out

    def need_open(self, token: str) -> bool:
        """True while this entry of a Needs cell is still unfinished."""
        done_ids = {r.id for r in self.done.rows}
        open_ids = {r.id for r in self.open_rows}
        ranged = self._range_ids(token)
        if ranged is not None:
            return not ranged or any(i in open_ids for i in ranged)
        if token in open_ids:
            return True
        if token in done_ids:
            return False
        # a row that was split and removed: finished when all its parts are
        parts = [i for i in done_ids | open_ids if i.startswith(token) and i != token]
        return not parts or any(i in open_ids for i in parts)

    def blockers(self, row: Row) -> list[str]:
        return [n for n in row.needs if self.need_open(n)]

    def status(self, row: Row) -> str:
        if row.done:
            return "done"
        if row.who:
            return "progress"
        if row.get("area").lower() in self.decision_areas:
            return "decision"
        return "blocked" if self.blockers(row) else "ready"

    def counts(self, rows=None) -> Counter:
        c = Counter({s: 0 for s in STATUSES})
        for r in (self.rows if rows is None else rows):
            c[self.status(r)] += 1
        return c

    def rows_in(self, key: str) -> list[Row]:
        return [r for r in self.rows if r.section == key]

    def ready(self, person: str | None = None) -> list[Row]:
        """Rows an agent may take now, in board order."""
        out = []
        for r in self.open_rows:
            if self.status(r) != "ready":
                continue
            area = r.get("area").lower()
            if person and area not in ("", "any", "unowned", person.lower()):
                continue
            out.append(r)
        return out

    # ---------------------------------------------------------------- changing
    def _set(self, row: Row, **cells: str) -> None:
        sec = self.done if row.done else self.section(row.section)
        data = dict(row.cells)
        data.update({k.lower(): v for k, v in cells.items()})
        self.lines[row.line] = join_row([data.get(c, "") for c in sec.columns])
        self._parse()

    def claim(self, rid: str, who: str, date: str | None = None, force: bool = False) -> None:
        row = self.find(rid)
        state = self.status(row)
        if state == "done":
            raise BoardError(f"{rid} is already done")
        if state == "progress":
            raise BoardError(f"{rid} is taken by {row.who}")
        if state == "decision":
            raise BoardError(f"{rid} is a decision for a person, not for an agent")
        if state == "blocked" and not force:
            raise BoardError(f"{rid} still needs {', '.join(self.blockers(row))}")
        self._set(row, who=f"{who} ({date or today()})")

    def release(self, rid: str, note: str = "") -> None:
        row = self.find(rid)
        if row.done or not row.who:
            raise BoardError(f"{rid} is not claimed")
        notes = row.get("notes")
        if note:
            notes = f"{notes}; {note}" if notes else note
        self._set(row, who="", notes=notes)

    def finish(self, rid: str, commit: str, who: str | None = None, date: str | None = None,
               summary: str | None = None) -> None:
        """Move a row to the Done table."""
        row = self.find(rid)
        if row.done:
            raise BoardError(f"{rid} is already done")
        if self.done.header_line < 0:
            raise BoardError(f"the board has no '## {self.done_heading}' table")
        owner = who or (_WHO.match(row.who).group(1) if _WHO.match(row.who) else row.who)
        data = {"id": rid, "task": summary or row.task, "section": row.section,
                "who": owner, "date": date or today(), "commit": commit}
        new = join_row([data.get(c, "") for c in self.done.columns])
        del self.lines[row.line]
        self._parse()
        self.lines.insert(self.done.last_table_line + 1, new)
        self._parse()

    def next_id(self, key: str) -> str:
        sec = self.section(key)
        letters = Counter()
        for r in self.rows_in(sec.key):
            m = _ID.match(r.id)
            if m:
                letters[m.group(1)] += 1
        letter = letters.most_common(1)[0][0] if letters else sec.name[:1].upper()
        nums = [int(m.group(2)) for r in self.rows if (m := _ID.match(r.id)) and m.group(1) == letter]
        return f"{letter}{max(nums, default=0) + 1}"

    def add(self, key: str, task: str, area: str = "any", needs: str = "", notes: str = "",
            rid: str | None = None) -> str:
        sec = self.section(key)
        rid = rid or self.next_id(key)
        if any(r.id == rid for r in self.rows):
            raise BoardError(f"{rid} is already on the board; IDs are never reused")
        data = {"id": rid, "task": task, "area": area, "needs": needs, "who": "", "notes": notes}
        self.lines.insert(sec.last_table_line + 1, join_row([data.get(c, "") for c in sec.columns]))
        self._parse()
        return rid

    def log(self, text: str, who: str, date: str | None = None) -> None:
        """Add a line to the change log, if the board keeps one."""
        if self.log_start < 0:
            return
        self.lines.insert(self.log_last + 1, f"- {date or today()} {who}: {text}")
        self._parse()

    # ---------------------------------------------------------------- checking
    def check(self, stale_days: int = 2, now: str | None = None) -> tuple[list[str], list[str]]:
        """Return (errors, warnings)."""
        errors, warnings = list(self.problems), []
        seen = Counter(r.id for r in self.rows)
        for rid, n in seen.items():
            if n > 1:
                errors.append(f"{rid} appears {n} times; IDs must be unique")
        if not self.sections:
            errors.append("no section with a board table (a table whose first column is ID)")
        if self.done.header_line < 0:
            errors.append(f"no '## {self.done_heading}' table")
        ids = set(seen)
        day = datetime.date.fromisoformat(now or today())
        for r in self.open_rows:
            for n in r.needs:
                if n in ids:
                    continue
                ranged = self._range_ids(n)
                if ranged is None and not any(i.startswith(n) for i in ids):
                    errors.append(f"{r.id} needs {n}, which is not on the board")
                elif ranged == []:
                    errors.append(f"{r.id} needs {n}, a range that matches no rows")
            if r.who:
                m = _WHO.match(r.who)
                if not m:
                    warnings.append(f"{r.id}: Who should be `name (YYYY-MM-DD)`, found `{r.who}`")
                elif (day - datetime.date.fromisoformat(m.group(2))).days > stale_days:
                    warnings.append(f"{r.id}: claimed by {m.group(1)} on {m.group(2)}, "
                                    f"more than {stale_days} days ago")
        keys = {s.key for s in self.sections}
        for r in self.done.rows:
            if not re.fullmatch(r"\d{4}-\d\d-\d\d", r.get("date")):
                errors.append(f"{r.id}: Done date should be YYYY-MM-DD, found `{r.get('date')}`")
            if r.get("commit") and not re.fullmatch(r"[0-9a-f]{7,40}", r.get("commit")):
                errors.append(f"{r.id}: Commit should be a hash, found `{r.get('commit')}`")
            if not r.get("commit"):
                warnings.append(f"{r.id}: done without a commit hash")
            if r.section not in keys:
                warnings.append(f"{r.id}: section `{r.get('section')}` is not a section of this board")
        return errors, warnings
