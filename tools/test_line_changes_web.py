#!/usr/bin/env python3
# 지시서: specs/04-line-tracer.md · specs/05-obstacle-stop.md
# 웹 제어의 라인 판단 통합 시험. --dry · 카메라/인식 끔으로 불러오며 서버와 바퀴는 실행하지 않음.
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "missions"))
sys.argv = [sys.argv[0], "--dry", "--no-camera", "--no-detect"]
import webabb as web


class LineChangesTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(web.args.dry)
        self.assertFalse(web.camera.enabled)
        self.assertFalse(web.vision.enabled)
        self.logs = []
        web.log = self.logs.append
        self.ctl = web.Controller()
        self.ctl.judge.on_time = 0.0
        self.s = dict(gen=1, press=1)
        self.step("0110", 600, 10.0)

    def step(self, pattern, distance, now):
        web.motors.dry_line = None if pattern is None else web.line_encode(pattern)
        web.motors.dry_ultra = distance
        return self.ctl._line("any", self.s, now)

    def test_right_loss_searches_right(self):
        self.step("0001", 600, 10.02)
        _, wheels, why = self.step("0000", 600, 10.04)
        self.assertEqual(wheels, (40, 40, -40, -40))
        self.assertIsNone(why)

    def test_obstacle_overrides_corner_entry(self):
        _, wheels, _ = self.step("1110", 600, 10.02)
        self.assertEqual(wheels, (40, 40, 40, 40))
        _, wheels, why = self.step("0000", 136, 10.04)
        self.assertEqual(wheels, web.ZERO)
        self.assertIsNone(why)
        self.assertIsNotNone(self.ctl.follower.paused_at)

    def test_search_follows_opposite_sensor_without_new_budget(self):
        self.step("1000", 600, 10.02)
        self.step("0000", 600, 10.04)
        _, wheels, why = self.step("0001", 600, 10.10)
        self.assertEqual(wheels, (40, 40, -40, -40))
        self.assertIsNone(why)
        self.assertEqual(self.ctl.follower.state, "search")
        self.assertGreater(self.ctl.follower.search_used, 0)
        _, wheels, why = self.step("0000", 136, 10.12)
        self.assertEqual(wheels, web.ZERO)
        self.assertIsNone(why)

    def test_controller_writes_equal_values_after_line_pivot(self):
        self.ctl.driver = "any"
        self.ctl.out = (-40, -40, 40, 40)
        state = dict(self.s, kind="line")
        with patch.object(self.ctl, "_gestures"), patch.object(self.ctl, "_alerts"), \
                patch.object(self.ctl, "_live", return_value=("ok", state)), \
                patch.object(self.ctl, "_line", return_value=("라인: 앞으로", (60,) * 4, None)), \
                patch.object(web.wishes["any"], "need_new_press", return_value=False), \
                patch.object(web.motors, "write", return_value=[]) as write:
            self.ctl.tick()
        write.assert_called_once_with((12,) * 4)
        self.assertEqual(self.ctl.out, (12,) * 4)

    def test_stop_line_overrides_corner_and_finishes(self):
        self.step("1110", 600, 10.02)
        for t in (10.04, 10.2, 10.8, 11.03):
            _, wheels, why = self.step("1111", 600, t)
            self.assertEqual(wheels, web.ZERO)
            self.assertIsNone(why)
        _, wheels, why = self.step("1111", 600, 11.05)
        self.assertEqual(wheels, web.ZERO)
        self.assertIn("마지막 정지선", why)

    def test_short_stop_line_waits_before_following(self):
        self.step("1111", 600, 10.02)
        for t in (10.1, 10.9, 11.01):
            _, wheels, why = self.step("0110", 600, t)
            self.assertEqual(wheels, web.ZERO)
            self.assertIsNone(why)
        self.assertEqual(self.step("0110", 600, 11.03)[1], (60,) * 4)

    def test_stop_line_observed_while_obstacle_remains(self):
        self.step("0110", 136, 10.02)
        _, wheels, why = self.step("1111", 136, 10.04)
        self.assertEqual(wheels, web.ZERO)
        self.assertIsNone(why)
        _, wheels, why = self.step("1111", 136, 11.05)
        self.assertEqual(wheels, web.ZERO)
        self.assertIn("마지막 정지선", why)

    def test_cleared_stop_line_does_not_override_obstacle(self):
        self.step("1111", 136, 10.02)
        for t in (10.1, 10.9, 11.1):
            _, wheels, why = self.step("0110", 136, t)
            self.assertEqual(wheels, web.ZERO)
            self.assertIsNone(why)

    def test_finish_invalidates_current_line_press(self):
        self.ctl.driver = "any"
        web.motors.dry_line = web.line_encode("1111")
        state = dict(self.s, kind="line")
        with patch.object(self.ctl, "_gestures"), patch.object(self.ctl, "_alerts"), \
                patch.object(self.ctl, "_live", return_value=("ok", state)), \
                patch.object(web.wishes["any"], "raise_floor") as invalidate, \
                patch.object(web.motors, "write", return_value=[]), \
                patch.object(web.time, "monotonic", return_value=10.02) as now:
            self.ctl.tick()
            invalidate.assert_not_called()
            now.return_value = 11.03
            self.ctl.tick()
        invalidate.assert_called_once_with(self.s["press"])
        self.assertIsNone(self.ctl.driver)
        self.assertIn("마지막 정지선", self.ctl.reason)

    def test_entry_sensor_failure_stops(self):
        self.step("1110", 600, 10.02)
        _, wheels, why = self.step(None, 600, 10.04)
        self.assertEqual(wheels, web.ZERO)
        self.assertIn("센서", why)

    def test_third_loss_can_recover_without_turning_line_off(self):
        self.ctl.follower.losses.extend([8.0, 9.0])
        self.step("0001", 600, 10.02)
        self.step("0000", 600, 10.04)
        _, wheels, why = self.step("0000", 600, 10.16)
        self.assertEqual(wheels, (40, 40, -40, -40))
        self.assertIsNone(why)
        self.assertEqual(len(self.ctl.follower.losses), 3)
        _, wheels, why = self.step("0110", 600, 10.18)
        self.assertEqual(wheels, (60,) * 4)
        self.assertIsNone(why)

    def test_far_distance_logged_then_resumes_after_one_second(self):
        self.step("0110", 136, 10.02)
        self.logs.clear()
        for i in range(1, 51):
            _, wheels, why = self.step("0110", 1200, 10.02 + i * 0.02)
            self.assertEqual(wheels, web.ZERO)
            self.assertIsNone(why)
        records = [s for s in self.logs if s.startswith("OBST 대기:")]
        self.assertTrue(4 <= len(records) <= 6, records)
        self.assertTrue(all("1200mm" in s and "치워짐 확인" in s for s in records))
        self.step("0110", 1200, 11.04)
        _, wheels, why = self.step("0110", 1200, 11.08)
        self.assertEqual(wheels, (60,) * 4)
        self.assertIsNone(why)

    def test_out_of_range_still_blocks_restart(self):
        self.step("0110", 119, 10.02)
        for i in range(1, 70):
            _, wheels, why = self.step("0110", 5001, 10.02 + i * .02)
            self.assertEqual(wheels, web.ZERO)
            self.assertIsNone(why)

    def test_40cm_clear_waits_one_second_and_discards_entry(self):
        self.step("1110", 600, 10.02)
        self.step("0110", 136, 10.04)
        for i in range(50):
            _, wheels, _ = self.step("0110", 400, 10.06 + i * 0.02)
            self.assertEqual(wheels, web.ZERO)
        self.step("0110", 400, 11.08)
        _, wheels, why = self.step("0110", 400, 11.10)
        self.assertEqual(wheels, (60, 60, 60, 60))
        self.assertEqual(self.ctl.follower.state, "follow")
        self.assertIsNone(why)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
