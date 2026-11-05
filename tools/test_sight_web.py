#!/usr/bin/env python3
# 지시서: specs/06-person-stop.md 「규칙표」 — 웹 조종 서버에 가짜 인식 · 라인센서 · 초음파를 넣어 확인 (바퀴 안 움직임)
# 실행: 먼저 python3 missions/webabb.py --dry --fault --port 5001 > /tmp/sdry.out 2>&1 &
#       그다음 python3 tools/test_sight_web.py 5001
import http.cookiejar
import json
import sys
import threading
import time
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
BASE = f"http://127.0.0.1:{PORT}"
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
ok_count, fail = 0, []
seq = press = 0
beat_on, beat_press = threading.Event(), [0]


def call(path, data=None):
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if data is None else "POST")
    try:
        with opener.open(req, timeout=3) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def nseq():
    global seq
    seq += 1
    return seq


def fault(**kw):
    call("/api/_fault", kw)


def status():
    return call("/api/status")


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
    else:
        fail.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail != "" else ""), flush=True)


def beater():
    while True:
        if beat_on.is_set():
            call("/api/line", dict(seq=nseq(), press=beat_press[0], on=True))
        time.sleep(0.25)


def line_on():
    global press
    press += 1
    beat_press[0] = press
    call("/api/line", dict(seq=nseq(), press=press, on=True))
    beat_on.set()


def line_off():
    beat_on.clear()
    call("/api/line", dict(seq=nseq(), press=beat_press[0], on=False))
    time.sleep(0.15)


def wait_for(cond, limit):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        s = status()
        if cond(s):
            return time.monotonic() - t0, s
        time.sleep(0.02)
    return None, status()


ln = lambda s: s.get("line", {})
moving = lambda s: s.get("moving")
P, S = [["person", 0.8]], [["stop sign", 0.8]]

call("/api/claim", {})
fault(vision=[], line_pattern="0110", ultra=600)
threading.Thread(target=beater, daemon=True).start()
time.sleep(1.2)

# 1) 사람
line_on()
t, s = wait_for(moving, 1.0)
check("1 라인 켬 · 아무것도 없음 → 달림", t is not None)
fault(vision=P)
t, s = wait_for(lambda s: not moving(s), 1.0)
check("2 사람 → 0.4초 안에 멈춤 (연속 2번 · 웹 왕복 포함)", t is not None and t < 0.4, t)
check("2 멈춘 중에도 라인 켜짐 · 이유 「사람」", ln(s).get("active") and "사람" in str(ln(s).get("action")), ln(s).get("action"))
time.sleep(2.0)
check("3 사람이 계속 보이면 2초 뒤에도 계속 멈춤", not moving(status()))
fault(vision=[])
t, s = wait_for(moving, 2.5)
check("4 사람이 사라지면 1.0~1.3초 뒤 다시 출발", t is not None and 0.95 <= t <= 1.35, t)

# 2) STOP 표지판
fault(vision=S)
t, s = wait_for(lambda s: not moving(s), 1.0)
check("5 STOP 표지판 → 멈춤", t is not None and "STOP" in str(ln(s).get("action")), ln(s).get("action"))
t, s = wait_for(moving, 4.0)
check("6 표지판이 계속 보여도 약 3초 뒤 출발", t is not None and 2.7 <= t <= 3.3, t)
time.sleep(2.0)
check("7 출발 뒤 5초 동안은 같은 표지판에 또 안 멈춤", moving(status()))
fault(vision=[])
line_off()

# 3) 인식 멈춤 · 켤 때
fault(vision="stale")
line_on()
time.sleep(0.4)
s = status()
check("8 인식이 멈춘 상태에서 라인 켜기 → 출발 안 함 「인식 준비 중」", not moving(s) and "인식" in str(ln(s).get("reason")), ln(s).get("reason"))
line_off()
fault(vision=[])
line_on()
wait_for(moving, 1.0)
fault(vision="stale")
t, s = wait_for(lambda s: not moving(s), 1.0)
check("9 달리는 중 인식 멈춤 → 「사람 없음」으로 안 보고 멈춤", t is not None and "인식 멈춤" in str(ln(s).get("action")), ln(s).get("action"))
fault(vision=[])
t, s = wait_for(moving, 1.0)
check("10 인식이 돌아오면 다시 출발", t is not None, t)

# 4) 장애물과 같이
fault(vision=P, ultra=100)
t, s = wait_for(lambda s: not moving(s), 1.0)
check("11 사람 + 장애물 → 멈춤", t is not None)
fault(vision=[])
time.sleep(1.6)
check("12 사람만 사라짐 · 장애물은 그대로 → 계속 멈춤", not moving(status()) and ln(s).get("active"))
fault(ultra=600)
t, s = wait_for(moving, 2.5)
check("13 장애물도 치우면 1초 뒤 출발", t is not None and 0.9 <= t <= 1.5, t)
line_off()

# 5) 비상정지 · 수동
fault(vision=[])
line_on()
wait_for(moving, 1.0)
fault(vision=P)
wait_for(lambda s: not moving(s), 1.0)
call("/api/estop", {})
fault(vision=[])
time.sleep(1.6)
s = status()
check("14 사람 멈춤 중 비상정지 → 사람이 사라져도 안 움직임 · 라인 꺼짐", not moving(s) and not ln(s).get("active"), ln(s).get("reason"))
line_off()
fault(vision=P)
press += 1
mp = press
moved, t0 = False, time.monotonic()
while time.monotonic() - t0 < 0.6:
    call("/api/move", dict(seq=nseq(), press=mp, keys=["fwd"], speed=120))
    moved = moved or bool(status().get("moving"))
    time.sleep(0.1)
call("/api/stop", dict(seq=nseq(), press=mp))
check("15 수동 앞으로는 사람이 보여도 움직임 (라인 중에만 적용)", moved)
fault(vision=None)

print(f"\n결과: {ok_count}/{ok_count + len(fail)} 통과")
sys.exit(1 if fail else 0)
