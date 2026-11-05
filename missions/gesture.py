#!/usr/bin/env python3
# 지시서: specs/08-hand-gesture.md 「규칙표」 (조원 결정 2026-11-05: 보 출발 · 주먹 멈춤 · 엄지척 빠르게 · 브이 사진)
# 인식 결과(손 모양) → 「명령 하나」만 판단한다. 바퀴 · 웹 · 카메라를 모른다. 명령을 실제로 하는 것은 webabb.py.

CONF = 0.65         # 명령으로 치는 확신도 (06과 같게)
CONFIRM = 5         # 같은 손 모양이 새 인식 결과에서 연속 몇 번 (약 0.5초 · Claude 제안)
COOLDOWN = 3.0      # 명령 뒤 이만큼 다른 손 명령 무시 (Claude 제안)
COMMANDS = {"palm": "start", "fist": "stop", "like": "faster", "peace": "photo"}


class GestureJudge:
    def __init__(self):
        self.reset()

    def reset(self):
        self.last_capture = None
        self.cand, self.run = None, 0
        self.quiet_until = None
        self.need_release = False   # 명령한 손을 내릴 때까지는 같은 손 모양으로 또 명령 안 함

    def update(self, v, now):
        """v: webabb Vision.status(). 돌려줌: 명령("start"·"stop"·"faster"·"photo") 또는 None"""
        if not v.get("enabled") or not v.get("ready") or v.get("stale") or v.get("error"):
            self.cand, self.run = None, 0
            return None
        cap = v.get("t_capture")
        if cap == self.last_capture:
            return None                                    # 새 인식 결과일 때만 센다
        self.last_capture = cap
        hands = [d for d in v.get("items", []) if d["label"] in COMMANDS and d["conf"] >= CONF]
        top = max(hands, key=lambda d: d["conf"])["label"] if hands else None
        if top is None:
            self.need_release = False
        if top != self.cand:
            self.cand, self.run = top, 0
        if top is None:
            return None
        self.run += 1
        if self.run < CONFIRM or self.need_release:
            return None
        if self.quiet_until is not None and now < self.quiet_until:
            return None
        self.quiet_until = now + COOLDOWN
        self.need_release = True
        self.run = 0
        return COMMANDS[top]
