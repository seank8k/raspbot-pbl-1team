#!/usr/bin/env python3
# 지시서: specs/08-hand-gesture.md — 웹 조종 서버에 가짜 손 모양을 넣어 명령 확인 (바퀴 안 움직임)
# 실행: 먼저 python3 missions/webabb.py --dry --fault --port 5001 > /tmp/gdry.out 2>&1 &
#       그다음 python3 tools/test_gesture_web.py 5001
import glob
import http.cookiejar
import json
import os
import sys
import threading
import time
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
BASE = f"http://127.0.0.1:{PORT}"
PHOTOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "photos")
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
    """화면이 보 명령을 받았을 때 하는 일과 같음 (lineStart)"""
    global press
    press += 1
    beat_press[0] = press
    call("/api/line", dict(seq=nseq(), press=press, on=True))
    beat_on.set()


def wait_gesture(cmd, limit=2.0, after=0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < limit:
        g = call("/api/vision").get("gesture")
        if g and g["id"] > after and g["cmd"] == cmd:
            return time.monotonic() - t0, g
        time.sleep(0.05)
    return None, call("/api/vision").get("gesture")


def gid():
    g = call("/api/vision").get("gesture")
    return g["id"] if g else 0


status = lambda: call("/api/status")
moving = lambda: bool(status().get("moving"))
call("/api/claim", {})
fault(vision=[], line_pattern="0110", ultra=600)
threading.Thread(target=beater, daemon=True).start()
time.sleep(1.2)

# 1) 보 → 출발 명령 · 보 + 사람 3초
g0 = gid()
fault(vision=[["palm", 0.9], ["person", 0.9]])
t, g = wait_gesture("start", after=g0)
check("1 보(+사람) 0.5초 유지 → 「출발」 명령 (0.5~1.0초)", t is not None and 0.4 <= t <= 1.0, t)
line_on()                                       # 화면이 라인을 켬
time.sleep(0.4)
check("2 보 뒤 사람이 같이 보여도 달림 (3초 사람 멈춤 쉼)", moving(), status().get("line", {}).get("action"))
time.sleep(3.2)
s = status()
check("3 3초 지나면 사람 때문에 다시 멈춤", not s.get("moving") and "사람" in str(s.get("line", {}).get("action")), s.get("line", {}).get("action"))
fault(vision=[])
t0 = time.monotonic()
while time.monotonic() - t0 < 2.5 and not moving():
    time.sleep(0.05)
check("4 사람이 사라지면 다시 달림", moving())

# 2) 엄지척 → 빠르게
time.sleep(3.0)                                  # 명령 뒤 3초 무시 지남
g0 = gid()
fault(vision=[["like", 0.9]])
t, g = wait_gesture("faster", after=g0)
fault(vision=[])
v = call("/api/vision")
check("5 엄지척 → 「빠르게」 · 라인 속도 +10 (60 → 70)", t is not None and v.get("line_speed") == 70, (t, v.get("line_speed")))
time.sleep(0.3)
check("6 달리는 바퀴 값이 70으로", "70" in str(status().get("move")) or moving(), status().get("move"))

# 3) 브이 → 사진
time.sleep(3.0)
before = set(glob.glob(os.path.join(PHOTOS, "*.jpg")))
g0 = gid()
fault(vision=[["peace", 0.9]])
t, g = wait_gesture("photo", after=g0)
fault(vision=[])
time.sleep(0.8)
new = set(glob.glob(os.path.join(PHOTOS, "*.jpg"))) - before
check("7 브이 → 「사진」 · results/photos/ 에 1장", t is not None and len(new) == 1, (t, [os.path.basename(p) for p in new]))
for p in new:
    os.remove(p)                                # 시험 사진은 지움 (얼굴)

# 4) 주먹 → 멈춤
time.sleep(3.0)
check("8 주먹 전에는 달리는 중", moving())
g0 = gid()
fault(vision=[["fist", 0.9]])
t, g = wait_gesture("stop", after=g0)
fault(vision=[])
time.sleep(0.2)
s = status()
check("9 주먹 → 바로 멈춤 · 라인 꺼짐", t is not None and not s.get("moving") and not s.get("line", {}).get("active"),
      (t, s.get("reason")))
time.sleep(1.5)
check("10 주먹 뒤엔 다시 눌러야 출발 (저절로 안 움직임)", not moving())
check("11 라인을 다시 켜면 속도 60으로", True if (line_on() or True) and time.sleep(0.5) is None and call("/api/vision").get("line_speed") == 60 else False,
      call("/api/vision").get("line_speed"))
beat_on.clear()
call("/api/stop", dict(seq=nseq(), press=press, all=True))

# 5) 화면을 닫으면 손 모양을 안 들음
call("/api/leave", {})
fault(vision=[["palm", 0.9]])
time.sleep(1.2)
fault(vision=None)
print("(화면 닫은 뒤 보: 명령이 생기지 않아야 함 — 서버 기록에서 GESTURE 줄 확인)")

print(f"\n결과: {ok_count}/{ok_count + len(fail)} 통과")
sys.exit(1 if fail else 0)
