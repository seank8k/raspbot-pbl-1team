#!/usr/bin/env python3
# 지시서: specs/01-webabb.md · specs/04-line-tracer.md — 웹 화면 대신 「라인 따라가기」를 켜고 끝날 때까지 지켜본다.
# 실행 (라즈봇 안 · 서버가 켜져 있을 때): python3 tools/line_run.py [최대초=40]
# 바퀴는 웹 서버의 규칙대로만 움직인다. 끝나거나 오류가 나면 라인을 끄고 정지 요청. 이 프로그램이 죽어도 서버가 1초 뒤 스스로 멈춘다.
import http.cookiejar
import json
import sys
import threading
import time
import urllib.request

BASE = "http://127.0.0.1:5000"
LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
seq = [0]
beating = threading.Event()


def call(path, data=None):
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"}, method="GET" if data is None else "POST")
    try:
        with opener.open(req, timeout=3) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def nseq():
    seq[0] += 1
    return seq[0]


def beater():
    while True:
        if beating.is_set():
            call("/api/line", dict(seq=nseq(), press=1, on=True))
        time.sleep(0.25)


def stop_all():
    beating.clear()
    call("/api/line", dict(seq=nseq(), press=1, on=False))
    call("/api/stop", dict(seq=nseq(), press=1))


try:
    c = call("/api/claim", {})
    print("자리:", c.get("slot_name"), c.get("ok"), flush=True)
    threading.Thread(target=beater, daemon=True).start()
    call("/api/line", dict(seq=nseq(), press=1, on=True))
    beating.set()
    t0, last = time.monotonic(), None
    while time.monotonic() - t0 < LIMIT:
        s = call("/api/status")
        ln = s.get("line", {}) or {}
        now = (ln.get("active"), s.get("move"), ln.get("reason"))
        if now != last:
            print(f"{time.monotonic() - t0:6.2f}s  라인={ln.get('active')}  동작={s.get('move')}  이유={ln.get('reason')}", flush=True)
            last = now
        if time.monotonic() - t0 > 1.5 and not ln.get("active"):
            break
        time.sleep(0.1)
finally:
    stop_all()
    print("라인 끔 · 정지 요청 보냄", flush=True)
