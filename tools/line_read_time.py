#!/usr/bin/env python3
# 지시서: specs/04-line-tracer.md 「시작 전 조건 3」 — 라인센서 I2C 읽기 시간 (바퀴 안 움직임)
# 실행: python3 tools/line_read_time.py [횟수]
import sys
import time

from Raspbot_Lib import Raspbot

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
bot = Raspbot()
dev, addr = bot._device, bot._addr
times, vals, fails = [], {}, 0
for _ in range(n):
    t = time.perf_counter()
    try:
        v = dev.read_i2c_block_data(addr, 0x0a, 1)[0]
    except Exception:
        fails += 1
        v = None
    times.append(time.perf_counter() - t)
    vals[v] = vals.get(v, 0) + 1
times.sort()
ms = lambda x: f"{x * 1000:.2f}ms"
print(f"읽기 {n}번 · 실패 {fails} · 중간 {ms(times[n // 2])} · 99% {ms(times[int(n * 0.99)])} · 최대 {ms(times[-1])}")
print("값 (x1 x2 x3 x4 비트):", {("없음" if k is None else format(k, "04b")): c for k, c in vals.items()})
