"""Two agents on one remote: claims, a local batch, and one landing push."""
import os
import subprocess
import tempfile
import unittest

from workboard.board import Board
from workboard.cli import main

BOARD = """# Board

## P0 Foundations

| ID | Task | Area | Needs | Who | Notes |
|---|---|---|---|---|---|
| F1 | First | any | | | |
| F2 | Second | any | | | |
| F3 | Third | any | | | |
| F4 | Fourth | any | F1 | | |

## Done

| ID | Task | Section | Who | Date | Commit |
|---|---|---|---|---|---|

## Changes to the board

- 2026-01-01 board created.
"""


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Flow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.remote = os.path.join(root, "remote.git")
        git(root, "init", "--quiet", "--bare", "-b", "main", self.remote)
        seed = os.path.join(root, "seed")
        git(root, "clone", "--quiet", self.remote, seed)
        self._identity(seed, "seed")
        with open(os.path.join(seed, "WORK.md"), "w", newline="\n") as f:
            f.write(BOARD)
        git(seed, "add", "WORK.md")
        git(seed, "commit", "--quiet", "-m", "board")
        git(seed, "push", "--quiet", "origin", "HEAD:main")
        self.a, self.b = os.path.join(root, "a"), os.path.join(root, "b")
        for clone, name in ((self.a, "ann"), (self.b, "bob")):
            git(root, "clone", "--quiet", self.remote, clone)
            self._identity(clone, name)
        os.environ["WORKBOARD_DATE"] = "2026-01-02"

    def tearDown(self):
        os.environ.pop("WORKBOARD_DATE", None)
        self.tmp.cleanup()

    @staticmethod
    def _identity(repo, name):
        git(repo, "config", "user.name", name)
        git(repo, "config", "user.email", f"{name}@example.com")

    def board(self, *args, cwd):
        return main(["-C", cwd, *args])

    def work(self, repo, rid, name):
        with open(os.path.join(repo, name), "w") as f:
            f.write(rid)
        git(repo, "add", name)
        self.assertEqual(self.board("commit", rid, "-m", f"add {name}", cwd=repo), 0)

    def remote_board(self):
        return Board(git(self.remote, "show", "main:WORK.md") + "\n")

    def test_batch_claim_local_work_one_landing_push(self):
        # Ann claims three rows at once. Only the claim is pushed.
        self.assertEqual(self.board("claim", "F1", "F2", "F3", "--who", "ann/claude", cwd=self.a), 0)
        rb = self.remote_board()
        self.assertEqual(rb.find("F2").who, "ann/claude (2026-01-02)")

        # Bob cannot take Ann's row, and gets nothing when that is all he asked for.
        self.assertEqual(self.board("claim", "F2", "--who", "bob/claude", cwd=self.b), 2)

        # Ann works locally on two rows. Nothing of it is on the remote.
        self.work(self.a, "F1", "one.txt")
        self.work(self.a, "F2", "two.txt")
        self.assertEqual(self.board("done", "F1", "--gap", "F1 left a gap", cwd=self.a), 0)
        self.assertEqual(self.board("done", "F2", "--summary", "Second, properly", cwd=self.a), 0)
        self.assertNotIn("one.txt", git(self.remote, "ls-tree", "--name-only", "main"))

        # Meanwhile Bob pushes unrelated work, so the remote has moved on.
        with open(os.path.join(self.b, "bob.txt"), "w") as f:
            f.write("bob")
        git(self.b, "add", "bob.txt")
        git(self.b, "commit", "--quiet", "-m", "bob's change")
        git(self.b, "pull", "--quiet", "--rebase", "origin", "main")
        git(self.b, "push", "--quiet", "origin", "HEAD:main")

        # Ann lands: rebased on Bob's work, both rows in Done, one push.
        self.assertEqual(self.board("land", cwd=self.a), 0)
        rb = self.remote_board()
        self.assertEqual(rb.check(now="2026-01-02")[0], [])
        files = git(self.remote, "ls-tree", "--name-only", "main").split()
        self.assertEqual(sorted(files), ["WORK.md", "bob.txt", "one.txt", "two.txt"])
        for rid, name in (("F1", "one.txt"), ("F2", "two.txt")):
            row = rb.find(rid)
            self.assertTrue(row.done)
            self.assertEqual(row.who, "ann/claude")
            # the recorded hash is the commit that added the file, as it is on main
            added_by = git(self.remote, "log", "--format=%h", "main", "--", name)
            self.assertEqual(row.get("commit"), added_by)
        self.assertEqual(rb.find("F2").task, "Second, properly")
        self.assertEqual(rb.find("F3").who, "ann/claude (2026-01-02)")  # still Ann's, still open
        self.assertEqual(rb.find("F5").get("notes"), "Gap of F1")
        self.assertEqual(rb.status(rb.find("F4")), "ready")              # F1 is done now
        self.assertEqual(git(self.remote, "log", "-1", "--format=%s", "main"), "done F1, F2")
        self.assertEqual(self.board("pending", cwd=self.a), 0)

    def test_two_agents_racing_for_one_row(self):
        # Bob's clone is stale: Ann claims first, then Bob asks for the same row and another.
        self.assertEqual(self.board("claim", "F1", "--who", "ann/claude", cwd=self.a), 0)
        self.assertEqual(self.board("claim", "F1", "F2", "--who", "bob/claude", cwd=self.b), 0)
        rb = self.remote_board()
        self.assertEqual(rb.find("F1").who, "ann/claude (2026-01-02)")
        self.assertEqual(rb.find("F2").who, "bob/claude (2026-01-02)")

    def test_done_needs_a_commit_for_the_row(self):
        self.assertEqual(self.board("claim", "F1", "--who", "ann/claude", cwd=self.a), 0)
        self.assertEqual(self.board("done", "F1", cwd=self.a), 2)
        self.assertEqual(self.board("done", "F1", "--no-commit", cwd=self.a), 0)
        self.assertEqual(self.board("land", cwd=self.a), 0)
        self.assertTrue(self.remote_board().find("F1").done)


if __name__ == "__main__":
    unittest.main()
