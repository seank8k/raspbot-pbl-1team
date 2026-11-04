#!/usr/bin/env python3
# 지시서: specs/05-obstacle-stop.md 「시작 전 조건 1 · 2」 — 초음파 값 · 갱신 간격 · 읽기 시간 · 바이트 섞임 (바퀴 안 움직임)
# 실행: python3 tools/ultrasonic_check.py [초]   — 「삐」 한 번이 나면 라즈봇 앞에 손을 댔다 뗐다, 「삐삐」면 끝
# 읽는 법: 0x1b(상위) → 0x1a(하위) → 0x1b(상위) 를 한 바이트씩. 두 상위 값이 다르면 「섞임」으로 센다.
#   (두 바이트 한 번에 읽기 read_i2c_block_data(0x1a, 2)는 이 보드에서 엉뚱한 값이 나와 쓰지 않는다 — 2026-11-04 측정)
import sys
import time

from Raspbot_Lib import Raspbot

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
bot = Raspbot()
dev, addr = bot._device, bot._addr


def beep(n):
    for _ in range(n):
        bot.Ctrl_BEEP_Switch(1)
        time.sleep(0.15)
        bot.Ctrl_BEEP_Switch(0)
        time.sleep(0.15)


bot.Ctrl_Ulatist_Switch(1)
time.sleep(1.0)
beep(1)
print(f"시작 — {secs:.0f}초 동안 0.005초마다 읽기", flush=True)
t0 = time.monotonic()
seq, torn, fails, rt, last = [], 0, 0, [], None
try:
    while time.monotonic() - t0 < secs:
        try:
            s = time.perf_counter()
            h1 = dev.read_i2c_block_data(addr, 0x1b, 1)[0]
            lo = dev.read_i2c_block_data(addr, 0x1a, 1)[0]
            h2 = dev.read_i2c_block_data(addr, 0x1b, 1)[0]
            rt.append(time.perf_counter() - s)
        except Exception:
            fails += 1
            continue
        if h1 != h2:
            torn += 1
            continue
        v = h1 << 8 | lo
        if v != last:
            seq.append((time.monotonic() - t0, v))
            last = v
        time.sleep(0.005)
finally:
    bot.Ctrl_Ulatist_Switch(0)
    beep(2)

ms = lambda x: f"{x * 1000:.2f}ms"
print(f"실패 {fails} · 섞임(상위 바이트 두 번이 다름) {torn} · 읽기 {len(rt)}번 · 읽기 시간 최대 {ms(max(rt)) if rt else '-'}")
gaps = sorted(b[0] - a[0] for a, b in zip(seq, seq[1:]))
if gaps:
    print(f"값이 바뀐 간격 {len(gaps)}번: 가장 짧음 {ms(gaps[0])} · 중간 {ms(gaps[len(gaps) // 2])} · 가장 김 {ms(gaps[-1])}")
else:
    print("값이 한 번도 안 바뀜 (손을 센서 앞에 대고 다시)")
print("나온 값(mm):", sorted(set(v for _, v in seq)))
print("시간순 (초:mm):", " ".join(f"{t:.2f}:{v}" for t, v in seq[:300]))
