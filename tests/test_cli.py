import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from crossword_builder.cli import main

WORDLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tiny_wordlist.txt")


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.tmp = self._dir.name

    def _write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_fill_then_show(self):
        template = self._write("template.txt", "#...\n....\n....\n...#\n")
        out_dir = os.path.join(self.tmp, "out")
        code, out, err = run_cli(
            "fill", template, "--wordlist", WORDLIST, "--workers", "1", "--out", out_dir, "--quiet"
        )
        self.assertEqual((code, out, err), (0, "", ""))

        with open(os.path.join(out_dir, "solutions.txt"), encoding="utf-8") as f:
            blocks = [b for b in f.read().split("\n\n") if b.strip()]
        self.assertEqual(len(blocks), 4)
        self.assertIn("█ORE\nAREA\nSCAR\nHAD█", blocks)

        code, out, _ = run_cli("show", os.path.join(out_dir, "combined.json"))
        self.assertEqual(code, 0)
        self.assertIn("█ASH\nORCA\nREAM\nEAR█", out)
        self.assertIn("4 grid(s)", out)

        # running again without --resume or --overwrite is refused
        code, _, err = run_cli(
            "fill", template, "--wordlist", WORDLIST, "--workers", "1", "--out", out_dir, "--quiet"
        )
        self.assertEqual(code, 2)
        self.assertIn("--resume", err)

    def test_fill_with_bad_pairs_file(self):
        template = self._write("template.txt", "#...\n....\n....\n...#\n")
        bad_pairs = self._write("bad_pairs.txt", "HAM ORCA\n")
        out_dir = os.path.join(self.tmp, "out")
        code, _, _ = run_cli(
            "fill", template, "--wordlist", WORDLIST, "--bad-pairs", bad_pairs,
            "--workers", "1", "--out", out_dir, "--quiet",
        )
        self.assertEqual(code, 0)
        with open(os.path.join(out_dir, "solutions.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(len([b for b in text.split("\n\n") if b.strip()]), 2)
        self.assertNotIn("HAM", text)

    def test_check(self):
        good = self._write("good.txt", "#ORE\nAREA\nSCAR\nHAD#\n")
        code, out, _ = run_cli("check", good, "--wordlist", WORDLIST)
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

        bad = self._write("bad.txt", "#ORE\nAREA\nSCAR\nHAT#\n")
        code, out, _ = run_cli("check", bad, "--wordlist", WORDLIST)
        self.assertEqual(code, 1)
        self.assertIn("HAT", out)
        self.assertIn("REAT", out)

    def test_ragged_template_is_reported(self):
        template = self._write("ragged.txt", "#...\n...\n....\n...#\n")
        code, _, err = run_cli(
            "fill", template, "--wordlist", WORDLIST, "--workers", "1",
            "--out", os.path.join(self.tmp, "out"), "--quiet",
        )
        self.assertEqual(code, 2)
        self.assertIn("line 2", err)

    def test_seed(self):
        template = self._write("template.txt", "#...\n....\n....\n...#\n")
        code, out, _ = run_cli("seed", template, "--place", "1,0,across,AREA")
        self.assertEqual(code, 0)
        self.assertEqual(out, "█...\nAREA\n....\n...█\n")


if __name__ == "__main__":
    unittest.main()
