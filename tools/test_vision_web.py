#!/usr/bin/env python3
# 지시서: specs/06-person-stop.md · specs/08-hand-gesture.md — 웹 조종 서버의 인식 결과 확인 (바퀴 안 움직임)
# 실행: 먼저 python3 missions/webabb.py --dry --port 5001 > /tmp/vdry.out 2>&1 &
#       그다음 python3 tools/test_vision_web.py 5001 [초=20]
import http.cookiejar
import json
import sys
import time
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5001
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 20
BASE = f"http://127.0.0.1:{PORT}"
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(path, data=None):
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if data is None else "POST")
    try:
        with opener.open(req, timeout=3) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


ok_count, fail = 0, []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
    else:
        fail.append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail != "" else ""), flush=True)


code, _ = call("/api/vision")
check("자리 없이 /api/vision → 거부", code == 403, code)
code, cfg = call("/api/config")
check("설정에 vision 켜짐", cfg.get("vision") is True, cfg.get("vision"))
call("/api/claim", {})
t0, v = time.monotonic(), {}
while time.monotonic() - t0 < 15:
    _, v = call("/api/vision")
    if v.get("ready"):
        break
    time.sleep(0.2)
check("인식 준비 끝 (15초 안)", v.get("ready"), v.get("error"))
ages, rates, mss, labels, stops = [], [], [], {}, 0
end = time.monotonic() + SECS
while time.monotonic() < end:
    _, v = call("/api/vision")
    if v.get("ready"):
        ages.append(v["age"]); rates.append(v["rate"]); mss.append(v["ms"])
        stops += bool(v.get("stop"))
        for d in v["items"]:
            labels[d["label"]] = labels.get(d["label"], 0) + 1
            assert 0 <= d["box"][0] <= 1 and 0 <= d["box"][1] <= 1
    time.sleep(0.2)
_, s = call("/api/status")
check("인식 결과가 늘 1초 안 (멈춤 없음)", ages and max(ages) <= 1.0, f"최대 {max(ages) if ages else None}초")
check("인식 횟수 초당 5번 이상", rates and min(rates[5:] or rates) >= 5, f"중간 {sorted(rates)[len(rates) // 2] if rates else None}번/초")
check("제어 한 바퀴 최대 0.1초 안 (인식이 제어를 안 막음)", s.get("ctl_max_gap", 9) <= 0.1, s.get("ctl_max_gap"))
check("감시 개입 0", s.get("guard_count") == 0, s.get("guard_count"))
check("영상 멈춤 없음", (s.get("frame_age") or 9) < 0.8, s.get("frame_age"))
print(f"인식 한 번 {sorted(mss)[len(mss) // 2] if mss else '-'}ms(중간) · 찾은 것(조회 횟수) {labels} · STOP 표시 {stops}번")
print(f"\n결과: {ok_count}/{ok_count + len(fail)} 통과")
sys.exit(1 if fail else 0)
