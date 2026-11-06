#!/usr/bin/env python3
# 지시서: specs/01-webabb.md 「안전 — 출발 · 가속은 서서히」 (2026-11-06) — webabb.ramp 시험 (바퀴 안 씀 · 라즈봇에서)
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "missions"))
sys.argv = [sys.argv[0], "--dry", "--no-camera", "--no-detect"]
import webabb as web


class RampTest(unittest.TestCase):
    def walk(self, start, want, n):
        out, cur = [], start
        for _ in range(n):
            cur = web.ramp(cur, want)
            out.append(cur)
        return out

    def test_start_from_zero_rises_by_step(self):
        seq = self.walk(web.ZERO, (120, 120, 120, 120), 11)
        self.assertEqual(seq[0], (12, 12, 12, 12))
        self.assertEqual(seq[4], (60, 60, 60, 60))
        self.assertEqual(seq[9], (120, 120, 120, 120))
        self.assertEqual(seq[10], (120, 120, 120, 120))

    def test_stop_is_immediate(self):
        self.assertEqual(web.ramp((120, 120, 120, 120), web.ZERO), web.ZERO)

    def test_line_pivot_exit_has_no_left_right_difference(self):
        for start in ((-40, -40, 40, 40), (40, 40, -40, -40), (60, 60, 0, 0)):
            cur = start
            for _ in range(5):
                prev = cur
                cur = web.ramp(cur, (60, 60, 60, 60), straight=True)
                self.assertEqual(len(set(cur)), 1)
                self.assertTrue(0 < cur[0] <= 60)
                for old, new in zip(prev, cur):
                    self.assertLessEqual(new, max(0, old) + web.RAMP_STEP)
            self.assertEqual(cur, (60, 60, 60, 60))

    def test_line_stop_and_turn_keep_existing_rules(self):
        self.assertEqual(web.ramp((-40, -40, 40, 40), web.ZERO, straight=True), web.ZERO)
        self.assertEqual(web.ramp((60, 60, 60, 60), (60, 60, 30, 30), straight=True), (60, 60, 30, 30))
        self.assertEqual(web.ramp((60, 60, 60, 60), (-40, -40, 40, 40), straight=True), (-12, -12, 40, 40))

    def test_slow_down_is_immediate(self):
        self.assertEqual(web.ramp((60, 60, 60, 60), (60, 60, 30, 30)), (60, 60, 30, 30))
        self.assertEqual(web.ramp((60, 60, 60, 60), (60, 60, 0, 0)), (60, 60, 0, 0))

    def test_reverse_goes_through_zero_then_rises(self):
        seq = self.walk((60, 60, 60, 60), (-40, -40, 40, 40), 4)
        self.assertEqual(seq[0], (-12, -12, 60, 60) if False else (-12, -12, 40, 40))
        self.assertEqual(seq[3], (-40, -40, 40, 40))

    def test_unknown_current_starts_from_zero(self):
        self.assertEqual(web.ramp(None, (60, 60, 60, 60)), (12, 12, 12, 12))

    def test_never_exceeds_target(self):
        for start in (web.ZERO, (30, -30, 30, -30), (150, 150, 150, 150)):
            for want in ((60, 60, 30, 30), (-120, 120, 120, -120), (40, 40, -40, -40)):
                cur = start
                for _ in range(20):
                    cur = web.ramp(cur, want)
                    for c, w in zip(cur, want):
                        self.assertLessEqual(abs(c), max(abs(w), 0))
                self.assertEqual(cur, want)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
