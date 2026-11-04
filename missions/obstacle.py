#!/usr/bin/env python3
# 지시서: specs/05-obstacle-stop.md  (Codex 적대적 리뷰 반영 · 조원 결정 2026-11-03 · 11-04)
# 장애물 「판단」만 한다. 바퀴 · I2C 를 모른다.
#   초음파 읽기 결과(mm · 버림 · 실패) + 지금 시각 → 상태(달림 / 잠깐 멈춤 / 치워짐 / 센서 실패) + 이유
# 웹 조종(missions/webabb.py)의 제어 스레드가 라인 모드일 때 0.02초마다 부르고, 07 자율주행에서도 그대로 쓴다.

# ---------------- 지시서 값 ----------------
STOP_MM = 150          # 이하면 잠깐 멈춤 (읽기 한 번이라도 · 0 = 아주 가까움도 포함)
CLEAR_MM = 200         # 넘어야 「치워짐」으로 셈 (5cm 여유)
CLEAR_HOLD = 1.0       # 치워짐이 이만큼 계속되면 출발 가능
GAP_MAX = 0.1          # 읽기 공백(실패 · 섞여서 버림)이 이보다 길면 치워짐 1초를 처음부터 (Q1 결정)
MAX_KNOWN = 800        # 2026-11-04 측정에서 본 값은 0~765mm → 이보다 크면 뜻을 모르는 값 (출발 허락에서 뺌)
READY_S = 1.0          # 초음파를 켠 뒤 이만큼 + 새 값 한 번 이상 받아야 준비 끝

RUN, PAUSE, CLEAR, FAIL, NOT_READY = "run", "pause", "clear", "fail", "not_ready"


class ObstacleJudge:
    def __init__(self, on_time):
        self.on_time = on_time        # 초음파를 켠 시각
        self.ready = False
        self.reset()

    def reset(self):
        """라인을 켤 때마다 · 라인이 꺼질 때마다 — 타이머 · 상태를 모두 지운다 (#15)."""
        self.state = RUN
        self.clear_since = None
        self.last_ok = None           # 마지막으로 쓸 수 있는 값을 받은 시각
        self.mm = None
        self.paused_at = None

    def update(self, kind, mm, now):
        """kind: 'ok'(mm 있음) · 'torn'(상위 바이트가 달라 버림) · 'fail'(읽기 실패).
        돌려줌: (상태, 이유 또는 None, 치워짐까지 남은 초 또는 None)"""
        if kind == "fail":
            return FAIL, "초음파 읽기 실패", None
        if kind == "ok":
            self.mm = mm
            if not self.ready and now - self.on_time >= READY_S:
                self.ready = True
        if not self.ready:
            return NOT_READY, "초음파 준비 중", None

        gap_too_long = self.last_ok is not None and now - self.last_ok > GAP_MAX
        if kind == "ok":
            self.last_ok = now

        if self.state == RUN:
            if kind == "ok" and mm <= STOP_MM:
                self.state, self.paused_at, self.clear_since = PAUSE, now, None
                return PAUSE, f"장애물 {mm / 10:.1f}cm", None
            return RUN, None, None

        # 잠깐 멈춤 중
        if kind != "ok":                              # 섞여서 버린 읽기: 공백이 0.1초를 넘으면 1초를 처음부터
            if self.last_ok is None or now - self.last_ok > GAP_MAX:
                self.clear_since = None
            return PAUSE, self._why(), None
        if gap_too_long:
            self.clear_since = None
        if CLEAR_MM < mm <= MAX_KNOWN:
            if self.clear_since is None:
                self.clear_since = now
            left = CLEAR_HOLD - (now - self.clear_since)
            if left <= 0:
                return CLEAR, None, 0.0
            return PAUSE, self._why(), left
        self.clear_since = None                       # 20cm 이하 · 뜻 모르는 값 → 1초를 처음부터
        return PAUSE, self._why(), None

    def _why(self):
        return "장애물" + ("" if self.mm is None else f" {self.mm / 10:.1f}cm") + " · 잠깐 멈춤"

    def resumed(self):
        """다시 출발했을 때 — 달림 상태로."""
        self.state, self.clear_since, self.paused_at = RUN, None, None
