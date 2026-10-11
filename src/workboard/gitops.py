"""Git plumbing: publish board changes without publishing unfinished work."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from .board import BoardError


class Git:
    def __init__(self, cwd: str, remote: str = "origin", branch: str = "main"):
        self.cwd, self.remote, self.branch = cwd, remote, branch

    def run(self, *args: str, check: bool = True, stdin: str | None = None, env: dict | None = None):
        p = subprocess.run(["git", *args], cwd=self.cwd, input=stdin, text=True, capture_output=True,
                           env={**os.environ, **(env or {})}, encoding="utf-8")
        if check and p.returncode:
            raise BoardError(f"git {' '.join(args[:3])} failed: {(p.stderr or p.stdout).strip()}")
        return p

    def out(self, *args: str, **kw) -> str:
        return self.run(*args, **kw).stdout.strip()

    # ------------------------------------------------------------------ facts
    def is_repo(self) -> bool:
        return self.run("rev-parse", "--git-dir", check=False).returncode == 0

    def has_remote(self) -> bool:
        return self.remote in self.out("remote").split()

    @property
    def upstream(self) -> str:
        return f"{self.remote}/{self.branch}"

    def dirty(self) -> bool:
        return bool(self.out("status", "--porcelain", "--untracked-files=no"))

    def head(self, short: bool = True) -> str:
        return self.out("rev-parse", *(["--short"] if short else []), "HEAD")

    # ---------------------------------------------------------------- journal
    def _journal_path(self) -> str:
        d = os.path.join(self.cwd, self.out("rev-parse", "--git-dir"), "workboard")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "pending.json")

    def journal(self) -> list[dict]:
        try:
            with open(self._journal_path(), encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def save_journal(self, entries: list[dict]) -> None:
        with open(self._journal_path(), "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=1)

    # ------------------------------------------------------ board-only commits
    def fetch(self) -> None:
        self.run("fetch", "--quiet", self.remote, self.branch)

    def show(self, ref: str, path: str) -> str:
        return self.run("show", f"{ref}:{path}").stdout

    def _commit_file_on(self, parent: str, path: str, content: str, message: str) -> str:
        """Build a commit on `parent` that changes one file, without touching the work tree."""
        blob = self.out("hash-object", "-w", "--stdin", stdin=content)
        fd, index = tempfile.mkstemp(prefix="workboard-index-")
        os.close(fd)
        os.unlink(index)
        try:
            env = {"GIT_INDEX_FILE": index}
            self.run("read-tree", parent, env=env)
            self.run("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
            tree = self.out("write-tree", env=env)
        finally:
            if os.path.exists(index):
                os.unlink(index)
        return self.out("commit-tree", tree, "-p", parent, "-m", message)

    def publish_board_change(self, path: str, change, tries: int = 5):
        """Apply `change(text) -> (new_text, message, result)` to the board on the
        remote branch and push only that commit. Local work is never included.

        If someone else pushed first, the newest board is read again and the
        change is re-applied, so two agents cannot both get the same row.
        """
        last = ""
        for _ in range(tries):
            self.fetch()
            tip = self.out("rev-parse", self.upstream)
            new_text, message, result = change(self.show(tip, path))
            sha = self._commit_file_on(tip, path, new_text, message)
            p = self.run("push", "--quiet", self.remote, f"{sha}:refs/heads/{self.branch}", check=False)
            if p.returncode == 0:
                self.sync()
                return result
            last = p.stderr.strip()
        raise BoardError(f"could not push the board change after {tries} tries: {last}")

    def sync(self) -> bool:
        """Bring the local branch up to the remote one, keeping local commits on top."""
        self.fetch()
        p = self.run("rebase", "--autostash", "--quiet", self.upstream, check=False)
        if p.returncode:
            self.run("rebase", "--abort", check=False)
            return False
        return True

    # ------------------------------------------------------------------ rows
    def row_commit(self, rid: str, base: str | None) -> str | None:
        """Newest commit that belongs to a row: a `Row: ID` trailer, or a
        subject that starts with the ID."""
        fmt = "%h%x1f%s%x1f%(trailers:key=Row,valueonly,separator=%x2c)%x1e"
        for span in ([f"{base}..HEAD"] if base else []) + ["-500"]:
            log = self.out("log", f"--format={fmt}", span)
            for entry in log.split("\x1e"):
                parts = entry.strip("\n").split("\x1f")
                if len(parts) < 3:
                    continue
                sha, subject, trailers = parts
                tagged = [t.strip() for t in trailers.split(",")]
                if rid in tagged or subject.startswith((f"{rid}:", f"{rid} ")):
                    return sha
        return None
