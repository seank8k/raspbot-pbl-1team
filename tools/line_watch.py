#!/usr/bin/env python3
# 지시서: specs/04-line-tracer.md 「시작 전 조건 1 — 라인센서 대응표」 (바퀴 안 움직임 · 손으로 밀며 확인)
# 실행: python3 tools/line_watch.py [초=20]  — 「삐」부터 「삐삐」까지 라인센서 값이 바뀐 순간을 기록
import sys
import time

from Raspbot_Lib import Raspbot

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
bot = Raspbot()
dev, addr = bot._device, bot._addr
NAMES = ["x1", "x2", "x3", "x4"]
SHIFT = {"x1": 3, "x2": 2, "x3": 1, "x4": 0}
fmt = lambda t: "".join(str((t >> SHIFT[n]) & 1) for n in NAMES)


def beep(n):
    for _ in range(n):
        bot.Ctrl_BEEP_Switch(1)
        time.sleep(0.15)
        bot.Ctrl_BEEP_Switch(0)
        time.sleep(0.15)


beep(1)
t0 = time.monotonic()
changes, last, fails, black = [], None, 0, {n: 0 for n in NAMES}
while time.monotonic() - t0 < secs:
    try:
        v = dev.read_i2c_block_data(addr, 0x0a, 1)[0]
    except Exception:
        fails += 1
        continue
    for n in NAMES:
        if ((v >> SHIFT[n]) & 1) == 0:
            black[n] += 1
    if v != last:
        changes.append(f"{time.monotonic() - t0:.2f}:{fmt(v)}")
        last = v
    time.sleep(0.005)
beep(2)
print(f"{secs:.0f}초 · 실패 {fails} · 칸마다 검게 읽힌 횟수:", black)
print("바뀐 순간 (초:x1x2x3x4 · 0 = 검은 줄):", " ".join(changes[:200]))
