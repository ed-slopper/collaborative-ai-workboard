import unittest

from workboard.board import Board, BoardError, split_row

SAMPLE = """# Board

## P0 Foundations

| ID | Task | Area | Needs | Who | Notes |
|---|---|---|---|---|---|
| F1 | Name the functions | any | F3 | sam/claude (2026-01-02) |
| F2 | Pick the reference | humans | | | |
| F4 | Replay test | unowned | F1, F11 | | Gap of F1 |

## P1 Engine

| ID | Task | Area | Needs | Who | Notes |
|---|---|---|---|---|---|
| E1 | Main loop | any | | | |
| E2 | Read the disc: the `|name` / `archive|name` rules | any | F11 | | |
| E3 | Everything in content | any | C1–C2 | | |

## P2 Content

| ID | Task | Area | Needs | Who | Notes |
|---|---|---|---|---|---|
| C1 | First course | any | | | |
| C2 | Second course | any | E1 | | |

## Done

| ID | Task | Section | Who | Date | Commit |
|---|---|---|---|---|---|
| F3 | Tooling | P0 | sam | 2026-01-01 | abc1234 |
| F11a | Split crate, part one | P0 | sam | 2026-01-01 | abc1235 |
| F11b | Split crate, part two | P0/P1 | sam | 2026-01-01 | abc1236 |

## Changes to the board

- 2026-01-01 sam: board created.
"""


def board(text=SAMPLE):
    return Board(text)


class Reading(unittest.TestCase):
    def test_pipe_inside_backticks_stays_in_the_cell(self):
        cells = split_row("| E2 | the `|name` / `a|b` rules | any |")
        self.assertEqual(cells, ["E2", "the `|name` / `a|b` rules", "any"])

    def test_sections_and_rows(self):
        b = board()
        self.assertEqual([s.key for s in b.sections], ["P0", "P1", "P2"])
        self.assertEqual(len(b.open_rows), 8)
        self.assertEqual(len(b.done_rows), 3)
        self.assertEqual(b.find("F11b").section, "P0")  # filed under two sections: the first
        self.assertEqual(b.problems, [])

    def test_status(self):
        b = board()
        status = {r.id: b.status(r) for r in b.rows}
        self.assertEqual(status["F1"], "progress")
        self.assertEqual(status["F2"], "decision")
        self.assertEqual(status["F4"], "blocked")      # F1 is still open
        self.assertEqual(status["E1"], "ready")
        self.assertEqual(status["E2"], "ready")        # F11 was split; both parts are done
        self.assertEqual(status["E3"], "blocked")      # a range with open rows
        self.assertEqual(status["C2"], "blocked")
        self.assertEqual(status["F3"], "done")

    def test_ready_is_in_board_order_and_respects_area(self):
        b = board()
        self.assertEqual([r.id for r in b.ready()], ["E1", "E2", "C1"])
        self.assertEqual([r.id for r in b.ready("alex")], ["E1", "E2", "C1"])


class Changing(unittest.TestCase):
    def test_claim_writes_who_and_keeps_other_lines(self):
        b = board()
        before = list(b.lines)
        b.claim("E1", "alex/claude", "2026-01-03")
        self.assertEqual(b.find("E1").who, "alex/claude (2026-01-03)")
        changed = [i for i, (x, y) in enumerate(zip(before, b.lines)) if x != y]
        self.assertEqual(len(changed), 1)

    def test_claim_refuses_taken_blocked_and_human_rows(self):
        b = board()
        for rid in ("F1", "F4", "F2", "F3"):
            with self.assertRaises(BoardError):
                b.claim(rid, "alex/claude")
        b.claim("F4", "alex/claude", force=True)

    def test_finish_moves_the_row_to_done(self):
        b = board()
        b.claim("E1", "alex/claude", "2026-01-03")
        b.finish("E1", "def5678", date="2026-01-04", summary="Loop at 60 Hz")
        row = b.find("E1")
        self.assertTrue(row.done)
        self.assertEqual((row.section, row.who, row.get("commit")), ("P1", "alex/claude", "def5678"))
        self.assertEqual(row.task, "Loop at 60 Hz")
        self.assertEqual(b.status(b.find("C2")), "ready")  # E1 was its only need

    def test_add_takes_the_next_free_id_of_the_section(self):
        b = board()
        self.assertEqual(b.add("P0", "A gap", notes="Gap of F1"), "F12")
        self.assertEqual(b.add("Content", "Third course"), "C3")
        self.assertEqual(b.find("F12").section, "P0")
        with self.assertRaises(BoardError):
            b.add("P0", "again", rid="F3")

    def test_release_and_log(self):
        b = board()
        b.release("F1", "half done")
        self.assertEqual(b.find("F1").who, "")
        self.assertIn("half done", b.find("F1").get("notes"))
        b.log("F1 released.", "sam", "2026-01-05")
        self.assertEqual(b.lines[b.log_last], "- 2026-01-05 sam: F1 released.")

    def test_text_round_trips(self):
        self.assertEqual(board().text, SAMPLE)


class Checking(unittest.TestCase):
    def test_clean_board(self):
        errors, warnings = board().check(stale_days=2, now="2026-01-03")
        self.assertEqual((errors, warnings), ([], []))

    def test_finds_mistakes(self):
        text = SAMPLE.replace("| C1 | First course | any | |", "| C1 | First course | any | Z9 |")
        text = text.replace("| E1 | Main loop", "| F3 | Main loop")
        errors, warnings = Board(text).check(stale_days=2, now="2026-02-01")
        self.assertTrue(any("Z9" in e for e in errors))
        self.assertTrue(any("F3 appears 2 times" in e for e in errors))
        self.assertTrue(any("F1" in w and "days ago" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
