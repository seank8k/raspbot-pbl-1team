#!/usr/bin/env python3
# 지시서: specs/08-hand-gesture.md — missions/gesture.py 「판단」 + sight.py 보 뒤 사람 멈춤 쉼 자동 시험 (바퀴 · 카메라 안 씀)
# 실행: python3 tools/test_gesture.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "missions"))
import gesture  # noqa: E402
import sight  # noqa: E402

ok_count, fail = 0, []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
    else:
        fail.append(f"{name} {detail}")
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail != "" else ""))


def V(items, cap, stale=False):
    return dict(enabled=True, ready=True, stale=stale, error=None, t_capture=cap,
                items=[dict(label=l, conf=c, box=(0, 0, .1, .1)) for l, c in items])


def feed(j, frames, t0=0.0):
    """frames: [(items, 장 수)] · 0.1초마다 새 결과 → [(t, 명령)]"""
    out, t, cap = [], t0, 0
    for items, n in frames:
        for _ in range(n):
            cap += 1
            c = j.update(V(items, cap), t)
            if c:
                out.append((round(t - t0, 2), c))
            t += 0.1
    return out


PALM, FIST, LIKE, PEACE = [("palm", .9)], [("fist", .9)], [("like", .9)], [("peace", .9)]
check("명령 표: 보 출발 · 주먹 멈춤 · 엄지척 빠르게 · 브이 사진",
      gesture.COMMANDS == {"palm": "start", "fist": "stop", "like": "faster", "peace": "photo"})
out = feed(gesture.GestureJudge(), [(PALM, 4)])
check("① 4번만 보이면 명령 없음 (연속 5번 필요)", out == [], out)
out = feed(gesture.GestureJudge(), [(PALM, 5)])
check("② 연속 5번 → 「출발」 한 번", out == [(0.4, "start")], out)
out = feed(gesture.GestureJudge(), [(PALM, 30)])
check("③ 손을 계속 들고 있어도 명령은 한 번만", out == [(0.4, "start")], out)
out = feed(gesture.GestureJudge(), [(FIST, 5), (LIKE, 10)])
check("④ 주먹 뒤 3초 안의 엄지척은 무시", out == [(0.4, "stop")], out)
out = feed(gesture.GestureJudge(), [(FIST, 5), ([], 30), (LIKE, 5)])
check("⑤ 3초 지나면 다음 명령 (엄지척 → 빠르게)", out == [(0.4, "stop"), (3.9, "faster")], out)
out = feed(gesture.GestureJudge(), [(PEACE, 5), ([], 31), (PEACE, 5)])
check("⑥ 손을 내렸다 다시 브이 → 사진 두 번", [c for _, c in out] == ["photo", "photo"], out)
out = feed(gesture.GestureJudge(), [([("palm", .6)], 10)])
check("⑦ 확신도 0.6(< 0.65)은 명령 아님", out == [], out)
out = feed(gesture.GestureJudge(), [(PALM, 3), (FIST, 1), (PALM, 3)])
check("⑧ 중간에 다른 손 모양이 끼면 처음부터 셈", out == [], out)
out = feed(gesture.GestureJudge(), [([("no_gesture", .95)], 10)])
check("⑨ 그냥 손(no_gesture)은 명령 아님", out == [], out)
out = feed(gesture.GestureJudge(), [([("palm", .7), ("fist", .9)], 5)])
check("⑩ 손이 둘이면 확신도 높은 손(주먹)", out == [(0.4, "stop")], out)
j = gesture.GestureJudge()
c = [j.update(V(PALM, i, stale=True), i * 0.1) for i in range(10)]
check("⑪ 인식이 멈춰 있으면(오래된 결과) 명령 없음", not any(c))

# sight: 보 뒤 3초 사람 멈춤 쉼
s = sight.SightJudge()
s.skip_person(3.0)
s.reset()                                   # 화면이 라인을 켜는 순간
holds, cap = [], 0
for k in range(50):
    cap += 1
    for _ in range(5):
        h, why, _ = s.update(dict(enabled=True, ready=True, stale=False, error=None, t_capture=cap,
                                  items=[dict(label="person", conf=.9, box=(0, 0, .1, .1))]), k * 0.1)
    holds.append((round(k * 0.1, 1), h))
first_hold = next((t for t, h in holds if h), None)
check("⑫ 보 뒤 3초는 사람이 보여도 안 멈춤 · 라인 켤 때 reset 해도 유지", all(not h for t, h in holds if t < 3.0), first_hold)
check("⑬ 3초 지나면 사람 멈춤 다시 (연속 2번 → 약 3.1초)", first_hold is not None and 3.0 <= first_hold <= 3.2, first_hold)
s = sight.SightJudge()
s.skip_person(3.0)
h, why, _ = s.update(dict(enabled=True, ready=True, stale=True, error=None, t_capture=1, items=[]), 0.5)
check("⑭ 사람 멈춤을 쉬는 중에도 인식 멈춤이면 멈춤", h and "인식 멈춤" in why, why)

print(f"\n결과: {ok_count}/{ok_count + len(fail)} 통과")
sys.exit(1 if fail else 0)
