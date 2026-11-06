#!/usr/bin/env python3
# 지시서: specs/04-line-tracer.md · 1111 즉시 정지/최소 1초/연속 1초 도착 (2026-11-06)
# 바퀴·센서·카메라 없이 판단만 실행한다.
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "missions"))
from line import LineFollower, ZERO


class StopLineTest(unittest.TestCase):
    def test_overrides_every_manoeuvre(self):
        for state in ("follow", "pivot_entry", "pivot", "search", "gap", "odd", "crab"):
            with self.subTest(state=state):
                f = LineFollower(60)
                f.state, f.last_dir, f.pivot_dir = state, "L", "L"
                wheels, _, why = f.step("1111", 10.0)
                self.assertEqual(wheels, ZERO)
                self.assertIsNone(why)
                self.assertEqual(f.state, "all_black")

    def test_continuous_one_second_latches_finish(self):
        f = LineFollower(60)
        for t in (10.0, 10.2, 10.8, 10.999):
            wheels, _, why = f.step("1111", t)
            self.assertEqual(wheels, ZERO)
            self.assertIsNone(why)
        wheels, _, why = f.step("1111", 11.0)
        self.assertEqual(wheels, ZERO)
        self.assertIn("마지막 정지선", why)
        self.assertEqual(f.step("0110", 12.0)[0], ZERO)

    def test_short_mark_waits_minimum_and_discards_old_turn(self):
        f = LineFollower(60)
        f.step("1110", 9.8)
        f.step("0000", 9.95)
        f.step("1111", 10.0)
        for t in (10.1, 10.9, 10.999):
            self.assertEqual(f.step("0110", t)[0], ZERO)
        self.assertEqual(f.step("0110", 11.0)[0], (60,) * 4)
        self.assertEqual(f.state, "follow")

    def test_interruption_restarts_continuous_confirmation(self):
        f = LineFollower(60)
        f.step("1111", 10.0)
        f.step("0110", 10.5)
        for t in (10.75, 11.0, 11.74):
            wheels, _, why = f.step("1111", t)
            self.assertEqual(wheels, ZERO)
            self.assertIsNone(why)
        self.assertIn("마지막 정지선", f.step("1111", 11.75)[2])

    def test_cleared_mark_uses_current_sensor(self):
        f = LineFollower(60)
        f.last_dir = "L"
        f.step("1111", 10.0)
        f.step("0010", 10.4)
        self.assertEqual(f.step("0001", 11.0)[0], (60, 60, 0, 0))

    def test_sensor_failure_during_hold_is_terminal(self):
        f = LineFollower(60)
        f.step("1111", 10.0)
        self.assertEqual(f.step(None, 10.2)[2], "센서 읽기 실패")
        self.assertEqual(f.step("0110", 11.2)[0], ZERO)

    def test_can_start_on_mark_without_moving(self):
        f = LineFollower(60)
        self.assertTrue(f.start("1111")[0])
        self.assertEqual(f.step("1111", 10.0)[0], ZERO)

    def test_pause_does_not_hide_stop_line(self):
        f = LineFollower(60)
        f.pause(10.0)
        self.assertEqual(f.check_stop_line("1111", 10.0)[0], ZERO)
        self.assertIn("마지막 정지선", f.check_stop_line("1111", 11.0)[2])

    def test_hold_does_not_reset_search_budget(self):
        f = LineFollower(60)
        f.last_dir, f.search_used = "L", .8
        f.step("1111", 10.0)
        f.step("0110", 10.2)
        f.step("0110", 11.0)
        self.assertAlmostEqual(f.search_used, .8)


if __name__ == "__main__":
    unittest.main()
