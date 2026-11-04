#!/usr/bin/env python3
# 지시서: specs/04-line-tracer.md 「시작 전 조건 1 — 라인센서 대응표」 (바닥에서 천천히 직진하며 잼)
# 실행: python3 tools/line_map_drive.py [속도=40] [초=2]
# 준비: 검은 테이프를 진행 방향에 비스듬히(약 45°, 왼쪽 끝이 라즈봇에 더 가깝게) 붙이고, 라즈봇을 그 앞 10~20cm에 둔다.
#       → 왼쪽 칸이 먼저 테이프에 닿으므로, 「처음 검게 된 시각」 순서 = 왼쪽부터의 순서.
# 동작: 삐 → 1초 뒤 직진(++++) → 끝나면(오류가 나도) 네 바퀴 0 → 삐삐 → 칸마다 결과 출력
import sys
import time

from Raspbot_Lib import Raspbot

LIMIT = 60  # 지시서 04 속도 한계
speed = int(sys.argv[1]) if len(sys.argv) > 1 else 40
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
if not 0 < speed <= LIMIT:
    sys.exit(f"속도는 1~{LIMIT} (지시서 04)")
if not 0 < secs <= 3:
    sys.exit("시간은 3초 이하")

bot = Raspbot()
dev, addr = bot._device, bot._addr
NAMES = ["x1", "x2", "x3", "x4"]
SHIFT = {"x1": 3, "x2": 2, "x3": 1, "x4": 0}


def stop():
    for i in range(4):
        bot.Ctrl_Muto(i, 0)


def beep(n):
    for _ in range(n):
        bot.Ctrl_BEEP_Switch(1)
        time.sleep(0.15)
        bot.Ctrl_BEEP_Switch(0)
        time.sleep(0.15)


def read():
    return dev.read_i2c_block_data(addr, 0x0a, 1)[0]


samples, fails = [], 0
try:
    stop()
    before = read()
    beep(1)
    time.sleep(1.0)
    for i in range(4):
        bot.Ctrl_Muto(i, speed)
    t0 = time.monotonic()
    while time.monotonic() - t0 < secs:
        try:
            samples.append((time.monotonic() - t0, read()))
        except Exception:
            fails += 1
        time.sleep(0.003)
finally:
    stop()
    stop()  # 한 번 더 (I2C 한 번 실패 대비)
    beep(2)

after = read()
fmt = lambda t: "".join(str((t >> SHIFT[n]) & 1) for n in NAMES)
print(f"속도 {speed} · {secs}초 · 읽기 {len(samples)}번 · 실패 {fails}")
print(f"출발 전 x1x2x3x4 = {fmt(before)} · 멈춘 뒤 = {fmt(after)}   (1 = 흰 바닥 · 0 = 검은 줄)")
first = {}
for n in NAMES:
    hits = [t for t, v in samples if ((v >> SHIFT[n]) & 1) == 0]
    first[n] = hits[0] if hits else None
    span = f"{hits[0]:.3f}~{hits[-1]:.3f}초 · {len(hits)}번" if hits else "한 번도 검게 안 됨"
    print(f"  {n}: {span}")
order = sorted((t, n) for n, t in first.items() if t is not None)
print("처음 검게 된 순서 (= 왼쪽부터, 테이프 왼쪽 끝이 가까울 때):", " → ".join(f"{n}({t:.3f})" for t, n in order))
changes, last = [], None
for t, v in samples:
    if v != last:
        changes.append(f"{t:.3f}:{fmt(v)}")
        last = v
print("바뀐 순간 (초:x1x2x3x4):", " ".join(changes[:80]))
