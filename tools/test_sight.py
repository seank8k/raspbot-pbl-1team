#!/usr/bin/env python3
# 지시서: specs/06-person-stop.md — missions/sight.py 「판단」 자동 시험 (바퀴 · 카메라 안 씀, PC/라즈봇 어디서나)
# 실행: python3 tools/test_sight.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "missions"))
import sight  # noqa: E402

ok_count, fail = 0, []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
    else:
        fail.append(f"{name} {detail}")
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail != "" else ""))


def V(items, t_cap, stale=False, ready=True, error=None):
    return dict(enabled=True, ready=ready, stale=stale, error=error, t_capture=t_cap,
                items=[dict(label=l, conf=c, box=(0, 0, .1, .1)) for l, c in items])


def run(j, frames, t0=0.0, tick=0.02, per=5):
    """frames: [(items, 몇 장)] · 인식은 tick 5번(0.1초)마다 새 결과 → [(t, hold, why, left)]"""
    out, t, cap = [], t0, 0
    for items, n in frames:
        for _ in range(n):
            cap += 1
            for _ in range(per):
                h, why, left = j.update(V(items, cap), t)
                out.append((round(t - t0, 2), h, why, left))
                t += tick
    return out, t


P, S, NONE = [("person", 0.8)], [("stop sign", 0.8)], []

# 1) 사람
j = sight.SightJudge()
out, _ = run(j, [(P, 1)])
check("사람 ①: 한 번만 보이면 안 멈춤 (연속 2번 필요)", not any(o[1] for o in out))
j = sight.SightJudge()
out, _ = run(j, [(P, 2)])
first = next((o[0] for o in out if o[1]), None)
check("사람 ②: 연속 2번 → 멈춤 · 이유 「사람」", first is not None and abs(first - 0.1) < 1e-6 and "사람" in out[-1][2], first)
j = sight.SightJudge()
out, _ = run(j, [(P, 30), (NONE, 15)])
hold_until = max(o[0] for o in out if o[1])
check("사람 ③: 보이는 동안 계속 멈춤 (3초)", all(o[1] for o in out if 0.1 <= o[0] < 3.0))
check("사람 ④: 마지막으로 보인 2.9초 + 1초 = 3.9초에 출발 (멈춤 마지막 순간 3.86~3.9)", 3.86 <= hold_until < 3.9, hold_until)
j = sight.SightJudge()
out, _ = run(j, [(P, 3), (NONE, 5), (P, 1), (NONE, 15)])
hold_until = max(o[0] for o in out if o[1])
check("사람 ⑤: 0.8초에 다시 보이면 1초를 처음부터 → 1.8초에 출발 (한 번만 보여도 · 이미 멈춘 중)", 1.76 <= hold_until < 1.8, hold_until)
j = sight.SightJudge()
out, _ = run(j, [(([("person", 0.6)]), 10)])
check("사람 ⑥: 확신도 0.6(< 0.65)은 무시", not any(o[1] for o in out))
j = sight.SightJudge()
out, _ = run(j, [(([("person", 0.65)]), 3)])
check("사람 ⑦: 확신도 0.65(기준과 같음)는 멈춤", any(o[1] for o in out))

# 2) STOP 표지판
j = sight.SightJudge()
out, _ = run(j, [(S, 2), (NONE, 40)])
holds = [o[0] for o in out if o[1]]
check("STOP ①: 연속 2번 → 3초 멈춤 뒤 출발", holds and abs(holds[0] - 0.1) < 1e-6 and 3.0 <= holds[-1] <= 3.12, (holds[:1], holds[-1:]))
check("STOP ②: 이유 「STOP 표지판」 · 남은 시간 표시", "STOP" in out[10][2] and 2.5 <= out[10][3] <= 2.9, out[10][2:])
j = sight.SightJudge()
out, _ = run(j, [(S, 80)])                     # 8초 내내 표지판이 보임
holds = [o[0] for o in out if o[1]]
check("STOP ③: 3초 뒤 표지판이 아직 보여도 출발", holds and holds[-1] <= 3.12, holds[-1:] if holds else None)
check("STOP ④: 출발 뒤 5초 동안은 또 안 멈춤", not any(o[1] for o in out if 3.12 < o[0] < 8.0))
j = sight.SightJudge()
out, _ = run(j, [(S, 2), (NONE, 85), (S, 2), (NONE, 40)])   # 8.7초 뒤(무시 5초 끝난 뒤) 다른 표지판
second = [o[0] for o in out if o[1] and o[0] > 5]
check("STOP ⑤: 무시 5초가 지나면 다음 표지판에서 다시 3초 멈춤", second and 8.8 <= second[0] <= 9.0, second[:1])

# 3) 동시 · 인식 멈춤
j = sight.SightJudge()
out, _ = run(j, [([("person", .8), ("stop sign", .8)], 2), (S, 10), (NONE, 30)])
holds = [o for o in out if o[1]]
check("동시 ①: 사람 + STOP → 사람이 먼저(이유) · 사람 풀린 뒤 STOP 3초 남으면 계속 멈춤",
      "사람" in holds[0][2] and holds[-1][0] >= 3.0, (holds[0][2], holds[-1][0]))
j = sight.SightJudge()
h, why, _ = j.update(V(NONE, 1, stale=True), 0.0)
check("멈춤 ①: 결과가 오래됨 → 「사람 없음」으로 안 보고 멈춤", h and "인식 멈춤" in why, why)
h, why, _ = j.update(dict(enabled=True, ready=False), 0.0)
check("멈춤 ②: 인식 준비 안 됨 → 멈춤", h)
h, why, _ = j.update(V(NONE, 2, error="boom"), 0.0)
check("멈춤 ③: 인식 오류 → 멈춤", h)
h, why, _ = j.update(dict(enabled=False), 0.0)
check("꺼짐: --no-detect(인식 꺼짐) → 멈춤 없음", not h)
j = sight.SightJudge()
run(j, [(P, 5)])
j.reset()
out, _ = run(j, [(NONE, 3)], t0=10.0)
check("리셋: 라인 다시 켜면 이전 사람 멈춤 지움", not any(o[1] for o in out))

print(f"\n결과: {ok_count}/{ok_count + len(fail)} 통과")
sys.exit(1 if fail else 0)
