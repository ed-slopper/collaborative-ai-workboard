"""Write the board as one self-contained, interactive HTML page."""
from __future__ import annotations

import datetime
import json
import os

from .board import Board
from .config import Config

TEMPLATE = os.path.join(os.path.dirname(__file__), "templates", "chart.html")


def items(board: Board) -> tuple[list[dict], list[list[str]]]:
    sections = [[s.key, s.name if s.name != s.key else ""] for s in board.sections]
    known = {s[0] for s in sections}
    out = []
    for r in board.rows:
        sec = r.section if r.section in known else "Other"
        out.append({
            "id": r.id, "task": r.task, "sec": sec, "status": board.status(r),
            "secraw": r.get("section") if r.done else "", "area": r.get("area"),
            "needs": r.get("needs"), "blockers": [] if r.done else board.blockers(r),
            "who": r.who, "notes": r.get("notes"), "date": r.get("date"), "commit": r.get("commit"),
        })
    if any(i["sec"] == "Other" for i in out):
        sections.append(["Other", ""])
    return out, sections


def render(board: Board, cfg: Config, commit: str = "") -> str:
    data, sections = items(board)
    now = datetime.datetime.now().astimezone()
    meta = {"title": cfg.title, "repo": cfg.repo_url.rstrip("/"), "board": cfg.board, "commit": commit,
            "when": f"{now.day} {now:%b %Y, %H:%M %Z}".strip()}

    def js(value) -> str:  # safe inside a <script> block
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    with open(TEMPLATE, encoding="utf-8") as f:
        page = f.read()
    title = cfg.title.replace("&", "&amp;").replace("<", "&lt;")
    return (page.replace("__TITLE__", title).replace("__META__", js(meta))
            .replace("__SECS__", js(sections)).replace("__DATA__", js(data)))
