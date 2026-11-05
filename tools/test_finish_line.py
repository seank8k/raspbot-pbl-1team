#!/usr/bin/env python3
# 지시서: specs/04-line-tracer.md 「마지막 구간 정지」. 바퀴 없이 판단만 시험.
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "missions"))
import line


class FinishLineTest(unittest.TestCase):
    def setUp(self):
        self.f = line.LineFollower(60)
        self.t = 0.0
        self.f.step("0110", self.t)

    def sample(self, pattern, dt=0.02):
        self.t += dt
        return self.f.step(pattern, self.t)

    def corner(self, pattern="1110"):
        self.sample(pattern)
        self.sample("0000", 0.12)
        self.sample("0110")
        return self.sample("0110")

    def final(self, arm=True):
        for _ in range(5):
            self.corner()
        if arm:
            self.sample("0110", 0.31)
            self.assertTrue(self.f.finish_armed)

    def test_count_only_completed_rotation(self):
        self.sample("1110")
        self.assertEqual(self.f.corner_count, 0)
        self.sample("0000", 0.12)
        self.sample("0110")
        self.assertEqual(self.f.corner_count, 0)
        self.sample("0110")
        self.assertEqual(self.f.corner_count, 1)
        for _ in range(5):
            self.sample("0110")
        self.assertEqual(self.f.corner_count, 1)

    def test_failed_corner_not_counted(self):
        self.sample("1110")
        self.sample("0000", 0.12)
        _, _, why = self.sample("0000", 1.51)
        self.assertIsNotNone(why)
        self.assertEqual(self.f.corner_count, 0)

    def test_search_recovery_not_counted(self):
        self.sample("0001")
        self.sample("0000")
        self.sample("0110")
        self.assertEqual(self.f.corner_count, 0)

    def test_fifth_corner_slows_immediately_and_caps_boost(self):
        for _ in range(4):
            self.corner()
        self.assertEqual(self.f.effective_speed, 60)
        wheels, _, _ = self.corner()
        self.assertEqual(self.f.corner_count, 5)
        self.assertEqual(wheels, (40, 40, 40, 40))
        self.f.speed = 90
        self.assertEqual(self.sample("0110")[0], (40, 40, 40, 40))

    def test_partial_stability_does_not_arm(self):
        self.final(arm=False)
        self.sample("0110", 0.2)
        self.assertFalse(self.f.finish_armed)
        self.sample("1000")
        self.sample("0110")
        self.sample("0110", 0.2)
        self.assertFalse(self.f.finish_armed)
        self.sample("0010", 0.11)
        self.assertTrue(self.f.finish_armed)

    def test_middle_course_black_still_uses_old_rule(self):
        for _ in range(4):
            self.corner()
        self.sample("1111")
        wheels, _, why = self.sample("1111")
        self.assertEqual(wheels, (60, 60, 60, 60))
        self.assertIsNone(why)

    def test_stop_after_two_black_samples(self):
        self.final()
        self.sample("1111")
        wheels, _, why = self.sample("1111")
        self.assertEqual(wheels, line.ZERO)
        self.assertIn("정지선", why)

    def test_real_short_black_pulse_during_entry(self):
        self.final()
        self.sample("1110")
        self.assertEqual(self.f.state, "pivot_entry")
        self.sample("1111", 0.026)
        wheels, _, why = self.sample("1111", 0.022)
        self.assertEqual(wheels, line.ZERO)
        self.assertIn("정지선", why)

    def test_black_priority_during_rotation_and_search(self):
        for state in ("pivot", "search"):
            with self.subTest(state=state):
                self.setUp()
                self.final()
                if state == "pivot":
                    self.sample("1110")
                    self.sample("0000", 0.12)
                else:
                    self.sample("0001")
                    self.sample("0000")
                self.assertEqual(self.f.state, state)
                self.sample("1111")
                wheels, _, why = self.sample("1111")
                self.assertEqual(wheels, line.ZERO)
                self.assertIn("정지선", why)

    def test_nonblack_resets_confirmation(self):
        self.final()
        self.sample("1111")
        self.sample("0110")
        _, _, why = self.sample("1111")
        self.assertIsNone(why)
        self.assertEqual(self.f.finish_black_run, 1)

    def test_pause_cannot_supply_center_hold_or_black_confirmation(self):
        self.final(arm=False)
        self.sample("0110", 0.2)
        self.f.pause(self.t)
        self.t += 5
        self.f.resume(self.t)
        self.sample("0110")
        self.assertFalse(self.f.finish_armed)
        self.sample("0110", 0.31)
        self.sample("1111")
        self.f.pause(self.t)
        self.t += 5
        self.f.resume(self.t)
        self.assertTrue(self.f.finish_armed)
        _, _, why = self.sample("1111")
        self.assertIsNone(why)
        self.assertEqual(self.f.finish_black_run, 1)
        self.assertEqual(self.f.corner_count, 5)

    def test_sensor_failure_remains_stop_and_new_run_resets(self):
        self.final()
        self.sample("1111")
        wheels, _, why = self.sample(None)
        self.assertEqual(wheels, line.ZERO)
        self.assertEqual(why, "센서 읽기 실패")
        fresh = line.LineFollower(60)
        self.assertEqual(fresh.corner_count, 0)
        self.assertFalse(fresh.finish_armed)
        self.assertEqual(fresh.effective_speed, 60)


if __name__ == "__main__":
    unittest.main()
