#!/usr/bin/env python3
# 지시서: specs/08-hand-gesture.md · 출발/정지 전용 모드 (2026-11-06)
# --dry --fault --gesture-start-stop-only 서버에서만 가짜 인식으로 시험. 실제 바퀴 안 씀.
import http.cookiejar
import json
import sys
import threading
import time
import urllib.request

BASE = "http://127.0.0.1:" + (sys.argv[1] if len(sys.argv) > 1 else "5001")
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
seq, press = 0, 0
beat = threading.Event()
fail, passed = [], 0


def call(path, data=None):
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=3) as r:
        return json.loads(r.read())


def check(name, condition, value=None):
    global passed
    if condition:
        passed += 1
    else:
        fail.append(name)
    print(("PASS " if condition else "FAIL ") + name + " " + str(value), flush=True)


def fault(items):
    call("/api/_fault", dict(vision=items, line_pattern="0110", ultra=600))


def send_line():
    global seq
    seq += 1
    call("/api/line", dict(seq=seq, press=press, on=True))


def beater():
    while True:
        if beat.is_set():
            send_line()
        time.sleep(.25)


def wait_gesture(cmd, after, timeout=2):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        g = call("/api/vision").get("gesture") or {}
        if g.get("id", 0) > after and g.get("cmd") == cmd:
            return g
        time.sleep(.05)
    return {}


cfg = call("/api/config")
if not (cfg.get("dry") and cfg.get("fault") and cfg.get("gesture_start_stop_only")):
    raise SystemExit("Requires --dry --fault --gesture-start-stop-only")
call("/api/claim", {})
threading.Thread(target=beater, daemon=True).start()
try:
    fault([])
    time.sleep(1.2)  # 초음파 준비. 자리 만료(3초) 전에 다음 요청을 보낸다.
    old = (call("/api/vision").get("gesture") or {}).get("id", 0)
    fault([["palm", .9], ["person", .9]])
    start = wait_gesture("start", old)
    check("보 → 출발 이벤트", bool(start))
    press += 1
    send_line()
    beat.set()
    time.sleep(.25)
    check("보 뒤 사람3초 유예 동안 라인 시작", bool(call("/api/status").get("moving")))
    t0 = time.monotonic()
    fault([["fist", .9], ["person", .9]])
    stop = wait_gesture("stop", start.get("id", old))
    beat.clear()
    s = call("/api/status")
    check("출발 직후 주먹 정지가3초 대기에 막히지 않음", bool(stop) and time.monotonic() - t0 < 3)
    check("주먹으로 바퀴0·라인 종료", not s.get("moving") and not s.get("line", {}).get("active"), s.get("reason"))
    last = (call("/api/vision").get("gesture") or {}).get("id", 0)
    for label in ("like", "peace"):
        fault([[label, .99]])
        time.sleep(.8)
        v = call("/api/vision")
        check(label + " 명령 제외·속도60 유지", (v.get("gesture") or {}).get("id", 0) == last and v.get("line_speed") == 60)
    fault([])
    time.sleep(.3)
    check("손을 내려도 주먹 정지 뒤 자동 재출발 없음", not call("/api/status").get("moving"))
finally:
    beat.clear()
    call("/api/estop", {})
    call("/api/_fault", dict(vision=None))
    call("/api/leave", {})

print(f"결과: {passed}/{passed + len(fail)} 통과")
sys.exit(bool(fail))
