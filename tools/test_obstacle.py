#!/usr/bin/env python3
# 지시서: specs/05-obstacle-stop.md — missions/obstacle.py 「판단」 + line.py 멈춤 · 이어 하기 자동 시험 (바퀴 · 센서 안 씀)
# 실행: python3 tools/test_obstacle.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "missions"))
import obstacle as ob  # noqa: E402
import line  # noqa: E402

ok_count, fail = 0, []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
    else:
        fail.append(f"{name} {detail}")
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail != "" else ""))


def feed(j, seq, t0=0.0, dt=0.02):
    """[(kind, mm, 횟수)] → [(시각, 상태, 이유, 남은)]"""
    out, t = [], t0
    for kind, mm, n in seq:
        for _ in range(n):
            s, why, left = j.update(kind, mm, t)
            out.append((t, s, why, left))
            t += dt
    return out, t


def ready_judge():
    j = ob.ObstacleJudge(on_time=0.0)
    _, t = feed(j, [("ok", 600, 60)])          # 1.2초 → 준비 끝
    return j, t


# 1) 준비
j = ob.ObstacleJudge(on_time=0.0)
out, _ = feed(j, [("ok", 600, 40)])
check("준비 ①: 켠 뒤 1초 전에는 준비 중", out[0][1] == ob.NOT_READY and out[-1][1] == ob.NOT_READY)
out, _ = feed(j, [("ok", 600, 15)], t0=0.8)
check("준비 ②: 1초 지나고 새 값 → 달림", out[-1][1] == ob.RUN, out[-1][1])
j = ob.ObstacleJudge(on_time=0.0)
out, _ = feed(j, [("torn", None, 80)])
check("준비 ③: 1초 지나도 쓸 수 있는 값이 없으면 준비 안 됨", out[-1][1] == ob.NOT_READY, out[-1][1])

# 2) 멈춤 판정
j, t = ready_judge()
out, t = feed(j, [("ok", 153, 1), ("ok", 136, 1)], t0=t)
check("멈춤 ①: 153mm → 달림 · 136mm 한 번 → 잠깐 멈춤", out[0][1] == ob.RUN and out[1][1] == ob.PAUSE, [o[1] for o in out])
j, t = ready_judge()
out, t = feed(j, [("ok", 150, 1)], t0=t)
check("멈춤 ②: 정확히 150mm → 잠깐 멈춤 (이하)", out[0][1] == ob.PAUSE)
j, t = ready_judge()
out, t = feed(j, [("ok", 0, 1)], t0=t)
check("멈춤 ③: 0 (아주 가까움) → 잠깐 멈춤", out[0][1] == ob.PAUSE)
j, t = ready_judge()
out, t = feed(j, [("ok", 5000, 1)], t0=t)
check("멈춤 ④: 뜻 모르는 큰 값은 달림 중에는 무시", out[0][1] == ob.RUN)
j, t = ready_judge()
out, t = feed(j, [("fail", None, 1)], t0=t)
check("실패: 읽기 실패 → 센서 실패", out[0][1] == ob.FAIL and out[0][2] == "초음파 읽기 실패")

# 3) 치워짐
j, t = ready_judge()
feed(j, [("ok", 100, 1)], t0=t)
t += 0.02
out, t = feed(j, [("ok", 600, 60)], t0=t)
first_clear = next((o[0] - out[0][0] for o in out if o[1] == ob.CLEAR), None)
check("치움 ①: 200mm 넘음 1초 계속 → 치워짐 (약 1.0초)", first_clear is not None and 0.98 <= first_clear <= 1.02, first_clear)
check("치움 ②: 그 전엔 남은 시간 표시", out[10][3] is not None and 0.75 <= out[10][3] <= 0.85, out[10][3])
j, t = ready_judge()
feed(j, [("ok", 100, 1)], t0=t)
t += 0.02
out, t = feed(j, [("ok", 600, 40), ("ok", 187, 1), ("ok", 600, 40)], t0=t)
check("치움 ③: 중간에 200mm 이하 한 번 → 1초를 처음부터 (81번째 읽기까지 치워짐 아님)",
      all(o[1] == ob.PAUSE for o in out), [o[1] for o in out if o[1] != ob.PAUSE][:1])
j, t = ready_judge()
feed(j, [("ok", 100, 1)], t0=t)
t += 0.02
out, t = feed(j, [("ok", 204, 30), ("ok", 600, 30)], t0=t)
check("치움 ④: 204mm(200 초과)도 치워짐으로 셈", out[-1][1] == ob.CLEAR, out[-1][1])
j, t = ready_judge()
feed(j, [("ok", 100, 1)], t0=t)
t += 0.02
out, t = feed(j, [("ok", 600, 30), ("torn", None, 6), ("ok", 600, 40)], t0=t)
check("치움 ⑤: 버린 읽기 0.12초(> 0.1초) → 1초를 처음부터", all(o[1] == ob.PAUSE for o in out),
      [o[1] for o in out if o[1] != ob.PAUSE][:1])
j, t = ready_judge()
feed(j, [("ok", 100, 1)], t0=t)
t += 0.02
out, t = feed(j, [("ok", 600, 30), ("torn", None, 3), ("ok", 600, 30)], t0=t)
check("치움 ⑥: 버린 읽기 0.06초(≤ 0.1초)는 이어서 셈", out[-1][1] == ob.CLEAR, out[-1][1])
j, t = ready_judge()
feed(j, [("ok", 100, 1)], t0=t)
t += 0.02
out, t = feed(j, [("ok", 600, 30), ("ok", 5000, 1), ("ok", 600, 40)], t0=t)
check("치움 ⑦: 뜻 모르는 값(> 800mm) → 출발 허락에서 뺌 · 1초 처음부터", all(o[1] == ob.PAUSE for o in out))
j, t = ready_judge()
feed(j, [("ok", 100, 1)], t0=t)
t += 0.02
out, t = feed(j, [("ok", 600, 30), ("fail", None, 1)], t0=t)
check("치움 ⑧: 멈춤 중 읽기 실패 → 센서 실패", out[-1][1] == ob.FAIL)
j, t = ready_judge()
feed(j, [("ok", 100, 1)], t0=t)
out, t = feed(j, [("ok", 100, 1500)], t0=t + 0.02)
check("오래 막힘: 30초 막혀 있어도 계속 잠깐 멈춤", all(o[1] == ob.PAUSE for o in out))
j.reset()
out, t = feed(j, [("ok", 600, 1)], t0=t)
check("리셋: 라인 끄면 타이머 · 상태 지움 → 달림", out[0][1] == ob.RUN)

# 4) line.py 멈춤 · 이어 하기 (#10 · #11)
f = line.LineFollower(60)
f.step("0110", 0.0)
f.step("1000", 0.02)                 # 마지막 방향 왼쪽 · 따라가기
for i in range(10):
    f.step("0000", 0.04 + i * 0.02)  # 0.2초 찾는 중
f.pause(0.24)
f.resume(10.24)                      # 10초 멈춤
check("이어 하기 ①: 찾기 동작은 버리고 따라가기로", f.state == "follow" and f.search_used == 0.0, (f.state, f.search_used))
check("이어 하기 ②: 마지막 방향 · 줄 놓침 기록은 남김", f.last_dir == "L" and len(f.losses) == 1, (f.last_dir, len(f.losses)))
check("이어 하기 ③: 줄 놓침 기록 시각을 멈춘 시간만큼 뒤로 (10초 3번 규칙이 대기 시간으로 안 지워짐)",
      abs(f.losses[0] - 10.04) < 1e-6, f.losses[0])
w, name, why = f.step("0110", 10.26)
check("이어 하기 ④: 다시 앞으로 · dt 가 대기 시간을 포함하지 않음", name == "앞으로" and why is None and f.prev_t == 10.26, (name, why))

# 5) 옆걸음 찾기 (지시서 05 · 2026-11-04 조원 결정): 항상 왼쪽 0.3초(≈1cm) → 오른쪽 0.6초(≈2cm) · 속도 55
L_CRAB, R_CRAB = (-55, 55, 55, -55), (55, -55, -55, 55)


def crab_run(side_pattern, seq):
    f = line.LineFollower(90)
    f.step("0110", 0.0)
    f.step(side_pattern, 0.02)
    f.step("0000", 0.04)                # 칸 사이 틈 상태에서 멈춤
    f.pause(0.06)
    f.resume(2.0)
    f.crab_search(2.0)
    out, t = [], 2.0
    for p, n in seq:
        for _ in range(n):
            out.append((round(t - 2.0, 2),) + f.step(p, t))
            t += 0.02
    return out


out = crab_run("0010", [("0000", 60)])
first_right = next((o[0] for o in out if o[1] == R_CRAB), None)
stop_at = next((o[0] for o in out if o[3]), None)
check("옆걸음 ①: 줄이 오른쪽에 있었어도 항상 왼쪽부터", out[0][1] == L_CRAB, out[0][1])
check("옆걸음 ②: 0.3초에 오른쪽으로 바꿈", first_right is not None and 0.29 <= first_right <= 0.33, first_right)
check("옆걸음 ③: 오른쪽 0.6초 뒤(합계 0.9초) 못 찾으면 정지 · 처음 쪽으로 돌아가지 않음",
      stop_at is not None and 0.89 <= stop_at <= 0.93 and "옆걸음" in out[-1][3]
      and not any(o[1] == L_CRAB for o in out if o[0] > 0.35), (stop_at, out[-1][3]))
check("옆걸음 ④: 회전 · 뒤로 없음 (옆걸음만)", all(o[1] in (L_CRAB, R_CRAB, (0, 0, 0, 0)) for o in out))
out = crab_run("0100", [("0000", 5), ("0001", 2), ("0010", 1), ("0110", 2)])
check("옆걸음 ⑤: 줄이 왼쪽에 있었어도 왼쪽부터", out[0][1] == L_CRAB, out[0][1])
check("옆걸음 ⑥: 바깥 칸은 계속 찾고 · 가운데 칸 보이면 바로 따라가기", out[5][2].startswith("옆걸음") and out[7][2] == "오른쪽 완만"
      and out[-1][2] == "앞으로" and not any(o[3] for o in out), [o[2] for o in out[5:]])
out = crab_run("0010", [("0000", 3), ("1111", 1)])
check("옆걸음 ⑧: 중간에 1111 → 정지", out[-1][3] is not None and "1111" not in "" and "네 칸" in out[-1][3], out[-1][3])

print(f"\n결과: {ok_count}/{ok_count + len(fail)} 통과")
sys.exit(1 if fail else 0)
