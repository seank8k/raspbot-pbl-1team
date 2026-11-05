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
        self.step("0110", 600, 9.4)  # 서보 정렬 시작 · 바퀴0 · 0.5초 대기
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

    def test_camera_aligns_each_new_press_before_moving(self):
        self.s["press"] = 2
        with patch.object(web.motors, "write_reg", return_value=True) as command:
            _, wheels, why = self.step("0110", 600, 10.02)
            self.assertEqual(wheels, web.ZERO)
            self.assertIsNone(why)
            self.assertIsNone(self.ctl.follower)
            command.assert_called_once_with(0x02, [2, 45])
            _, wheels, _ = self.step("0110", 600, 10.50)
            self.assertEqual(wheels, web.ZERO)
            _, wheels, _ = self.step("0110", 600, 10.54)
            self.assertEqual(wheels, (60, 60, 60, 60))
            command.assert_called_once()
            self.s["press"] = 3
            _, wheels, _ = self.step("0110", 600, 10.56)
            self.assertEqual(wheels, web.ZERO)
            self.assertEqual(command.call_count, 2)

    def test_camera_command_failure_blocks_start(self):
        self.s["press"] = 2
        with patch.object(web.motors, "write_reg", return_value=False):
            _, wheels, why = self.step("0110", 600, 10.02)
        self.assertEqual(wheels, web.ZERO)
        self.assertIn("카메라", why)

    def test_camera_wait_does_not_bypass_fresh_obstacle_check(self):
        self.s["press"] = 2
        self.step("0110", 600, 10.02)
        _, wheels, why = self.step("0110", 136, 10.54)
        self.assertEqual(wheels, web.ZERO)
        self.assertIn("장애물", why)

    def test_blocked_crab_restart_is_not_logged_as_departure(self):
        self.ctl.follower.losses.extend([9.0, 9.5])
        self.step("0110", 136, 10.02)
        self.step("0000", 400, 10.04)
        _, wheels, why = self.step("0000", 400, 11.10)
        self.assertEqual(wheels, web.ZERO)
        self.assertIn("3번", why)
        self.assertTrue(any("OBST 재출발 취소" in s for s in self.logs))
        self.assertFalse(any("OBST 다시 출발" in s for s in self.logs))

    def test_final_corner_cap_logs_and_short_finish_pulse(self):
        self.ctl.follower.corner_count = 4
        self.step("1110", 600, 10.02)
        self.step("0000", 600, 10.14)
        self.step("0110", 600, 10.16)
        _, wheels, _ = self.step("0110", 600, 10.18)
        self.assertEqual(wheels, (40, 40, 40, 40))
        self.assertEqual(self.ctl.line_speed, 40)
        self.assertTrue(any("코너 통과: 5/5" in s for s in self.logs))
        self.step("0110", 600, 10.50)
        self.assertTrue(any("정지선 감지 준비" in s for s in self.logs))
        self.step("1110", 600, 10.52)
        self.step("1111", 600, 10.546)
        _, wheels, why = self.step("1111", 600, 10.568)
        self.assertEqual(wheels, web.ZERO)
        self.assertIn("정지선", why)

    def test_final_speed_boost_remains_capped(self):
        self.ctl.follower.corner_count = 5
        self.step("0110", 600, 10.02)
        self.ctl.follower.speed = 90
        _, wheels, _ = self.step("0110", 600, 10.04)
        self.assertEqual(wheels, (40, 40, 40, 40))
        self.assertEqual(self.ctl.line_speed, 40)

    def test_obstacle_overrides_corner_entry(self):
        _, wheels, _ = self.step("1110", 600, 10.02)
        self.assertEqual(wheels, (40, 40, 40, 40))
        _, wheels, why = self.step("0000", 136, 10.04)
        self.assertEqual(wheels, web.ZERO)
        self.assertIsNone(why)
        self.assertIsNotNone(self.ctl.follower.paused_at)

    def test_entry_sensor_failure_stops(self):
        self.step("1110", 600, 10.02)
        _, wheels, why = self.step(None, 600, 10.04)
        self.assertEqual(wheels, web.ZERO)
        self.assertIn("센서", why)

    def test_far_distance_logged_and_wait_remains(self):
        self.step("0110", 136, 10.02)
        self.logs.clear()
        for i in range(1, 61):
            _, wheels, why = self.step("0110", 1200, 10.02 + i * 0.02)
            self.assertEqual(wheels, web.ZERO)
            self.assertIsNone(why)
        records = [s for s in self.logs if s.startswith("OBST 대기:")]
        self.assertTrue(4 <= len(records) <= 6, records)
        self.assertTrue(all("1200mm" in s and "800mm 초과" in s for s in records))

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
