#!/usr/bin/env python3
# 지시서: specs/04-line-tracer.md  (Codex 적대적 리뷰 반영판 · 2026-11-03 · 뒤로 찾기 뺌 · 칸 사이 틈 규칙 2026-11-04)
# 라인 따라가기 「판단」만 한다. 바퀴 · I2C 를 모른다.
#   센서 4칸(또는 None = 읽기 실패) + 지금 시각 → (네 바퀴 값, 지금 동작 이름, 멈춘 이유 또는 None)
# 웹 조종(missions/webabb.py)의 제어 스레드가 0.02초마다 부르고, 07 자율주행에서도 그대로 쓴다.
from collections import deque

# ---------------- 라인센서 대응 (시작 전 조건 1 · 2026-11-04 확인) ----------------
# 왼쪽부터 x2 · x1 · x3 · x4, 값 0 = 검은 줄
SENSOR_ORDER = ("x2", "x1", "x3", "x4")   # 왼바 · 왼안 · 오안 · 오바
BLACK_VALUE = 0

# ---------------- 지시서 값 (고정 한계는 지시서부터 바꾼다) ----------------
TURN_SEARCH = 1.0        # 줄 놓침 회전 찾기 = 찾기 합계 최대 (조원 결정 · 1.5 → 0.7 → 1.0초 · 뒤로는 안 감 2026-11-04)
TURN_SPEED = 40          # 제자리 회전(크게 꺾임 · 줄 찾기) 속도 — 빠르면 줄이 가운데를 지나쳐 못 잡음 (조원 결정 2026-11-04)
# 지시서 05 「옆걸음 찾기」: 장애물을 치웠는데 줄이 안 보일 때 (조원 결정 2026-11-04 · 숫자는 Claude 제안)
CRAB_SPEED = 55                          # 70은 빠름 → 55 (조원 결정 2026-11-04)
CRAB_STEPS = ((0.3, "L"), (0.6, "R"))    # 항상 왼쪽 ≈1cm → 오른쪽 ≈2cm (속도를 낮춘 만큼 시간을 늘림 · 실물에서 거리 재서 맞춤)
CRAB_SIGNS = {"L": (-1, 1, 1, -1), "R": (1, -1, -1, 1)}   # 옆왼 -++- · 옆오 +--+ (AGENTS.md)
GAP_MAX = 0.3            # 칸 사이 틈: 안쪽 칸 바로 뒤 0000 → 그쪽으로 세게 꺾기 최대 (조원 결정 · 값은 Claude 제안)
PIVOT_MAX = 1.5          # 크게 꺾임 제자리 회전 최대
ALL_BLACK_MAX = 0.3      # 1111 앞으로 최대 (고정 한계 · 조원 결정)
ODD_HOLD = 0.1           # 이상한 모양 직전 동작 유지 최대
CENTER_CONFIRM = 2       # 가운데 칸이 연속 이만큼 보여야 「다시 잡음」
STABLE_RESET = 0.5       # 따라가기로 이만큼 안정적으로 달려야 찾기 2초가 새로 생김
LOSS_WINDOW, LOSS_MAX = 10.0, 3   # 10초 안에 줄 놓침 3번 → 정지
GENTLE, HARD = 0.5, 0.0  # 완만 / 세게 돌 때 안쪽 바퀴 비율 (바꿔 볼 값)

CENTER = {"0110", "0100", "0010"}
BIG_LEFT, BIG_RIGHT = {"1100", "1110"}, {"0011", "0111"}
ODD = {"1001", "1010", "0101", "1011", "1101"}
ZERO = (0, 0, 0, 0)


def decode(byte):
    """레지스터 0x0a 한 바이트 → '왼바왼안오안오바' 4글자 (1 = 검은 줄). byte 가 None 이면 None."""
    if byte is None:
        return None
    bits = {"x1": (byte >> 3) & 1, "x2": (byte >> 2) & 1, "x3": (byte >> 1) & 1, "x4": byte & 1}
    return "".join("1" if bits[k] == BLACK_VALUE else "0" for k in SENSOR_ORDER)


def encode(pattern):
    """decode 의 반대 (바퀴 없이 시험할 때 가짜 센서 값을 만들려고)."""
    bits = {k: (BLACK_VALUE if c == "1" else 1 - BLACK_VALUE) for k, c in zip(SENSOR_ORDER, pattern)}
    return (bits["x1"] << 3) | (bits["x2"] << 2) | (bits["x3"] << 1) | bits["x4"]


class LineFollower:
    def __init__(self, speed):
        self.speed = speed
        self.state = "follow"     # follow · gap · pivot · all_black · odd · search · stopped
        self.last_dir = None      # "L" / "R" — 켤 때마다 지움
        self.last_pattern = None  # 바로 앞 읽기의 모양 (칸 사이 틈 판단용)
        self.gap_dir = None
        self.t_state = 0.0        # 지금 상태(크게 꺾임 · 1111 · 이상한 모양)를 시작한 시각
        self.pivot_dir = None
        self.center_run = 0
        self.search_used = 0.0    # 이번 줄 놓침에서 찾기에 쓴 시간 (중간에 잠깐 보여도 안 지움)
        self.follow_since = None
        self.losses = deque()
        self.prev_t = None
        self.out = ZERO
        self.reason = None

    # ---------------- 바퀴 값 (왼앞, 왼뒤, 오앞, 오뒤) ----------------
    def _w(self, left, right):
        s = self.speed
        return (round(s * left), round(s * left), round(s * right), round(s * right))

    def _stop(self, why):
        self.state, self.reason, self.out = "stopped", why, ZERO
        return ZERO, "정지", why

    def _go(self, wheels, name):
        self.out = wheels
        return wheels, name, None

    # ---------------- 켤 때 ----------------
    def start(self, pattern):
        """켜는 순간 검사. (출발 가능?, 이유)"""
        if pattern is None:
            return False, "센서 읽기 실패"
        if pattern not in CENTER:
            return False, "줄 위에 올려 주세요 (가운데 칸이 줄 위여야 출발)"
        return True, None

    # ---------------- 장애물 잠깐 멈춤 (지시서 05 #10 · #11) ----------------
    def pause(self, now):
        """장애물로 잠깐 멈춤 — 이 시각부터 라인 판단의 시간을 멈춘다."""
        if getattr(self, "paused_at", None) is None:
            self.paused_at = now

    def resume(self, now):
        """다시 출발 — 멈춘 시간만큼 시각을 뒤로 민다. 찾기 · 크게 꺾임 · 틈 같은 동작은 버리고,
        마지막 방향과 줄 놓침 기록(10초 3번)은 남긴다."""
        p = getattr(self, "paused_at", None)
        if p is None:
            return
        d = max(0.0, now - p)
        self.paused_at = None
        self.losses = type(self.losses)(t + d for t in self.losses)
        self.prev_t = now
        self.state, self.search_used, self.follow_since = "follow", 0.0, None
        self.center_run, self.last_pattern, self.gap_dir, self.pivot_dir = 0, None, None, None

    def crab_search(self, now):
        """장애물을 치웠는데 줄이 안 보임(0000) → 옆걸음 찾기: 항상 왼쪽 1cm → 오른쪽 2cm (지시서 05 · 줄 놓침 1번으로 셈)."""
        why = self._count_loss(now)
        if why:
            self._stop(why)
            return
        self.state, self.t_state, self.follow_since = "crab", now, None

    def _crab(self, pattern, now):
        if pattern in CENTER:                         # 가운데 칸이 보이면 바로 따라가기
            self._to_follow(now)
            return None
        if pattern == "1111":
            return self._stop("옆걸음 찾기 중 네 칸 모두 검음")
        t = now - self.t_state
        for dur, d in CRAB_STEPS:
            if t < dur:
                s = min(CRAB_SPEED, 150)
                return self._go(tuple(s * x for x in CRAB_SIGNS[d]),
                                f"옆걸음 찾기: {'왼쪽' if d == 'L' else '오른쪽'} {now - self.t_state:.2f}초")
            t -= dur
        return self._stop(f"옆걸음 찾기 {sum(x[0] for x in CRAB_STEPS):.1f}초 동안 줄을 못 찾음")

    # ---------------- 0.02초마다 ----------------
    def step(self, pattern, now):
        dt = 0.0 if self.prev_t is None else max(0.0, now - self.prev_t)
        self.prev_t = now
        if self.state == "stopped":
            return ZERO, "정지", self.reason
        if pattern is None:
            return self._stop("센서 읽기 실패")

        prev, self.last_pattern = self.last_pattern, pattern
        self.center_run = self.center_run + 1 if pattern in CENTER else 0
        recovered = self.center_run >= CENTER_CONFIRM

        if self.state == "crab":
            r = self._crab(pattern, now)
            if r is not None:
                return r                              # 아직 찾는 중 · 정지 · 그 밖이면 아래 따라가기로

        if self.state == "gap":
            if pattern != "0000":
                self.state = "follow"                 # 줄이 다시 보임 → 그 모양대로 따라가기
            elif now - self.t_state < GAP_MAX:
                return self._go(self._hard(self.gap_dir), self._gap_name())
            else:
                self.state = "follow"
                return self._lost(now)                # 0.3초 뒤에도 0000 → 진짜 줄 놓침

        elif self.state == "search":
            if recovered:
                self._to_follow(now)
            else:
                self.search_used += dt
                return self._search_out()

        elif self.state == "pivot":
            if recovered:
                self._to_follow(now)
            elif now - self.t_state < PIVOT_MAX:
                return self._go(self._turn(self.pivot_dir), "크게 꺾임: 제자리 " + ("왼쪽" if self.pivot_dir == "L" else "오른쪽"))
            else:
                return self._stop("크게 꺾임 1.5초 안에 줄을 못 잡음")   # 0000 이어도 뒤로 가지 않고 정지

        elif self.state == "all_black":
            if pattern == "1111":
                if now - self.t_state < ALL_BLACK_MAX:
                    return self._go(self._w(1, 1), "네 칸 모두 검음: 앞으로")
                return self._stop("네 칸 모두 검음 0.3초")
            self._to_follow(now)

        elif self.state == "odd":
            if pattern in ODD:
                if now - self.t_state < ODD_HOLD:
                    return self._go(self.out, "이상한 모양: 직전 동작 유지")
                return self._stop(f"이상한 모양 {pattern} 0.1초")
            self._to_follow(now)

        return self._follow(pattern, now, prev)

    # ---------------- 따라가기 ----------------
    def _to_follow(self, now):
        self.state, self.follow_since = "follow", now

    def _follow(self, p, now, prev=None):
        if self.follow_since is None:
            self.follow_since = now
        if self.search_used and now - self.follow_since >= STABLE_RESET:
            self.search_used = 0.0                    # 0.5초 안정적으로 달림 → 다음 줄 놓침은 2초 새로
        if p == "0110":
            return self._go(self._w(1, 1), "앞으로")
        if p == "0100":
            self.last_dir = "L"
            return self._go(self._w(GENTLE, 1), "왼쪽 완만")
        if p == "0010":
            self.last_dir = "R"
            return self._go(self._w(1, GENTLE), "오른쪽 완만")
        if p == "1000":
            self.last_dir = "L"
            return self._go(self._w(HARD, 1), "왼쪽 세게")
        if p == "0001":
            self.last_dir = "R"
            return self._go(self._w(1, HARD), "오른쪽 세게")
        if p in BIG_LEFT or p in BIG_RIGHT:
            d = "L" if p in BIG_LEFT else "R"
            self.last_dir = self.pivot_dir = d
            self.state, self.t_state = "pivot", now
            return self._go(self._turn(d), "크게 꺾임: 제자리 " + ("왼쪽" if d == "L" else "오른쪽"))
        if p == "1111":
            self.state, self.t_state = "all_black", now
            return self._go(self._w(1, 1), "네 칸 모두 검음: 앞으로")
        if p in ODD:
            self.state, self.t_state = "odd", now
            return self._go(self.out, "이상한 모양: 직전 동작 유지")
        if prev in ("0100", "0010"):                   # 0000 이지만 바로 앞이 안쪽 칸 → 줄이 칸 사이 틈
            self.gap_dir = "L" if prev == "0100" else "R"
            self.state, self.t_state = "gap", now
            return self._go(self._hard(self.gap_dir), self._gap_name())
        return self._lost(now)                         # 0000

    def _hard(self, d):
        return self._w(HARD, 1) if d == "L" else self._w(1, HARD)

    def _gap_name(self):
        return "줄이 칸 사이: " + ("왼쪽" if self.gap_dir == "L" else "오른쪽") + " 세게"

    def _turn(self, d):
        s = min(TURN_SPEED, self.speed)                         # 제자리 회전은 느리게 (라인 속도보다 크지 않게)
        return (-s, -s, s, s) if d == "L" else (s, s, -s, -s)   # 제자리 왼쪽 --++ / 오른쪽 ++--

    def _count_loss(self, now):
        self.losses.append(now)
        while self.losses and now - self.losses[0] > LOSS_WINDOW:
            self.losses.popleft()
        if len(self.losses) >= LOSS_MAX:
            return f"{LOSS_WINDOW:.0f}초 안에 줄 놓침 {LOSS_MAX}번"
        return None

    def _lost(self, now):
        if self.last_dir is None:
            return self._stop("줄이 안 보입니다 (마지막 방향 모름)")
        if self.search_used == 0.0:                   # 새 줄 놓침 (앞의 것을 이어 쓰는 중이 아니면)
            why = self._count_loss(now)
            if why:
                return self._stop(why)
        self.state, self.follow_since = "search", None
        return self._search_out()

    def _search_out(self):
        if self.search_used < TURN_SEARCH:                # 항상 시계방향(제자리 오른쪽) — 조원 결정 2026-11-04
            return self._go(self._turn("R"), f"줄 찾기: 시계방향 회전 {self.search_used:.1f}초")
        return self._stop(f"줄을 못 찾음 (회전 {TURN_SEARCH}초)")
