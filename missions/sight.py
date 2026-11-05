#!/usr/bin/env python3
# 지시서: specs/06-person-stop.md 「규칙표」 (조원 결정 2026-11-05: 사람은 보이는 동안 멈춤 · STOP 표지판은 3초 멈췄다 출발)
# 인식 결과(사람 · STOP 표지판) → 「지금 멈춰야 하나 · 이유」만 판단한다. 바퀴 · 웹 · 카메라를 모른다.
# webabb.py 제어 스레드가 라인 모드일 때 0.02초마다 부르고, 07에서도 그대로 쓴다.

CONF = 0.65           # 「보임」 확신도 (조원 결정 2026-11-05 · 전에는 0.5)
CONFIRM = 2           # 새 인식 결과에서 연속 몇 번 (Claude 제안)
PERSON_CLEAR = 1.0    # 사람이 안 보인 지 이만큼 지나면 출발 (Claude 제안 · 05와 같게)
STOP_HOLD = 3.0       # STOP 표지판 앞에서 서 있는 시간 (조원 결정)
STOP_IGNORE = 5.0     # STOP 출발 뒤 표지판 무시 시간 (Claude 제안)


class SightJudge:
    def __init__(self):
        self.reset()

    def reset(self):
        """라인을 켤 때 · 꺼질 때 — 모든 타이머 · 횟수를 지운다."""
        self.last_capture = None
        self.person_run = self.stop_run = 0
        self.person_active, self.person_last = False, None
        self.stop_until = None
        self.stop_ignore_until = None
        # 보 명령의 「사람 멈춤 쉼」은 지우지 않는다 — 보 → 화면이 라인을 켜는 순간 reset() 이 불리기 때문
        self.person_skip_until = getattr(self, "person_skip_until", None)

    def skip_person(self, until):
        """손 모양 「보」(출발) 뒤 잠깐 사람 멈춤을 쉰다 (지시서 08 · 06). STOP 표지판 · 인식 멈춤은 그대로."""
        self.person_skip_until = until
        self.person_active, self.person_run = False, 0

    def update(self, v, now):
        """v: webabb Vision.status() (ready · stale · items · t_capture · error).
        돌려줌: (멈춤 여부, 이유 또는 None, 출발까지 남은 초 또는 None)"""
        if not v.get("enabled", False):
            return False, None, None
        if not v.get("ready") or v.get("stale") or v.get("error"):
            return True, "인식 멈춤 · 잠깐 멈춤", None             # 결과가 없거나 오래됨 → 「사람 없음」으로 보지 않음
        cap = v.get("t_capture")
        if cap != self.last_capture:                               # 새 인식 결과일 때만 횟수를 센다
            self.last_capture = cap
            items = v.get("items", [])
            person = any(d["label"] == "person" and d["conf"] >= CONF for d in items)
            if self.person_skip_until is not None and now < self.person_skip_until:
                person = False                                     # 보 명령 뒤 3초 — 사람 멈춤 쉼
            stop = any(d["label"] == "stop sign" and d["conf"] >= CONF for d in items)
            self.person_run = self.person_run + 1 if person else 0
            self.stop_run = self.stop_run + 1 if stop else 0
            if self.person_run >= CONFIRM:
                self.person_active = True
            if person and self.person_active:
                self.person_last = now
            if (self.stop_run >= CONFIRM and self.stop_until is None
                    and (self.stop_ignore_until is None or now >= self.stop_ignore_until)):
                self.stop_until = now + STOP_HOLD
                self.stop_ignore_until = self.stop_until + STOP_IGNORE

        if self.person_active and now - self.person_last >= PERSON_CLEAR:
            self.person_active = False                             # 1초 동안 안 보임 → 사람 멈춤 풀림
        if self.stop_until is not None and now >= self.stop_until:
            self.stop_until = None                                 # 3초 끝 → 출발 (5초 무시는 계속)

        if self.person_active:
            left = None if self.person_run else max(0.0, PERSON_CLEAR - (now - self.person_last))
            return True, "사람 · 잠깐 멈춤", left
        if self.stop_until is not None:
            return True, "STOP 표지판 · 3초 멈춤", max(0.0, self.stop_until - now)
        return False, None, None
