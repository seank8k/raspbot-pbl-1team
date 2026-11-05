#!/usr/bin/env python3
# 지시서: specs/05-obstacle-stop.md 「깨뜨리는 시험 (--dry)」 — 웹 조종 서버에 가짜 초음파 · 라인센서를 넣어 확인 (바퀴 안 움직임)
# 실행: 먼저 python3 missions/webabb.py --dry --fault --port 5001 > /tmp/dry.out 2>&1 &
#       그다음 python3 tools/test_obstacle_web.py 5001
import http.cookiejar
import json
import sys
import threading
import time
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
BASE = f"http://127.0.0.1:{PORT}"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
ok_count, fail = 0, []
seq = 0
press = 0
beat_on = threading.Event()
beat_press = [0]


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
    r = call("/api/line", dict(seq=nseq(), press=press, on=True))
    beat_on.set()
    return r


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


def ln(s):
    return s.get("line", {})


def ob_state(s):
    return ln(s).get("obstacle", {}).get("state")


r = call("/api/claim", {})
fault(vision=[])                                  # 06 인식은 「아무것도 없음」으로 고정 (카메라 앞 사람 때문에 멈추지 않게)
check("자리 잡기", r.get("ok"), r)
threading.Thread(target=beater, daemon=True).start()
time.sleep(1.2)                                   # 초음파 준비 1초

# 1) 라인 + 장애물 없음 → 달림
fault(line_pattern="0110", ultra=600)
line_on()
t, s = wait_for(lambda s: s.get("moving"), 1.0)
check("1 라인 켬 · 장애물 없음 → 달림", t is not None, ln(s).get("action"))

# 2) 150mm 이하 → 잠깐 멈춤 (라인 모드 유지)
fault(ultra=136)
t, s = wait_for(lambda s: not s.get("moving"), 1.0)
check("2 136mm → 바퀴 0 (0.1초 안 · 웹 왕복 포함)", t is not None and t < 0.1, t)
check("2 잠깐 멈춤 중에도 라인 모드 켜짐", ln(s).get("active") and ob_state(s) == "pause", (ln(s).get("active"), ob_state(s)))

# 3) 치움 → 1초 뒤 다시 출발
fault(ultra=600)
t, s = wait_for(lambda s: s.get("moving"), 2.0)
check("3 치움 → 다시 출발 1.0~1.2초", t is not None and 0.95 <= t <= 1.2, t)

# 4) 1초 안에 다시 넣음 → 출발 안 함
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
fault(ultra=600)
time.sleep(0.6)
fault(ultra=187)
time.sleep(0.1)
fault(ultra=600)
t, s = wait_for(lambda s: s.get("moving"), 2.0)
check("4 치웠다 0.6초에 다시 187mm → 그 뒤 1초를 처음부터 (0.95초 넘게 기다림)", t is not None and t >= 0.9, t)

# 5) 섞인 읽기(버림) 짧게 → 이어서 셈
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
fault(ultra=600)
time.sleep(0.4)
fault(ultra="torn")
time.sleep(0.04)
fault(ultra=600)
t, s = wait_for(lambda s: s.get("moving"), 2.0)
check("5 버린 읽기 0.04초는 이어서 셈 → 처음부터 1초보다 빨리 출발", t is not None and t < 0.85, t)

# 6) 잠깐 멈춤 중 초음파 실패 → 라인 끔
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
fault(ultra="fail")
t, s = wait_for(lambda s: not ln(s).get("active"), 1.0)
check("6 멈춤 중 초음파 실패 → 라인 꺼짐", t is not None and "초음파" in str(ln(s).get("reason")), ln(s).get("reason"))
fault(ultra=600)
time.sleep(1.3)
check("6 그 뒤 치워져도 안 움직임 (다시 눌러야)", not status().get("moving"))
line_off()

# 7) 치웠는데 줄이 없음 → 라인 끔
fault(line_pattern="0110", ultra=600)
line_on()
wait_for(lambda s: s.get("moving"), 1.0)
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
fault(line_pattern="0000")
time.sleep(0.2)
fault(ultra=600)
t, s = wait_for(lambda s: s.get("moving"), 2.0)
check("7 (B) 치웠는데 줄 없음 → 끄지 않고 옆걸음 찾기", t is not None and "옆걸음" in str(s.get("move")), s.get("move"))
t, s = wait_for(lambda s: not ln(s).get("active"), 2.0)
check("7 (B) 옆걸음 1.0초 동안 못 찾으면 정지 · 라인 꺼짐", t is not None and "줄을 못 찾음" in str(ln(s).get("reason")), ln(s).get("reason"))
line_off()

# 7-2) 치웠을 때 1111(들림 · 가림) → 라인 끔
fault(line_pattern="0110", ultra=600)
line_on()
wait_for(lambda s: s.get("moving"), 1.0)
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
fault(line_pattern="1111")
time.sleep(0.2)
fault(ultra=600)
t, s = wait_for(lambda s: not ln(s).get("active"), 2.0)
time.sleep(0.3)
check("7-2 (B) 치웠는데 1111 → 출발 안 함 · 라인 꺼짐", t is not None and not status().get("moving") and "1111" not in "" and "들림" in str(ln(s).get("reason")),
      ln(s).get("reason"))
line_off()

# 7-3) 치웠을 때 바깥 칸 → 04 따라가기로 바로 출발
fault(line_pattern="0110", ultra=600)
line_on()
wait_for(lambda s: s.get("moving"), 1.0)
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
fault(line_pattern="1000")
time.sleep(0.2)
fault(ultra=600)
t, s = wait_for(lambda s: s.get("moving"), 2.0)
check("7-3 (B) 치웠는데 바깥 칸(1000) → 왼쪽 세게로 출발", t is not None and "왼쪽 세게" in str(s.get("move")), s.get("move"))
line_off()

# 8) 잠깐 멈춤 중 비상정지 → 치워도 출발 안 함
fault(line_pattern="0110", ultra=600)
line_on()
wait_for(lambda s: s.get("moving"), 1.0)
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
call("/api/estop", {})
fault(ultra=600)
time.sleep(1.5)
s = status()
check("8 멈춤 중 비상정지 → 치워도 안 움직임 · 라인 꺼짐", not s.get("moving") and not ln(s).get("active"), (s.get("moving"), ln(s).get("active")))
line_off()

# 9) 잠깐 멈춤 중 「라인 계속」 끊김 → 라인 끔
fault(line_pattern="0110", ultra=600)
line_on()
wait_for(lambda s: s.get("moving"), 1.0)
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
beat_on.clear()
time.sleep(1.3)
fault(ultra=600)
time.sleep(1.5)
s = status()
check("9 멈춤 중 「라인 계속」 1초 끊김 → 라인 꺼짐 · 치워도 안 움직임", not s.get("moving") and not ln(s).get("active"),
      (s.get("moving"), ln(s).get("reason")))
line_off()

# 10) 잠깐 멈춤 중 라인센서 실패 → 라인 끔
fault(line_pattern="0110", ultra=600)
line_on()
wait_for(lambda s: s.get("moving"), 1.0)
fault(ultra=100)
wait_for(lambda s: not s.get("moving"), 1.0)
fault(sensor_fail=1)
t, s = wait_for(lambda s: not ln(s).get("active"), 1.0)
fault(sensor_fail=0)                              # 남은 주입 실패가 다음 시험에 섞이지 않게
check("10 멈춤 중 라인센서 실패 → 라인 꺼짐", t is not None and "센서" in str(ln(s).get("reason")), ln(s).get("reason"))
line_off()

# 11) 앞에 장애물이 있으면 라인 켜기 거부
fault(line_pattern="0110", ultra=100)
line_on()
time.sleep(0.4)
s = status()
check("11 켤 때 앞에 장애물 → 출발 안 함", not s.get("moving") and "장애물" in str(ln(s).get("reason")), ln(s).get("reason"))
line_off()

# 12) 수동 조종은 장애물 정지 안 함 (조원 결정)
fault(ultra=100)
press += 1
mp = press
t0 = time.monotonic()
moved = False
while time.monotonic() - t0 < 0.6:
    call("/api/move", dict(seq=nseq(), press=mp, keys=["fwd"], speed=120))
    if status().get("moving"):
        moved = True
    time.sleep(0.1)
call("/api/stop", dict(seq=nseq(), press=mp))
check("12 수동 앞으로는 장애물이 있어도 움직임 (조원 결정)", moved)
time.sleep(0.3)

print(f"\n결과: {ok_count}/{ok_count + len(fail)} 통과")
sys.exit(1 if fail else 0)
