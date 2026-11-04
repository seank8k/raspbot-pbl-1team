#!/usr/bin/env python3
# 키 입력 간격 점검 — 바퀴는 돌리지 않는다.
# teleop.py 와 같은 방식(curses, 0.05초마다 확인)으로 키를 읽고,
# 키를 꾹 누르고 있을 때 입력 사이 간격이 AUTO_STOP(0.6초)을 넘는지 잰다.
# 넘으면 teleop.py 에서는 그 순간 라즈봇이 잠깐 멈췄다 다시 움직인다(펄스).
#
# 사용법: (영어 입력 상태에서) w 를 3초쯤 꾹 누르고 떼기 → 2초 이상 쉬기 → 3~5번 반복 → x 로 끝내기
# 결과: results/key_gap.csv (키 입력마다 시각 기록)
import csv
import curses
import os
import time

AUTO_STOP = 0.6   # teleop.py 와 같은 값
RELEASE = 1.5     # 이만큼 조용하면 손을 뗀 것으로 본다 (그래서 누름 사이엔 2초 이상 쉰다)
BURST = 0.02      # 핫스팟을 거치며 뭉쳐 도착한 입력은 하나로 본다
MOVE_KEYS = set("wasdqe")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "results", "key_gap.csv")


def main(screen):
    curses.curs_set(0)
    screen.timeout(50)
    events = []  # (시각, 키 코드)
    t0 = time.monotonic()
    while True:
        ch = screen.getch()
        now = time.monotonic() - t0
        if ch == ord("x") or ch == ord("X"):
            break
        if ch >= 0:
            events.append((now, ch))
        screen.erase()
        screen.addstr(0, 0, "key gap test (wheels do NOT move)")
        screen.addstr(1, 0, "English input! hold w ~3s, release, rest 2s+, repeat 3-5x, x = quit")
        screen.addstr(3, 0, f"key events: {len(events)}")
        if events:
            gap = now - events[-1][0]
            screen.addstr(4, 0, f"since last key: {gap:.2f}s")
    return events


def summarize(events):
    # 뭉쳐 온 입력을 하나로 합친다
    times = []
    for t, _ in events:
        if not times or t - times[-1] > BURST:
            times.append(t)
    presses = []  # 각 누름: 그 안의 시각 목록
    for t in times:
        if not presses or t - presses[-1][-1] > RELEASE:
            presses.append([t])
        else:
            presses[-1].append(t)
    return presses


events = curses.wrapper(main)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t_sec", "code", "char"])
    for t, ch in events:
        w.writerow([f"{t:.3f}", ch, chr(ch) if 32 <= ch < 127 else ""])

other = sum(1 for _, ch in events if not (0 <= ch < 128 and chr(ch).lower() in MOVE_KEYS))
print(f"[OK] 키 입력 {len(events)}개 기록 -> {OUT}")
if other:
    print(f"  ! 조종 키가 아닌 입력 {other}개 (한글 입력 상태였을 수 있음 — 한/영 키로 영어로)")
worst_first = 0.0
breaks = 0
for i, p in enumerate(summarize(events), 1):
    if len(p) < 2:
        print(f"  {i}번째 누름: 한 번만 입력됨 (짧게 눌렀거나 반복이 안 옴)")
        continue
    gaps = [b - a for a, b in zip(p, p[1:])]
    # 첫 반복 대기 = 누른 뒤 1초 안에서 가장 긴 간격 (핫스팟이 첫 입력을 둘로 쪼개 보내도 맞게)
    head = [b - a for a, b in zip(p, p[1:]) if a - p[0] < 1.0]
    first = max(head)
    rest = [b - a for a, b in zip(p, p[1:]) if a - p[0] >= 1.0]
    mx = max(rest) if rest else 0.0
    n = sum(1 for g in gaps if g > AUTO_STOP)
    worst_first, breaks = max(worst_first, first), breaks + n
    flag = "  <- 펄스" if n else ""
    print(f"  {i}번째 누름: {p[-1] - p[0]:.1f}초 · 첫 반복까지 {first:.2f}s · 그 뒤 최대 간격 {mx:.2f}s · {AUTO_STOP}초 넘음 {n}번{flag}")
if worst_first:
    print(f"  => 가장 긴 첫 반복 대기 {worst_first:.2f}s (기준 {AUTO_STOP}s, 여유 {AUTO_STOP - worst_first:+.2f}s) · 끊김 합계 {breaks}번")
