#!/usr/bin/env python3
# 지시서: specs/04-line-tracer.md — missions/line.py 「판단」 자동 시험 (바퀴 · 센서 안 씀, PC/라즈봇 어디서나)
# 실행: python3 tools/test_line.py
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "missions"))
import line  # noqa: E402

S = 60
ok_count, fail = 0, []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
    else:
        fail.append(f"{name} {detail}")
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail != "" else ""))


def kind(w):
    """바퀴 값 → 동작 종류"""
    lf, lb, rf, rb = w
    if w == (0, 0, 0, 0):
        return "정지"
    if lf == rf > 0:
        return "앞"
    if lf == rf < 0:
        return "뒤"
    if lf < 0 < rf:
        return "제자리왼"
    if rf < 0 < lf:
        return "제자리오"
    if 0 <= lf < rf:
        return "왼쪽세게" if lf == 0 else "왼쪽완만"
    if 0 <= rf < lf:
        return "오른쪽세게" if rf == 0 else "오른쪽완만"
    return "?"


def run(f, seq, t0=0.0, dt=0.02):
    """[(패턴, 횟수)] 를 0.02초 간격으로 넣고 (시각, 바퀴, 이름, 이유) 목록을 돌려줌"""
    out, t = [], t0
    for p, n in seq:
        for _ in range(n):
            w, name, why = f.step(p, t)
            out.append((t, w, name, why))
            t += dt
    return out, t


# 1) decode
check("decode: 0 → 1111 (0 = 검은 줄)", line.decode(0) == "1111")
check("decode: 0x0F → 0000", line.decode(0x0F) == "0000")
check("decode: x2 만 검음(0b1011) → 왼바만 1", line.decode(0b1011) == "1000", line.decode(0b1011))
check("decode: None → None", line.decode(None) is None)

# 2) 켤 때
f = line.LineFollower(S)
check("켤 때: 0110 출발", f.start("0110")[0])
check("켤 때: 0000 출발 안 함", not f.start("0000")[0])
check("켤 때: 1100 출발 안 함 (가운데 칸 아님)", not f.start("1100")[0])
check("켤 때: None 출발 안 함", not f.start(None)[0])

# 3) 16가지 모양 (따라가기 상태 · 직전 동작 = 앞)
expect = {"0110": "앞", "0100": "왼쪽완만", "0010": "오른쪽완만", "1000": "왼쪽세게", "0001": "오른쪽세게",
          "1100": "앞", "1110": "앞", "0011": "앞", "0111": "앞", "1111": "앞",
          "1001": "앞", "1010": "앞", "0101": "앞", "1011": "앞", "1101": "앞", "0000": "제자리왼"}  # 0000 시험은 마지막 감지가 왼쪽
for p, k in expect.items():
    f = line.LineFollower(S)
    f.step("0110", 0.0)
    if p == "0000":
        f.step("1000", 0.02)        # 마지막 방향 = 왼쪽 (바깥 칸 뒤 0000 = 진짜 줄 놓침 · 안쪽 칸 뒤는 아래 「칸 사이 틈」)
    w, name, why = f.step(p, 0.04)
    check(f"16모양 {p} → {k}", kind(w) == k and why is None, f"{kind(w)} / {name}")
check("16모양 표가 16개", len(expect) == 16 and len(set(expect)) == 16)

# 4) 마지막 방향 모름 → 바로 정지
f = line.LineFollower(S)
f.step("0110", 0.0)
w, name, why = f.step("0000", 0.02)
check("마지막 방향 모름 → 바로 정지", w == line.ZERO and why and "마지막 방향" in why, why)

# 5) 줄 놓침: 회전 1.0초 → 정지 (뒤로 안 감 · 2026-11-04)
f = line.LineFollower(S)
_, t = run(f, [("0110", 5), ("0001", 3)])             # 마지막 방향 = 오른쪽 (바깥 칸 뒤 → 바로 찾기)
t_lost = t
out, t = run(f, [("0000", 120)], t0=t)
kinds = [(round(tt - t_lost, 2), kind(w), why) for tt, w, _, why in out]
first_back = next((x[0] for x in kinds if x[1] == "뒤"), None)
first_stop = next((x[0] for x in kinds if x[2]), None)
check("줄 놓침 ①: 마지막 방향이 오른쪽이면 오른쪽 찾기", kinds[0][1] == "제자리오", kinds[0])
check("줄 놓침 ②: 뒤로 가지 않음", first_back is None, first_back)
check("줄 놓침 ③: 약 1.0초에 정지", first_stop is not None and 0.98 <= first_stop <= 1.04, first_stop)
check("정지 뒤 다시 안 움직임 (가운데 줄을 봐도)", all(f.step("0110", t + i * 0.02)[0] == line.ZERO for i in range(5)))

# 6) 찾는 중 바깥 칸만 깜빡 → 다시 잡은 것 아님 · 가운데 1번 → 다시 잡음(2026-11-05 A) · 0.5초 안정 전에 또 놓치면 남은 시간만
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("1000", 2)])
t_lost = t
out, t = run(f, [("0000", 30), ("1000", 2), ("0000", 10)], t0=t)
check("깜빡임: 찾는 중 바깥 칸(1000)만 보이면 계속 찾기 (다시 잡은 것 아님)", "찾기" in out[31][2] and "찾기" in out[-1][2], (out[31][2], out[-1][2]))
out2, t = run(f, [("0110", 1)], t0=t)
check("A: 찾는 중 가운데 칸 1번 → 바로 따라가기 (앞으로)", out2[0][2] == "앞으로", out2[0][2])
out3, t = run(f, [("0000", 80)], t0=t)
stop_at = next((tt - t_lost for tt, w, n, why in out + out2 + out3 if why), None)
check("깜빡임으로 찾기 시간이 새로 시작되지 않음 (0.5초 안정 전 → 합계 약 1.0초에 정지)", stop_at is not None and 0.96 <= stop_at <= 1.1, stop_at)

# 6-2) 「9」 코스 첫 주행 두 번째 코너에서 실제로 나온 순서 (2026-11-05 서버 기록) — 전에는 여기서 정지
f = line.LineFollower(80)
_, t = run(f, [("0110", 5), ("0010", 1), ("0110", 3)])
out, t = run(f, [("0000", 1), ("0010", 1), ("1110", 1), ("0000", 20)], t0=t)
check("코너 재현 ①: 오른쪽을 마지막으로 본 뒤 0000 → 오른쪽 찾기", kind(out[0][1]) == "제자리오", kind(out[0][1]))
check("코너 재현 ②: 회전 중 가운데 1번(0010) → 다시 잡음", "오른쪽" in out[1][2], out[1][2])
check("코너 재현 ③: 이어서 1110 → 크게 꺾임 왼쪽 · 그 뒤 0000에도 회전 계속 (정지 아님)",
      "진입 전진" in out[2][2] and all(kind(w) == "제자리왼" and why is None for _, w, _, why in out[9:]), out[2][2])

# 7) 가운데 연속 2번 → 다시 잡음 → 0.2초 뒤 또 놓침 → 남은 시간만 씀
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("1000", 2)])
t1 = t
out1, t = run(f, [("0000", 25)], t0=t)                  # 0.5초 찾음
out2, t = run(f, [("0110", 10)], t0=t)                  # 0.2초 따라감
check("가운데 연속 2번 → 따라가기로 복귀", kind(out2[-1][1]) == "앞", out2[-1][2])
out3, t = run(f, [("0000", 80)], t0=t)
used = next((tt for tt, w, n, why in out3 if why), None)
check("0.5초 안정 전 또 놓침 → 남은 0.5초만 찾고 정지", used is not None and 0.44 <= used - out3[0][0] <= 0.56,
      None if used is None else round(used - out3[0][0], 2))

# 8) 0.5초 안정적으로 달리면 1.0초 새로
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("1000", 2), ("0000", 25), ("0110", 30), ("1000", 2)])
out, t = run(f, [("0000", 120)], t0=t)
stop_at = next((tt - out[0][0] for tt, w, n, why in out if why), None)
check("0.5초 안정 뒤 새 줄 놓침 → 다시 1.0초", stop_at is not None and 0.96 <= stop_at <= 1.06, stop_at)

# 9) 10초 안에 줄 놓침 3번 → 정지
f = line.LineFollower(S)
seq = [("0110", 3), ("1000", 2)]
for _ in range(3):
    seq += [("0000", 10), ("0110", 30), ("1000", 2)]
out, t = run(f, seq)
whys = [why for _, _, _, why in out if why]
check("10초 안에 줄 놓침 3번 → 정지", whys and "3번" in whys[0], whys[:1])

# 10) 1111: 0.3초 앞으로 → 정지 / 0.3초 안에 바뀌면 따라가기
f = line.LineFollower(S)
_, t = run(f, [("0110", 3)])
t0 = t
out, t = run(f, [("1111", 30)], t0=t)
stop_at = next((tt - t0 for tt, w, n, why in out if why), None)
check("1111 계속 → 약 0.3초에 정지", stop_at is not None and 0.28 <= stop_at <= 0.34, stop_at)
check("1111 동안은 앞으로", kind(out[0][1]) == "앞")
f = line.LineFollower(S)
out, t = run(f, [("0110", 3), ("1111", 10), ("0110", 3)])
check("1111 0.2초 뒤 0110 → 계속 따라감", kind(out[-1][1]) == "앞" and not any(x[3] for x in out))

# 11) 이상한 모양: 직전 동작 0.1초 유지 → 정지
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("0010", 2)])
t0 = t
out, t = run(f, [("1001", 10)], t0=t)
stop_at = next((tt - t0 for tt, w, n, why in out if why), None)
check("이상한 모양 → 직전 동작(오른쪽 완만) 유지", kind(out[0][1]) == "오른쪽완만", kind(out[0][1]))
check("이상한 모양 계속 → 약 0.1초에 정지", stop_at is not None and 0.08 <= stop_at <= 0.14, stop_at)

# 12) 크게 꺾임
f = line.LineFollower(S)
out, t = run(f, [("0110", 3), ("1100", 10), ("0000", 10), ("0100", 1), ("0110", 2)])
check("크게 꺾임 1100 → 진입 전진 뒤 왼쪽 회전 · 중간 0000 에도 계속 회전",
      out[3][1] == (40, 40, 40, 40) and all(kind(w) == "제자리왼" for _, w, _, _ in out[9:23]))
check("크게 꺾임 → 가운데 연속 2번에 따라가기", kind(out[-1][1]) == "앞" and not any(x[3] for x in out), out[-1][2])
f = line.LineFollower(S)
_, t = run(f, [("0110", 3)])
t0 = t
out, t = run(f, [("0011", 5), ("0000", 120)], t0=t)
first_back = next((tt - t0 for tt, w, n, why in out if kind(w) == "뒤"), None)
stop_at = next((tt - t0 for tt, w, n, why in out if why), None)
check("진입 0.1초 + 회전 1.5초 실패 → 뒤로 안 가고 약 1.6초에 정지", first_back is None and stop_at and 1.58 <= stop_at <= 1.66,
      (first_back, stop_at))
f = line.LineFollower(S)
out, t = run(f, [("0110", 3), ("1100", 5), ("1000", 100)])
whys = [why for _, _, _, why in out if why]
check("크게 꺾임 1.5초 실패 + 바깥 칸만 → 정지", whys and "크게 꺾임" in whys[0], whys[:1])

# 12-2) 칸 사이 틈 (2026-11-04): 안쪽 칸 바로 뒤 0000 → 그쪽으로 세게 최대 0.3초
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("0010", 2)])
out, t = run(f, [("0000", 10), ("0001", 2), ("0010", 2), ("0110", 3)], t0=t)
check("틈 ①: 오른쪽 안쪽 뒤 0000 → 오른쪽 세게 (회전 아님)", all(kind(w) == "오른쪽세게" for _, w, _, _ in out[:10]),
      [kind(w) for _, w, _, _ in out[:3]])
check("틈 ②: 0.2초 안에 바깥 칸이 보이면 그대로 따라가기 · 정지 없음", kind(out[-1][1]) == "앞" and not any(x[3] for x in out),
      out[-1][2])
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("0100", 2)])
out, t = run(f, [("0000", 3)], t0=t)
check("틈 ③: 왼쪽 안쪽 뒤 0000 → 왼쪽 세게", kind(out[0][1]) == "왼쪽세게", kind(out[0][1]))
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("0010", 2)])
t0 = t
out, t = run(f, [("0000", 120)], t0=t)
first_spin = next((tt - t0 for tt, w, n, why in out if kind(w) == "제자리오"), None)
stop_at = next((tt - t0 for tt, w, n, why in out if why), None)
check("틈 ④: 0.3초 뒤에도 0000 → 그때부터 회전 찾기", first_spin is not None and 0.28 <= first_spin <= 0.34, first_spin)
check("틈 ⑤: 회전 1.0초 더 → 약 1.3초에 정지 · 뒤로 없음",
      stop_at is not None and 1.28 <= stop_at <= 1.36 and not any(kind(w) == "뒤" for _, w, _, _ in out), stop_at)
f = line.LineFollower(S)
seq = [("0110", 3), ("0010", 2)]
for _ in range(5):
    seq += [("0000", 5), ("0010", 2), ("0110", 5), ("0010", 2)]
out, t = run(f, seq)
check("틈 ⑥: 짧은 틈 반복은 줄 놓침으로 세지 않음 (정지 없음)", not any(x[3] for x in out), [x[3] for x in out if x[3]][:1])
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("0010", 2)])
out, t = run(f, [("0000", 5), (None, 1)], t0=t)
check("틈 ⑦: 틈 중 센서 실패 → 바로 정지", out[-1][1] == line.ZERO and out[-1][3] == "센서 읽기 실패", out[-1][3])

# 12-3) 제자리 회전 속도 40 (2026-11-04 · 60이면 줄이 가운데를 지나쳐 못 잡음) · 「마지막 방향 고정」은 뺌
f = line.LineFollower(60)
w, _, _ = f.step("0110", 0.0)
w, _, _ = f.step("0011", 0.02)
check("코너 진입: 속도 40으로 먼저 전진", w == (40, 40, 40, 40), w)
w, _, _ = f.step("0000", 0.13)
check("회전 ①: 크게 꺾임 제자리 회전 = (40, 40, -40, -40) · 직진은 60 그대로", w == (40, 40, -40, -40), w)
f = line.LineFollower(60)
run(f, [("0110", 3), ("1000", 2)])
w, _, _ = f.step("0000", 0.2)
check("회전 ②: 줄 찾기 회전도 40 · 반시계방향", w == (-40, -40, 40, 40), w)
f = line.LineFollower(30)
f.step("0110", 0.0)
w, _, _ = f.step("1100", 0.02)
check("코너 진입: 라인 속도가 40보다 낮으면 전진도 그 속도", w == (30, 30, 30, 30), w)
w, _, _ = f.step("0000", 0.13)
check("회전 ③: 라인 속도가 40보다 낮으면 회전도 그 속도", w == (-30, -30, 30, 30), w)
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("0011", 10), ("0010", 2)])          # 진입 전진 → 오른쪽 회전 → 다시 잡음
out, t = run(f, [("0100", 2), ("1000", 1), ("0000", 3)], t0=t)   # 곧바로 줄이 왼쪽 → 놓침
check("반시계 ①: 줄이 왼쪽으로 사라지면 찾기는 반시계(제자리 왼쪽)", kind(out[-1][1]) == "제자리왼", kind(out[-1][1]))
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("0001", 2)])
out, t = run(f, [("0000", 3)], t0=t)
check("방향 ②: 줄이 오른쪽으로 사라지면 오른쪽 찾기", kind(out[-1][1]) == "제자리오", kind(out[-1][1]))
f = line.LineFollower(S)
_, t = run(f, [("0110", 3), ("0100", 2)])
out, t = run(f, [("0000", 30)], t0=t)
check("반시계 ③: 칸 사이 틈(왼쪽 세게 0.3초)은 그대로 → 그 뒤 찾기만 반시계",
      kind(out[0][1]) == "왼쪽세게" and kind(out[-1][1]) == "제자리왼", (kind(out[0][1]), kind(out[-1][1])))

# 13) 센서 실패
for corner, spin in (("1110", (-40, -40, 40, 40)), ("0111", (40, 40, -40, -40))):
    f = line.LineFollower(60)
    f.step("0110", 0.0)
    w, _, _ = f.step(corner, 1.0)
    check(f"코너 {corner}: 감지 순간 진입 전진", w == (40, 40, 40, 40))
    w, _, _ = f.step("0110", 1.08)
    check(f"코너 {corner}: 진입 중 가운데를 봐도 0.1초까지 전진", w == (40, 40, 40, 40))
    w, _, _ = f.step("0110", 1.11)
    check(f"코너 {corner}: 회전 시작 때 기존 가운데 횟수 초기화", w == spin and f.center_run == 0)
    w, _, _ = f.step("0110", 1.13)
    check(f"코너 {corner}: 회전 중 가운데 1번은 계속 회전", w == spin)
    w, _, _ = f.step("0110", 1.15)
    check(f"코너 {corner}: 회전 중 가운데 2번에 직진 복귀", w == (60, 60, 60, 60))

f = line.LineFollower(60)
f.step("1110", 0.0)
w, _, why = f.step(None, 0.02)
check("코너 진입 중 센서 실패 → 즉시 네 바퀴 정지", w == line.ZERO and why == "센서 읽기 실패")
f = line.LineFollower(60)
f.step("1110", 0.0)
f.pause(0.04)
f.resume(5.04)
w, name, why = f.step("0110", 5.06)
check("코너 진입 중 대기 뒤 재출발 → 예전 진입·회전은 버림", w == (60, 60, 60, 60) and name == "앞으로" and why is None)

f = line.LineFollower(S)
f.step("0110", 0.0)
w, name, why = f.step(None, 0.02)
check("센서 읽기 실패(None) → 바로 정지", w == line.ZERO and why == "센서 읽기 실패", why)

# 14) 속도 한계
f = line.LineFollower(80)
mx = 0
for p in expect:
    g = line.LineFollower(80)
    g.step("0110", 0)
    g.step("0100", 0.02)
    mx = max(mx, max(abs(v) for v in g.step(p, 0.04)[0]))
check("어떤 모양에서도 바퀴 값 ≤ 속도(80)", mx <= 80, mx)

print(f"\n결과: {ok_count}/{ok_count + len(fail)} 통과")
sys.exit(1 if fail else 0)
