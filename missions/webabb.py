#!/usr/bin/env python3
# 지시서: specs/01-webabb.md(Codex 적대적 리뷰 반영판 · 휴대폰 1대 + 컴퓨터 1대 · 2026-11-02)
#         specs/03-blackbox.md (블랙박스 녹화 — missions/blackbox.py · 2026-11-03)
#         specs/04-line-tracer.md (라인 따라가기 모드 — 판단은 missions/line.py · 2026-11-03)
#         specs/05-obstacle-stop.md (장애물 잠깐 멈춤 — 라인 따라가기와 같이 켜짐 · 판단은 missions/obstacle.py · 2026-11-04)
#         specs/06-person-stop.md · specs/08-hand-gesture.md (인식 결과 화면 표시만 · 바퀴 안 씀 · missions/detect.py · 2026-11-05)
# 웹 브라우저(노트북 · 휴대폰)에서 버튼 · 키보드로 라즈봇을 조종하고 카메라 화면을 본다.
#
# 실행:   python3 missions/webabb.py              (바퀴가 움직임 — 안전 수칙 확인 후)
#         python3 missions/webabb.py --dry        (바퀴 안 움직임 · 명령만 기록)
#         python3 missions/webabb.py --no-camera  (카메라 없이 — 「영상 멈춤 정지」 규칙도 꺼짐)
#         python3 missions/webabb.py --dry --fault (깨뜨리는 시험용 고장 주입 주소를 켬 · dry 에서만)
# 접속:   http://raspibot-01.local:5000
# 끝내기: Ctrl+C
#
# 안전 구조 (리뷰 반영)
#  - 바퀴에 명령을 쓰는 것은 「제어 스레드」 하나뿐이다. 웹 요청은 원하는 상태만 적어 둔다.
#  - 화면은 메시지마다 순번(seq)과 누름 번호(press)를 붙인다. 순번이 거꾸로 온 메시지는 버린다.
#    한 번 멈춘 누름 번호(floor 이하)의 이동은 다시 실행하지 않는다 → 새로 눌러야 움직인다.
#  - 휴대폰 자리 · 컴퓨터 자리가 따로 있다. 먼저 누른 기기가 손을 뗄 때까지 다른 기기 입력은 무시하고,
#    무시된 누름은 다시 눌러야 한다. 어느 기기든 정지 버튼 · 비상정지는 둘 다 멈춘다.
#  - 정지는 네 바퀴 각각 따로 시도한다. 실패하면 주행을 잠그고 다음 주기에 다시 시도한다.
#    멈춰 있는 동안에도 0.5초마다 「0」을 다시 보낸다.
#  - 드라이버(Raspbot_Lib)는 I2C 오류를 print 만 하고 삼키므로, 같은 명령(레지스터 0x01)을 직접 보내 오류를 잡는다.
#  - 감시 스레드가 제어 스레드의 심장 박동을 본다. 멈추면 직접 0 을 보내고 주행을 거부한다.
#  - 프로그램이 강제로 죽는 경우(kill -9 · 전원)는 이 프로그램이 막을 수 없다 → 보드 동작은 실험으로 확인 ·
#    물리 비상정지는 확장보드 전원 스위치.
import argparse
import os
import secrets
import signal
import threading
import time
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, make_response, request, send_from_directory

from line import LineFollower, decode as line_decode, encode as line_encode, CENTER as LINE_CENTER   # 지시서 04 판단 부분
import obstacle as obs                                   # 지시서 05 장애물 판단 부분
from sight import SightJudge, CONF as SIGHT_CONF         # 지시서 06 사람 · STOP 표지판 멈춤 판단 부분
from gesture import GestureJudge                         # 지시서 08 손 모양 명령 판단 부분

# ---------------- 지시서에서 정한 값 ----------------
PORT = 5000
SPEED_DEFAULT = 120
SPEED_MIN, SPEED_MAX = 40, 150    # 150 = 프로젝트 한계
WATCHDOG = 0.4                    # 「계속 가」 신호가 이만큼 없으면 정지
CAM_STALE = 0.8                   # 새 카메라 화면이 이만큼 없으면 정지 (판정 · 정지까지 합쳐 1초 안)
OWNER_TIMEOUT = 3.0               # 조종하던 화면이 이만큼 조용하면 자리 비움
TICK = 0.02                       # 제어 주기 (초)
ZERO_RESEND = 0.5                 # 멈춰 있을 때 0 을 다시 보내는 간격
GUARD_LIMIT = 0.3                 # 제어 스레드 심장 박동이 이만큼 끊기면 감시 스레드가 개입
STALL_LIMIT = 0.1                 # 한 번 판단하는 데 이보다 오래 걸렸으면 그 판단(옛 정보)으로 움직이지 않음
CAM_W, CAM_H, CAM_FPS, JPEG_QUALITY = 640, 480, 10, 70
LINE_SPEED = 80                   # 라인 따라가기 속도 (지시서 04: 60 → 90 → 80 조원 결정 2026-11-04 · 90 충돌 뒤 · 제자리 회전은 line.py 40)
LINE_SPEED_STEP, LINE_SPEED_MAX = 10, 90   # 지시서 08 엄지척: +10 · 최대 90 (Claude 제안)
GESTURE_PERSON_SKIP = 3.0         # 지시서 08 보: 명령 뒤 사람 멈춤을 쉬는 시간 (Claude 제안)
ULTRA_LOG_MM = 400                # 라인 중 초음파가 이보다 가까우면 값이 바뀔 때마다 기록 (지시서 05 · 늦은 감지 확인용)
LINE_BEAT_TIMEOUT = 1.0           # 「라인 계속」 신호가 이만큼 없으면 정지 (지시서 04)
SENSOR_LIMIT = 0.05               # 라인센서 읽기가 이보다 오래 걸리면 실패로 봄 (2026-11-03 실측 최대 0.78ms)
ULTRA_LIMIT = 0.05                # 초음파 읽기(3번)가 이보다 오래 걸리면 실패로 봄 (2026-11-04 실측 최대 1.29ms)
ALERT_LIMIT = 0.05                # 불빛 · 부저 쓰기가 이보다 오래 걸리면 그 뒤로 알림은 화면만 (지시서 05 #16)
BEEP_S = 0.1                      # 잠깐 멈춤 순간 부저 길이 (지시서 05)
RESTART_CONFIRM = 2               # 치워진 뒤 가운데 칸이 연속 이만큼 보여야 다시 출발 (지시서 05 #13)
SLOTS = ("any",)                  # 조종 자리 1개 — 기기 종류와 상관없이 먼저 접속한 한 대만 (2026-11-02 조원 결정)
SLOT_NAME = {"any": "기기"}

# 바퀴 부호 (왼앞, 왼뒤, 오앞, 오뒤)
SINGLE = {
    "fwd": (1, 1, 1, 1),
    "back": (-1, -1, -1, -1),
    "left": (-1, 1, 1, -1),
    "right": (1, -1, -1, 1),
    "turn_left": (-1, -1, 1, 1),
    "turn_right": (1, 1, -1, -1),
}
DIAGONAL = {  # (앞뒤, 좌우): 앞=+1 뒤=-1, 오른쪽=+1 왼쪽=-1 — 지시서 「동시에 누르기 표」
    (1, 1): ("앞 오른쪽 대각선", (1, 0, 0, 1)),
    (1, -1): ("앞 왼쪽 대각선", (0, 1, 1, 0)),
    (-1, 1): ("뒤 오른쪽 대각선", (0, -1, -1, 0)),
    (-1, -1): ("뒤 왼쪽 대각선", (-1, 0, 0, -1)),
}
NAMES = {"fwd": "앞", "back": "뒤", "left": "옆으로 왼쪽", "right": "옆으로 오른쪽",
         "turn_left": "제자리 왼쪽", "turn_right": "제자리 오른쪽"}
ZERO = (0, 0, 0, 0)

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "webabb")

parser = argparse.ArgumentParser()
parser.add_argument("--dry", action="store_true")
parser.add_argument("--no-camera", action="store_true")
parser.add_argument("--no-detect", action="store_true", help="사람 · STOP · 손 모양 인식 끄기 (지시서 06 · 08)")
parser.add_argument("--fault", action="store_true")
parser.add_argument("--port", type=int, default=PORT, help="시험할 때 다른 포트로 (기본 5000)")
# 블박 (지시서 03) — 아래 값은 시험할 때만 바꾼다
parser.add_argument("--bb-dir", default=os.path.join(os.path.dirname(HERE), "results", "blackbox"))
parser.add_argument("--bb-limit-mb", type=float, default=2048, help="블박 폴더 한도 (기본 2GB)")
parser.add_argument("--bb-file-mb", type=float, default=200, help="파일 하나 한도 (기본 200MB)")
parser.add_argument("--bb-segment-s", type=float, default=180, help="파일 길이 (기본 3분)")
parser.add_argument("--bb-min-free-mb", type=float, default=1024, help="SD 빈 공간 최소 (기본 1GB)")
args = parser.parse_args()
PORT = args.port
if args.fault and not args.dry:
    raise SystemExit("--fault 는 --dry 와 같이만 쓸 수 있습니다")


def log(msg):
    t = time.time()
    print(time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d}  {msg}", flush=True)


def mix(keys, speed):
    """지금 눌린 것 전체 → (이름, 네 바퀴 속도). 지시서 「동시에 누르기 표」."""
    k = {x for x in keys if x in SINGLE}
    if not k:
        return "정지", ZERO
    if "turn_left" in k or "turn_right" in k:
        if len(k) == 1:
            d = next(iter(k))
            return NAMES[d], tuple(s * speed for s in SINGLE[d])
        return "안 움직임 (회전 + 다른 버튼)", ZERO
    if "left" in k and "right" in k:
        return "안 움직임 (왼쪽 + 오른쪽)", ZERO
    if "fwd" in k and "back" in k:
        return "안 움직임 (앞 + 뒤)", ZERO
    v = 1 if "fwd" in k else -1 if "back" in k else 0
    h = 1 if "right" in k else -1 if "left" in k else 0
    if v and h:
        name, signs = DIAGONAL[(v, h)]
        return name, tuple(s * speed for s in signs)
    d = "fwd" if v == 1 else "back" if v == -1 else "right" if h == 1 else "left"
    return NAMES[d], tuple(s * speed for s in SINGLE[d])


# ---------------- 바퀴 출력 (오류를 삼키지 않음) ----------------
class Motors:
    def __init__(self, dry):
        self.dry = dry
        self.fail_next = 0      # 고장 주입: 다음 n 번 쓰기 실패
        self.hang_next = 0.0    # 고장 주입: 다음 쓰기에서 n 초 멈춤
        self.sensor_fail_next = 0     # 고장 주입: 다음 n 번 라인센서 읽기 실패
        self.sensor_delay_next = 0.0  # 고장 주입: 다음 라인센서 읽기에서 n 초 멈춤
        self.dry_line = None          # dry: 가짜 라인센서 바이트 (고장 주입 주소로 바꿈)
        self.dry_ultra = 600          # dry: 가짜 초음파 mm · "fail" · "torn" (고장 주입 주소로 바꿈)
        self.dev = self.addr = None
        if not dry:
            from Raspbot_Lib import Raspbot
            bot = Raspbot()
            self.dev, self.addr = bot._device, bot._addr  # 드라이버와 같은 I2C 장치 · 주소

    def write(self, speeds):
        """네 바퀴를 각각 쓴다. 실패한 바퀴 번호 목록을 돌려준다(빈 목록 = 성공)."""
        failed, last_err = [], None
        for motor_id, sp in enumerate(speeds):
            try:
                if self.hang_next:
                    h, self.hang_next = self.hang_next, 0.0
                    time.sleep(h)
                if self.fail_next:
                    self.fail_next -= 1
                    raise OSError("주입된 I2C 오류")
                if not self.dry:
                    sp = max(-SPEED_MAX, min(SPEED_MAX, int(sp)))
                    self.dev.write_i2c_block_data(self.addr, 0x01, [motor_id, 1 if sp < 0 else 0, abs(sp)])
            except Exception as e:  # 한 바퀴가 실패해도 나머지 바퀴는 계속 시도
                failed.append(motor_id)
                last_err = e
        if failed:
            log(f"!! 바퀴 쓰기 실패 {failed}: {last_err}")
        return failed

    def read_line(self):
        """라인센서 바이트(레지스터 0x0a). 실패면 None — 드라이버처럼 오류를 삼키지 않고, 이전 값을 대신 주지 않는다."""
        try:
            if self.sensor_delay_next:
                d, self.sensor_delay_next = self.sensor_delay_next, 0.0
                time.sleep(d)
            if self.sensor_fail_next:
                self.sensor_fail_next -= 1
                raise OSError("주입된 센서 오류")
            if self.dry:
                return self.dry_line
            data = self.dev.read_i2c_block_data(self.addr, 0x0a, 1)
            if not data or len(data) != 1 or not 0 <= data[0] <= 255:
                return None
            return data[0]
        except Exception as e:
            log(f"!! 라인센서 읽기 실패: {e}")
            return None

    def _byte(self, reg):
        data = self.dev.read_i2c_block_data(self.addr, reg, 1)
        if not data or len(data) != 1 or not 0 <= data[0] <= 255:
            raise OSError(f"레지스터 {reg:#x} 값 이상: {data}")
        return data[0]

    def read_ultra(self):
        """초음파 거리 (지시서 05 #7 · #17). 상위(0x1b) → 하위(0x1a) → 상위 한 바이트씩.
        돌려줌: ("ok", mm) · ("torn", None) 상위 두 번이 달라 버림 · ("fail", None) 읽기 오류."""
        try:
            if self.dry:
                v = self.dry_ultra
                return ("fail", None) if v == "fail" else ("torn", None) if v == "torn" else ("ok", int(v))
            h1 = self._byte(0x1b)
            lo = self._byte(0x1a)
            h2 = self._byte(0x1b)
            if h1 != h2:
                return "torn", None
            return "ok", h1 << 8 | lo
        except Exception as e:
            log(f"!! 초음파 읽기 실패: {e}")
            return "fail", None

    def write_reg(self, reg, data):
        """불빛(0x03) · 부저(0x06) · 초음파 켜기(0x07) — 드라이버와 같은 레지스터, 오류는 돌려줌. 성공 True."""
        if self.dry:
            return True
        try:
            self.dev.write_i2c_block_data(self.addr, reg, list(data))
            return True
        except Exception as e:
            log(f"!! 쓰기 실패 (레지스터 {reg:#x}): {e}")
            return False


motors = Motors(args.dry)


# ---------------- 카메라 ----------------
class Camera:
    def __init__(self, enabled):
        self.enabled = enabled
        self.frame = None
        self.frame_time = None  # 마지막으로 새 화면을 받은 시각 (monotonic)
        self.raw, self.raw_time = None, None   # 인식용 최신 원본 장면 1장 + 찍은 시각 (밀린 장면은 덮어씀 · 06 리뷰 #1 · #8)
        self.lock = threading.Lock()
        self.running = enabled
        self.cap = None
        self.paused = False     # 고장 주입: 영상 멈춤
        if enabled:
            threading.Thread(target=self._loop, daemon=True, name="camera").start()

    def _loop(self):
        import cv2
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
        if not self.cap.isOpened():
            log("카메라를 못 열었습니다 → 영상이 없으면 주행도 안 됩니다 (--no-camera 로 끌 수 있음)")
            return
        log(f"카메라 켜짐 {CAM_W}x{CAM_H} · 최대 {CAM_FPS}장/초")
        params = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        period = 1.0 / CAM_FPS
        next_t = time.monotonic()
        while self.running:
            try:
                ok, img = self.cap.read()
                t_mono, t_wall = time.monotonic(), time.time()   # 장면을 받은 시각 (블박에 찍힘)
                if ok and not self.paused:
                    ok2, buf = cv2.imencode(".jpg", img, params)
                    if ok2:
                        with self.lock:    # 잠금은 바꿔 끼우는 순간만
                            self.frame, self.frame_time = buf.tobytes(), time.monotonic()
                            self.raw, self.raw_time = img, t_mono   # 참조만 넘김 (cap.read 가 장면마다 새 배열)
                    if recorder is not None:
                        recorder.submit(img, t_mono, t_wall)   # 잠금 밖 · 넣어 보기만 (꽉 차면 버림)
                else:
                    time.sleep(0.05)
            except Exception as e:
                log(f"카메라 오류: {e}")
                time.sleep(0.2)
            # 「다음 칸 시각까지만」 쉰다 (처리 뒤 0.1초를 또 쉬면 초당 10장이 안 나옴 — 03 리뷰 #4)
            next_t += period
            now = time.monotonic()
            if next_t > now:
                time.sleep(next_t - now)
            else:
                next_t = now

    def age(self):
        if not self.enabled:
            return 0.0
        with self.lock:
            return float("inf") if self.frame_time is None else time.monotonic() - self.frame_time

    def latest(self):
        with self.lock:
            return self.frame, self.frame_time

    def latest_raw(self):
        with self.lock:
            return self.raw, self.raw_time

    def close(self):
        self.running = False
        if self.cap is not None:
            self.cap.release()


recorder = None
if not args.no_camera:
    # OpenCV 를 여기(시작 전, 한 스레드)에서 미리 불러 둔다 — 여러 스레드가 동시에 불러오면
    # 그동안 다른 스레드가 멈출 수 있음 (2026-11-03 블박 시험에서 제어 0.74초 멈춤 관찰)
    import cv2  # noqa: F401
    from blackbox import Recorder, MiB
    recorder = Recorder(args.bb_dir, fps=CAM_FPS, segment_s=args.bb_segment_s,
                        folder_limit=int(args.bb_limit_mb * MiB), file_limit=int(args.bb_file_mb * MiB),
                        min_free=int(args.bb_min_free_mb * MiB), size=(CAM_W, CAM_H), log=log)
camera = Camera(not args.no_camera)


# ---------------- 인식 (지시서 06 · 08 — 화면 표시만 · 바퀴에는 안 씀) ----------------
VISION_HZ = 10            # 초당 최대 인식 횟수 (06 설계 · Claude 제안)
VISION_STALE = 1.0        # 결과가 이보다 오래되면 화면에 「인식 멈춤」 (표시용 임시 값 · 조원 결정 전)


class Vision:
    def __init__(self, enabled):
        self.lock = threading.Lock()
        self.enabled = enabled
        self.models = []
        self.result = None        # dict(t_capture, t_done, ms, items)
        self.error = None
        self.rate = 0.0
        self.fake = None          # 고장 주입(--dry --fault): 가짜 인식 결과 [(이름, 확신도)] · "stale"
        if enabled:
            threading.Thread(target=self._loop, daemon=True, name="vision").start()

    def _loop(self):
        import detect
        self.models = detect.load_models(log=log)
        if not self.models:
            self.error = "모델 없음 (models/ 확인)"
            return
        names = " + ".join(t for t, _ in self.models)
        log(f"인식 켬: {names} · 초당 최대 {VISION_HZ}번 · 화면 표시만 (바퀴 안 씀)")
        period, last_t, done = 1.0 / VISION_HZ, None, []
        while True:
            t0 = time.monotonic()
            img, t_cap = camera.latest_raw()
            if img is None or t_cap == last_t:            # 새 장면이 없으면 같은 장면을 또 보지 않음
                time.sleep(0.01)
                continue
            last_t = t_cap
            try:
                items = []
                for tag, m in self.models:
                    for d in m.detect(img):
                        d["model"] = tag
                        items.append(d)
                t1 = time.monotonic()
                done = [t for t in done if t1 - t < 2.0] + [t1]
                with self.lock:
                    self.result = dict(t_capture=t_cap, t_done=t1, ms=round((t1 - t0) * 1000), items=items)
                    self.rate = len(done) / 2.0
                    self.error = None
            except Exception as e:
                if self.error is None:
                    log(f"!! 인식 오류: {e}")
                with self.lock:
                    self.error = str(e)
            wait = period - (time.monotonic() - t0)
            if wait > 0:
                time.sleep(wait)

    def status(self):
        if not self.enabled:
            return dict(enabled=False)
        if self.fake is not None:                 # 깨뜨리는 시험용 — 0.1초마다 「새 결과」로 보이게
            now = time.monotonic()
            if self.fake == "stale":
                return dict(enabled=True, ready=True, error=None, age=5.0, stale=True, ms=0, rate=0.0, items=[],
                            t_capture=now - 5.0, stop=False)
            items = [dict(label=l, conf=float(c), box=(0.4, 0.3, 0.2, 0.4), model="fake") for l, c in self.fake]
            return dict(enabled=True, ready=True, error=None, age=0.05, stale=False, ms=0, rate=10.0, items=items,
                        t_capture=round(now * 10) / 10, stop=any(d["label"] in ("person", "stop sign") and d["conf"] >= SIGHT_CONF for d in items))
        with self.lock:
            r, err, rate = self.result, self.error, self.rate
        if r is None:
            return dict(enabled=True, ready=False, error=err)
        age = time.monotonic() - r["t_capture"]
        items = r["items"]
        stop = any(d["label"] in ("person", "stop sign") and d["conf"] >= SIGHT_CONF for d in items)   # 멈춤 기준과 같게 (06 · 0.65)
        return dict(enabled=True, ready=True, error=err, age=round(age, 2), stale=age > VISION_STALE,
                    ms=r["ms"], rate=round(rate, 1), items=items, stop=stop and age <= VISION_STALE,
                    t_capture=r["t_capture"])


vision = Vision(camera.enabled and not args.no_detect)


# ---------------- 조종 자리 (휴대폰 1 · 컴퓨터 1) ----------------
class Seat:
    def __init__(self, slot):
        self.slot = slot
        self.token = None
        self.who = None
        self.gen = 0            # 자리가 바뀔 때마다 1 증가 — 이전 사람의 명령은 모두 무효
        self.last_seen = 0.0
        self.stream = 0         # 영상 스트림 번호 (자리당 1개)


class Seats:
    def __init__(self):
        self.lock = threading.Lock()
        self.s = {k: Seat(k) for k in SLOTS}

    @staticmethod
    def kind_of(user_agent):
        return "any"            # 자리가 하나뿐이라 기기 종류를 나누지 않음

    def _alive(self, st, now):
        return st.token and now - st.last_seen <= OWNER_TIMEOUT

    def _expire(self, st, now):
        if st.token and not self._alive(st, now):
            log(f"자리 비움: {SLOT_NAME[st.slot]} {st.who} ({OWNER_TIMEOUT}초 동안 연결 없음)")
            st.token = None
            st.gen += 1

    def claim(self, token, who, slot):
        with self.lock:
            now = time.monotonic()
            for st in self.s.values():          # 같은 브라우저(쿠키) → 자리 그대로 (새로고침)
                if token and st.token == token and self._alive(st, now):
                    st.last_seen = now
                    return st.slot, st.gen, False
            st = self.s[slot]
            self._expire(st, now)
            if st.token:
                return None, None, False
            st.token, st.who, st.last_seen = secrets.token_hex(16), who, now
            st.gen += 1
            log(f"조종 시작: {SLOT_NAME[slot]} {who} (자리 {st.gen}번)")
            return slot, st.gen, True

    def token_of(self, slot):
        with self.lock:
            return self.s[slot].token

    def touch(self, token):
        """만료 검사까지 한 번에. 유효하면 (자리 종류, 자리 번호), 아니면 (None, None)."""
        with self.lock:
            now = time.monotonic()
            for st in self.s.values():
                if token and st.token == token:
                    if self._alive(st, now):
                        st.last_seen = now
                        return st.slot, st.gen
                    self._expire(st, now)
            return None, None

    def current_gen(self, slot):
        with self.lock:
            now = time.monotonic()
            st = self.s[slot]
            self._expire(st, now)
            return st.gen if st.token else None

    def release(self, token):
        with self.lock:
            for st in self.s.values():
                if token and st.token == token:
                    log(f"조종 끝: {SLOT_NAME[st.slot]} {st.who} (창 닫음 · 새로고침)")
                    st.token = None
                    st.gen += 1
                    return st.slot
            return None

    def new_stream(self, slot):
        with self.lock:
            self.s[slot].stream += 1
            return self.s[slot].stream

    def stream_of(self, slot):
        with self.lock:
            return self.s[slot].stream


seats = Seats()


# ---------------- 원하는 상태 (자리마다 하나 · 웹 요청이 적고 제어 스레드가 읽음) ----------------
class Wish:
    """floor(이 누름 번호 이하는 다시 움직이지 않음)는 여기 한 곳에서만 관리한다.
    정지 · 비상정지는 요청을 받는 그 순간 floor 를 올리므로, 제어 스레드가 읽기 전에
    같은 누름 번호의 이동이 와서 정지를 덮어써도 다시 움직이지 않는다."""

    def __init__(self):
        self.lock = threading.Lock()
        self.gen = None
        self.last_seq = 0
        self.kind = "stop"      # "move" · "line"(라인 따라가기) · "stop"
        self.press = 0
        self.max_press = 0
        self.floor = 0
        self.keys = ()
        self.speed = SPEED_DEFAULT
        self.recv = 0.0
        self.press_start = 0.0  # 지금 누름 번호가 처음 도착한 시각 (먼저 누른 기기 판정)

    def _reset_if_new(self, gen):
        if gen != self.gen:
            self.gen, self.last_seq, self.press, self.max_press, self.floor = gen, 0, 0, 0, 0
            self.kind, self.keys = "stop", ()

    def put(self, gen, seq, kind, press, keys=(), speed=SPEED_DEFAULT):
        with self.lock:
            self._reset_if_new(gen)
            if seq <= self.last_seq:
                return False                    # 늦게 도착한 옛 메시지 → 버림
            self.last_seq = seq
            self.max_press = max(self.max_press, press)
            if kind == "stop":
                self.floor = max(self.floor, press)
            elif press <= self.floor:
                return False                    # 멈춘 누름 번호 → 새로 눌러야 함
            if kind == "move" and self.kind == "line" and self.press > self.floor and press != self.press:
                # 라인 따라가기 중 방향 버튼 첫 누름 = 끄고 멈추기만 (지시서 04) → 손 떼고 다시 눌러야 수동
                self.floor = max(self.floor, press)
                self.kind = "stop"
                return False
            now = time.monotonic()
            if kind in ("move", "line") and (press != self.press or self.kind != kind):
                self.press_start = now
            self.kind, self.press, self.keys, self.speed = kind, press, tuple(keys), speed
            self.recv = now
            return True

    def raise_floor(self, press=None):
        with self.lock:
            self.floor = max(self.floor, self.max_press if press is None else press)

    def need_new_press(self, press):
        with self.lock:
            return press <= self.floor

    def snapshot(self):
        with self.lock:
            return dict(gen=self.gen, kind=self.kind, press=self.press, keys=self.keys, floor=self.floor,
                        speed=self.speed, recv=self.recv)


wishes = {k: Wish() for k in SLOTS}
estop_flag = threading.Event()
guard_tripped = threading.Event()   # 감시 스레드가 직접 0 을 보냈음 → 제어부는 「정지」로 다시 맞추고, 다시 눌러야 움직임


def save_photo(img):
    """지시서 08 브이: 사진 1장 → results/photos/ (깃에 안 올림 · 얼굴)"""
    try:
        import cv2
        d = os.path.join(os.path.dirname(HERE), "results", "photos")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, time.strftime("%Y-%m-%d_%H-%M-%S") + ".jpg")
        cv2.imwrite(p, img)
        log(f"사진 저장: {os.path.relpath(p, os.path.dirname(HERE))}")
    except Exception as e:
        log(f"!! 사진 저장 실패: {e}")


def stop_everyone(why):
    """정지 버튼 · 비상정지 · 창 닫기: 두 자리의 지금까지 누름을 모두 멈춤."""
    for w in wishes.values():
        w.raise_floor()
    estop_flag.set()
    ctl.estop_reason = why


# ---------------- 제어 스레드 (바퀴에 쓰는 유일한 곳) ----------------
class Controller:
    def __init__(self):
        self.out = ZERO          # 마지막으로 성공적으로 쓴 값
        self.out_name = "정지"
        self.driver = None       # 지금 움직이고 있는 자리 ("phone" / "computer" / None)
        self.locked = False      # 정지 실패 → 주행 잠금
        self.reason = "시작"
        self.estop_reason = "비상정지"
        self.beat = time.monotonic()
        self.max_gap = 0.0
        self.guard_count = 0     # 감시 스레드가 개입한 횟수
        self.last_zero = 0.0
        self.shutting = False
        self.done = threading.Event()
        self.line_key = None     # (자리, 자리 번호, 라인 누름 번호) — 바뀌면 판단을 처음부터
        self.follower = None
        self.line_view = dict(pattern=None, action="꺼짐", reason=None)
        self.line_log_pat = None # 기록에 마지막으로 남긴 센서 값 (지시서 04 · 바뀔 때마다 기록 2026-11-04)
        # 지시서 05 장애물 — 라인 따라가기를 켜면 같이 켜짐 (따로 버튼 없음)
        self.judge = obs.ObstacleJudge(on_time=time.monotonic())   # 시작할 때 초음파를 켬 (main)
        self.sight = SightJudge()  # 지시서 06: 사람 = 보이는 동안 멈춤 · STOP 표지판 = 3초 멈춤 (라인 중에만)
        self.sight_held = False
        self.obs_view = dict(mm=None, state="꺼짐", left=None)
        self.obs_paused = False  # 이번 주기에 장애물 잠깐 멈춤 중인가 (불빛 · 부저 판단용)
        self.center_seen = 0     # 치워진 뒤 가운데 칸 연속 횟수
        self.light_on = False
        self.beep_until = None
        self.alerts_ok = True    # 알림 쓰기가 0.05초를 넘으면 False → 그 뒤로 화면만
        self.cur_press = None    # 지금 움직이는 누름 번호 (쓰기 직전 다시 확인 · 지시서 05 #3)
        self.ultra_log_mm = None # 기록에 마지막으로 남긴 초음파 값
        # 지시서 08 손 모양 명령 — 보 출발 · 주먹 멈춤 · 엄지척 빠르게 · 브이 사진
        self.gesture = GestureJudge()
        self.gesture_event = None   # 화면에 알릴 마지막 명령 dict(id, cmd, t)
        self.line_speed = LINE_SPEED

    def _live(self, slot, now):
        """이 자리가 지금 움직이고 싶어하는가? (이유, 원하는지) — 끊김 · 영상 멈춤이면 floor 를 올림."""
        s = wishes[slot].snapshot()
        gen = seats.current_gen(slot)
        if gen is None or s["gen"] != gen or s["kind"] not in ("move", "line") or s["press"] <= s["floor"]:
            return None, s
        limit = LINE_BEAT_TIMEOUT if s["kind"] == "line" else WATCHDOG
        if now - s["recv"] > limit:
            wishes[slot].raise_floor(s["press"])
            what = "라인 계속" if s["kind"] == "line" else SLOT_NAME[slot]
            return f"{what} 신호 {limit}초 끊김", None
        if s["kind"] == "line" and not camera.enabled:
            wishes[slot].raise_floor(s["press"])
            return "카메라 없이(--no-camera) 라인 모드 못 씀", None
        if camera.age() > CAM_STALE:
            wishes[slot].raise_floor(s["press"])
            return f"영상 {CAM_STALE}초 멈춤", None
        if self.locked:
            wishes[slot].raise_floor(s["press"])
            return "정지 실패 잠금", None
        return "ok", s

    def _line(self, slot, s, now):
        """라인 따라가기 한 번: 라인센서 읽기 → 초음파 읽기 → 장애물 판단 → 라인 판단.
        (이름, 바퀴 값, 멈춘 이유 또는 None) — 이유가 있으면 라인 모드를 끈다."""
        t0 = time.monotonic()
        byte = motors.read_line()                    # 잠깐 멈춤 중에도 늘 읽음 (센서 건강 · 지시서 05 #12)
        took = time.monotonic() - t0
        pattern = line_decode(byte) if took <= SENSOR_LIMIT else None
        t1 = time.monotonic()
        ukind, umm = motors.read_ultra()
        if time.monotonic() - t1 > ULTRA_LIMIT:
            ukind, umm = "fail", None
        key = (slot, s["gen"], s["press"])
        if self.line_key != key:                     # 새로 켬 → 판단을 처음부터 · 켜는 순간 검사
            self.line_key = key
            self.line_speed = LINE_SPEED             # 라인을 다시 켜면 80으로 (08 엄지척은 달리는 중에만)
            self.follower = LineFollower(self.line_speed)
            self.judge.reset()                       # 장애물 타이머도 처음부터 (#15)
            self.sight.reset()                       # 사람 · STOP 타이머도 처음부터 (06)
            self.sight_held = False
            self.center_seen = 0
            ok, why = self.follower.start(pattern)
            if ok and vision.enabled:
                v0 = vision.status()
                if not v0.get("ready") or v0.get("stale") or v0.get("error"):
                    ok, why = False, "인식 준비 중 — 잠시 뒤 다시"   # 06: 인식이 안 되는데 출발하지 않음
            if ok:
                st0, why0, _ = self.judge.update(ukind, umm, now)
                if st0 == obs.NOT_READY:
                    ok, why = False, "초음파 준비 중 (켠 뒤 1초) — 잠시 뒤 다시"
                elif st0 == obs.FAIL:
                    ok, why = False, why0
                elif st0 == obs.PAUSE:
                    ok, why = False, f"앞에 장애물 ({why0}) — 치우고 다시"
                    self.judge.reset()
            if not ok:
                self.line_view = dict(pattern=pattern, action="정지", reason=why)
                log(f"LINE 출발 안 함: {why}")
                return "정지", ZERO, why
            log(f"LINE 시작 (속도 {self.line_speed} · 센서 {pattern} · 초음파 {umm}mm)")
            self.line_log_pat = pattern
        else:
            # ---- 장애물 (지시서 05) ----
            if ukind == "torn":
                log("   초음파 읽기 버림 (상위 바이트 두 번이 다름)")
            elif ukind == "ok" and umm < ULTRA_LOG_MM and umm != self.ultra_log_mm:
                log(f"   초음파 {umm}mm · 센서 {pattern}")   # 늦은 감지 확인용 (400mm 안에서 값이 바뀔 때마다)
            if ukind == "ok":
                self.ultra_log_mm = umm
            was_paused = self.judge.state == obs.PAUSE
            st, owhy, left = self.judge.update(ukind, umm, now)
            self.obs_view = dict(mm=self.judge.mm, state=st, left=None if left is None else round(left, 1))
            if st in (obs.FAIL, obs.NOT_READY):
                why = owhy if st == obs.FAIL else "초음파 준비 안 됨"
                self.line_view = dict(pattern=pattern, action="정지", reason=why)
                log(f"LINE 끝: {why}")
                return "정지", ZERO, why
            if pattern != self.line_log_pat and st in (obs.PAUSE, obs.CLEAR):   # 멈춘 동안 센서 변화도 기록
                self.line_log_pat = pattern
                log(f"   센서 {pattern} (잠깐 멈춤 중 · 초음파 {umm}mm)")
            if pattern is None:                      # 잠깐 멈춤 중이어도 라인센서 실패면 라인 끔 (#12)
                why = "센서 읽기 실패" if took <= SENSOR_LIMIT else f"센서 읽기 {took * 1000:.0f}ms 걸림 (기준 {SENSOR_LIMIT * 1000:.0f}ms)"
                self.line_view = dict(pattern=pattern, action="정지", reason=why)
                log(f"LINE 끝: {why}")
                return "정지", ZERO, why
            # ---- 사람 · STOP 표지판 (지시서 06 · 조원 결정 2026-11-05) — 장애물보다 먼저 · 불빛 · 부저는 안 씀 ----
            hold, swhy, sleft = self.sight.update(vision.status(), now)
            if hold:
                if not self.sight_held:
                    self.sight_held = True
                    self.follower.pause(now)         # 라인 판단 시간 멈춤 (이미 장애물로 멈춘 중이면 그대로)
                    log(f"SIGHT 멈춤: {swhy} · 센서 {pattern} · 초음파 {umm}mm")
                self.center_seen = 0
                name = swhy + (f" (남은 {sleft:.1f}초)" if sleft is not None else "")
                self.line_view = dict(pattern=pattern, action=name, reason=None)
                return "라인: " + name, ZERO, None
            if self.sight_held:
                self.sight_held = False
                if st == obs.RUN:                    # 장애물도 없으면 이어서 · 남아 있으면 아래 장애물 규칙이 이어받음
                    self.follower.resume(now)
                    log(f"SIGHT 다시 출발 · 센서 {pattern}")
                else:
                    log("SIGHT 풀림 · 장애물 멈춤은 계속")
            if st == obs.PAUSE:
                if not was_paused:
                    self.follower.pause(now)
                    log(f"OBST 잠깐 멈춤: 초음파 {umm}mm (기준 {obs.STOP_MM}mm 이하) · 센서 {pattern}")
                self.center_seen = 0
                self.obs_paused = True
                name = owhy + (f" · 치우면 출발 (남은 {left:.1f}초)" if left is not None else " · 치우면 1초 뒤 출발")
                self.line_view = dict(pattern=pattern, action=name, reason=None)
                return "라인: " + name, ZERO, None
            if st == obs.CLEAR:
                # 지시서 05 B (2026-11-04): 가운데 → 연속 2번 확인 · 0000 → 04 찾기 · 1111 → 끔 · 그 밖 → 04 따라가기
                if pattern == "1111":
                    self.judge.reset()
                    why = "장애물 치움 · 네 칸 모두 검음(들림 · 가림) → 출발 안 함"
                    self.line_view = dict(pattern=pattern, action="정지", reason=why)
                    log(f"LINE 끝: {why}")
                    return "정지", ZERO, why
                if pattern in LINE_CENTER:
                    self.center_seen += 1
                    if self.center_seen < RESTART_CONFIRM:
                        self.obs_paused = True
                        return "라인: 장애물 치움 · 줄 확인 중", ZERO, None
                self.judge.resumed()
                self.follower.resume(now)
                self.center_seen = 0
                if pattern == "0000":
                    self.follower.crab_search(now)
                    log("OBST 다시 출발: 치워짐 1초 · 줄 안 보임 → 옆걸음 찾기 (왼쪽 1cm → 오른쪽 2cm)")
                else:
                    log(f"OBST 다시 출발: 치워짐 1초 · 센서 {pattern}")
        wheels, action, why = self.follower.step(pattern, now)
        if pattern != self.line_log_pat:             # 센서 값이 바뀔 때마다 기록 (회전 중 줄이 지나갔는지도 보이게)
            self.line_log_pat = pattern
            log(f"   센서 {pattern} → {action}")
        if why == "센서 읽기 실패" and took > SENSOR_LIMIT:
            why = f"센서 읽기 {took * 1000:.0f}ms 걸림 (기준 {SENSOR_LIMIT * 1000:.0f}ms)"
        self.line_view = dict(pattern=pattern, action=action, reason=why)
        if why:
            log(f"LINE 끝: {why}")
        return "라인: " + action, wheels, why

    def _gestures(self, now):
        """지시서 08: 손 모양 명령 — 조종 화면이 열려 있을 때만. 바퀴는 정지 · 라인 켜기 길로만 움직인다."""
        if not vision.enabled or seats.current_gen(SLOTS[0]) is None:
            self.gesture.reset()
            return
        cmd = self.gesture.update(vision.status(), now)
        if cmd is None:
            return
        eid = (self.gesture_event or {}).get("id", 0) + 1
        note = ""
        if cmd == "stop":                          # 주먹 = 정지 버튼과 같게 (서버가 바로)
            stop_everyone("손 모양: 주먹(멈춤)")
        elif cmd == "start":                       # 보 = 라인 켜기 (화면이 버튼을 누른 것처럼 켬) + 3초 사람 멈춤 쉼
            w = wishes[SLOTS[0]].snapshot()
            if w["kind"] == "line" and w["press"] > w["floor"]:
                note = " (이미 라인 중 · 무시)"
            else:
                self.sight.skip_person(now + GESTURE_PERSON_SKIP)
        elif cmd == "faster":                      # 엄지척 = 라인 속도 +10 · 최대 90
            self.line_speed = min(LINE_SPEED_MAX, self.line_speed + LINE_SPEED_STEP)
            if self.follower is not None:
                self.follower.speed = self.line_speed
            note = f" → 라인 속도 {self.line_speed}"
        elif cmd == "photo":                       # 브이 = 사진 1장 (저장은 다른 스레드 · 제어를 안 막음)
            img, _ = camera.latest_raw()
            if img is not None:
                threading.Thread(target=save_photo, args=(img,), daemon=True).start()
        self.gesture_event = dict(id=eid, cmd=cmd, t=now, note=note)
        log(f"GESTURE {cmd}{note}")

    def tick(self):
        now = time.monotonic()
        try:
            self._gestures(now)
        except Exception as e:                   # 손 모양 오류가 제어를 막지 않게
            log(f"!! 손 모양 처리 오류: {e}")
        want_name, want, why = "정지", ZERO, None
        self.obs_paused = False                      # _line 이 잠깐 멈춤이면 True 로 → 아래 알림(빨간 불)
        line_now = False
        if guard_tripped.is_set():
            # 감시 스레드가 바퀴를 0 으로 만들었다: 제어부 기억(self.out)도 「모름」으로 → 아래에서 0 을 다시 씀
            guard_tripped.clear()
            for w in wishes.values():
                w.raise_floor()
            self.out, self.out_name, self.driver = None, "정지", None
            why = "감시 정지 · 다시 눌러야 움직임"
        elif self.shutting:
            why = "프로그램 끝"
        elif estop_flag.is_set():
            estop_flag.clear()
            why = self.estop_reason
            self.driver = None
        else:
            states = {k: self._live(k, now) for k in SLOTS}
            # 먼저 누른 기기 우선: 지금 운전 중인 자리가 계속 원하면 그대로
            if self.driver and states[self.driver][0] == "ok":
                pick = self.driver
            else:
                if self.driver and states[self.driver][0] not in (None, "ok"):
                    why = states[self.driver][0]
                self.driver = None
                pick = None
                cands = [k for k in SLOTS if states[k][0] == "ok"]
                if cands:  # 둘 다 원하면 누름이 먼저 도착한 기기가 이김
                    pick = min(cands, key=lambda k: wishes[k].press_start)
            for k in SLOTS:
                st = states[k]
                if st[0] not in (None, "ok") and why is None:
                    why = st[0]
            if pick:
                # 다른 자리가 같은 때 누르고 있었다면 그 누름은 무효 (다시 눌러야 함)
                for k in SLOTS:
                    if k != pick and states[k][0] == "ok":
                        wishes[k].raise_floor(states[k][1]["press"])
                        log(f"   {SLOT_NAME[k]} 입력 무시 ({SLOT_NAME[pick]}가 먼저 누름)")
                self.driver = pick
                s = states[pick][1]
                self.cur_press = s["press"]
                if s["kind"] == "line":
                    line_now = True
                    want_name, want, line_why = self._line(pick, s, now)
                    if line_why:                     # 라인 판단이 멈춤 → 이 누름은 끝 (다시 눌러야 출발)
                        wishes[pick].raise_floor(s["press"])
                        self.driver = None
                        self.obs_paused = False
                        self.judge.reset()           # 라인이 꺼지면 장애물 타이머도 지움 (#15)
                        self.sight.reset()           # 사람 · STOP 타이머도 지움 (06)
                        self.sight_held = False
                        want_name, want, why = "정지", ZERO, "라인: " + line_why
                    elif want == ZERO:               # 장애물 잠깐 멈춤 (라인 모드는 유지)
                        why = want_name
                else:
                    sp = max(SPEED_MIN, min(SPEED_MAX, int(s["speed"])))
                    want_name, want = mix(s["keys"], sp)
                    if want == ZERO:
                        why = want_name
            elif why is None:
                why = "손 뗌 · 정지"
        if want != ZERO and (guard_tripped.is_set() or time.monotonic() - now > STALL_LIMIT):
            # 판단하는 동안 멈춰 있었다 → 판단에 쓴 정보가 낡았으므로 움직이지 않고, 지금 누름은 무효
            for w in wishes.values():
                w.raise_floor()
            self.driver = None
            want_name, want, why = "정지", ZERO, f"제어 지연 {time.monotonic() - now:.2f}초 · 다시 눌러야 움직임"
        if want != ZERO and (estop_flag.is_set() or self.driver is None
                             or wishes[self.driver].need_new_press(self.cur_press)):
            # 쓰기 바로 직전 다시 확인: 판단(센서 읽기) 도중 정지 · 비상정지 · 새 누름이 왔으면 움직이지 않음 (지시서 05 #3)
            self.driver = None
            want_name, want, why = "정지", ZERO, "판단 중 정지 요청 · 다시 눌러야 움직임"
        if not line_now:
            self.obs_view = dict(mm=None, state="꺼짐", left=None)
        if why and want == ZERO:
            self.reason = why

        need_write = want != self.out or (want == ZERO and now - self.last_zero >= ZERO_RESEND)
        if need_write:
            failed = motors.write(want)
            if failed:
                self.locked = True
                if want == ZERO:
                    self.reason = "정지 실패 → 다시 시도 중"
                else:
                    for w in wishes.values():
                        w.raise_floor()
                    self.reason = "바퀴 쓰기 실패"
                    self.driver = None
                    if motors.write(ZERO) == []:
                        self.out, self.out_name, self.last_zero = ZERO, "정지", time.monotonic()
                return
            done = time.monotonic()
            if want == ZERO:
                self.last_zero = done
                if self.locked:
                    log("   정지 다시 시도 성공 → 잠금 풂 (다시 눌러야 움직임)")
                    self.locked = False
            if want != self.out:
                if want == ZERO:
                    log(f"STOP  ({self.reason}) · 정지 명령 완료 {done - now:.3f}초")
                else:
                    log(f"DRIVE {want_name} {want}  ← {SLOT_NAME[self.driver]}" + ("   [dry]" if args.dry else ""))
            self.out, self.out_name = want, want_name
        self._alerts()                               # 바퀴를 먼저 쓴 뒤에 불빛 · 부저 (지시서 05 #16)

    def _alerts(self):
        """장애물 잠깐 멈춤 = 빨간 불(계속) + 부저 0.1초(멈추는 순간). 실패해도 바퀴에는 영향 없음 (기록만).
        한 번이라도 0.05초를 넘게 걸리면 그 뒤로는 불빛 · 부저를 쓰지 않는다(화면 표시만)."""
        if not self.alerts_ok:
            return
        now = time.monotonic()
        t0 = now
        want_light = self.obs_paused
        if want_light and not self.light_on:
            motors.write_reg(0x03, [1, 0])          # 빨강 켜기
            motors.write_reg(0x06, [1])             # 삐
            self.light_on, self.beep_until = True, now + BEEP_S
        elif not want_light and self.light_on:
            motors.write_reg(0x03, [0, 0])          # 끄기
            self.light_on = False
            if self.beep_until is not None:
                motors.write_reg(0x06, [0])
                self.beep_until = None
        if self.beep_until is not None and now >= self.beep_until:
            motors.write_reg(0x06, [0])
            self.beep_until = None
        took = time.monotonic() - t0
        if took > ALERT_LIMIT:
            self.alerts_ok = False
            log(f"!! 불빛 · 부저 쓰기 {took:.3f}초 걸림 (기준 {ALERT_LIMIT}초) → 그 뒤로 알림은 화면만")

    def run(self):
        while True:
            try:
                self.tick()
            except Exception as e:               # 제어 스레드는 죽지 않는다
                log(f"!! 제어 오류: {e} → 정지 시도 · 잠금")
                self.locked = True
                self.driver = None
                try:
                    motors.write(ZERO)
                    self.out = ZERO
                except Exception:
                    pass
            b = time.monotonic()
            if b - self.beat > 0.1:
                log(f"!! 제어 한 바퀴 {b - self.beat:.3f}초 걸림 (기준 0.1초)")
            self.max_gap = max(self.max_gap, b - self.beat)   # 제어 한 바퀴 최대 간격 (03 성공 기준: 0.1초 이내)
            self.beat = b
            if self.shutting and self.out == ZERO:
                self.done.set()
                return
            time.sleep(TICK)


ctl = Controller()
ctl_thread = threading.Thread(target=ctl.run, daemon=True, name="controller")


def guardian():
    """제어 스레드가 멈추거나 죽으면 직접 0 을 보낸다."""
    warned = False
    while True:
        time.sleep(0.05)
        try:
            stale = time.monotonic() - ctl.beat
            if (not ctl_thread.is_alive()) or stale > GUARD_LIMIT:
                if not warned:
                    log(f"!! 감시: 제어 스레드 {stale:.2f}초 응답 없음 → 직접 정지 · 주행 거부")
                    warned = True
                    ctl.guard_count += 1
                guard_tripped.set()
                for w in wishes.values():   # 지금까지의 누름은 모두 무효 → 회복 뒤에도 새로 눌러야 움직임
                    w.raise_floor()
                motors.write(ZERO)
                time.sleep(0.2)
            elif warned:
                log("   감시: 제어 스레드 회복")
                warned = False
        except Exception as e:
            log(f"!! 감시 오류: {e}")


def controller_ok():
    return ctl_thread.is_alive() and time.monotonic() - ctl.beat <= GUARD_LIMIT and not ctl.shutting


def on_signal(signum, _frame):
    # 신호 처리기에서는 잠금을 잡지 않는다: 표시만 하고, 끝내는 일은 다른 스레드가 한다
    ctl.shutting = True

    def finish():
        ctl.done.wait(1.0)
        try:
            motors.write(ZERO)                   # ① 네 바퀴 0 먼저
        finally:
            log("끝 · 네 바퀴 0")
            for reg, data in ((0x06, [0]), (0x03, [0, 0]), (0x07, [0])):   # 부저 · 불빛 끄기 · 초음파 끄기 (바퀴 다음)
                try:
                    motors.write_reg(reg, data)
                except Exception:
                    pass
            try:
                if recorder is not None:         # ② 녹화 마무리는 최대 1초만
                    done = recorder.close(1.0)
                    log("블박 파일 마무리 " + ("완료" if done else "못 끝냄(마지막 파일은 열리면 다행)"))
            except Exception:
                pass
            camera.close()
            os._exit(0)

    threading.Thread(target=finish, daemon=True).start()


# ---------------- 웹 ----------------
app = Flask(__name__, static_folder=None)
COOKIE = "seat"


def same_origin():
    origin = request.headers.get("Origin")
    return origin is None or urlparse(origin).netloc == request.host


def body():
    return request.get_json(silent=True, force=True) or {}


def line_status(slot):
    w = wishes[slot or SLOTS[0]].snapshot()
    active = w["kind"] == "line" and w["press"] > w["floor"]
    v = ctl.line_view
    return dict(active=active, pattern=v["pattern"], action=v["action"] if active else "꺼짐",
                reason=v["reason"] if v["reason"] else (None if active else ctl.reason), speed=ctl.line_speed,
                available=camera.enabled, obstacle=dict(ctl.obs_view))   # 지시서 05: 거리 mm · 상태 · 남은 초


def status_json(slot):
    a = camera.age()
    return dict(
        moving=ctl.out not in (ZERO, None) and controller_ok(), move=ctl.out_name, reason=ctl.reason, locked=ctl.locked,
        controller=controller_ok(), dry=args.dry, camera=camera.enabled,
        frame_age=None if a == float("inf") else round(a, 2),
        seat=slot is not None, my_slot=slot, my_slot_name=SLOT_NAME.get(slot),
        driver=ctl.driver, driver_name=SLOT_NAME.get(ctl.driver),
        blackbox=None if recorder is None else recorder.status(),   # 메모리 값만 (폴더 안 훑음)
        ctl_max_gap=round(ctl.max_gap, 3), guard_count=ctl.guard_count,
        line=line_status(slot),
    )


@app.get("/api/vision")
def vision_api():
    # 인식 결과 (지시서 06 · 08 · 화면 표시만) — 조종 자리 주인만 (사람 위치 정보)
    slot, gen = seats.touch(request.cookies.get(COOKIE))
    if slot is None:
        return jsonify(ok=False), 403
    e = ctl.gesture_event
    g = None if e is None else dict(id=e["id"], cmd=e["cmd"], note=e["note"], age=round(time.monotonic() - e["t"], 2))
    return jsonify(ok=True, gesture=g, line_speed=ctl.line_speed, **vision.status())


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/api/config")
def config():
    return jsonify(speed_default=SPEED_DEFAULT, speed_min=SPEED_MIN, speed_max=SPEED_MAX,
                   dry=args.dry, camera=camera.enabled, cam_stale=CAM_STALE, fault=args.fault,
                   line_speed=LINE_SPEED, line_beat=0.25, vision=vision.enabled)


@app.post("/api/claim")
def claim():
    if not same_origin():
        return jsonify(ok=False, reason="다른 곳에서 온 요청"), 403
    want = Seats.kind_of(request.headers.get("User-Agent"))
    slot, gen, new = seats.claim(request.cookies.get(COOKIE), request.remote_addr, want)
    if slot is None:
        return jsonify(ok=False, reason="다른 사람이 조종 중입니다", slot=want), 409
    resp = make_response(jsonify(ok=True, slot=slot, slot_name=SLOT_NAME[slot], gen=gen, resumed=not new))
    resp.set_cookie(COOKIE, seats.token_of(slot), httponly=True, samesite="Strict")
    return resp


@app.post("/api/move")
def move():
    if not same_origin():
        return jsonify(ok=False, reason="다른 곳에서 온 요청"), 403
    slot, gen = seats.touch(request.cookies.get(COOKIE))
    if slot is None:
        return jsonify(ok=False, reason="조종 자리가 없습니다"), 403
    if not controller_ok():
        return jsonify(ok=False, reason="제어부 이상 — 주행 거부"), 503
    d = body()
    try:
        seq, press = int(d["seq"]), int(d["press"])
        keys = [k for k in d.get("keys", []) if k in SINGLE]
        speed = int(d.get("speed", SPEED_DEFAULT))
    except (KeyError, TypeError, ValueError):
        return jsonify(ok=False, reason="형식 오류"), 400
    accepted = wishes[slot].put(gen, seq, "move", press, keys, speed)
    st = status_json(slot)
    blocked = ctl.driver is not None and ctl.driver != slot
    st.update(ok=True, accepted=accepted, need_new_press=wishes[slot].need_new_press(press),
              blocked_by=SLOT_NAME[ctl.driver] if blocked else None)
    return jsonify(st)


@app.post("/api/line")
def line_api():
    # 라인 따라가기 켜기 · 「라인 계속」(0.25초마다) · 끄기 — 지시서 04
    if not same_origin():
        return jsonify(ok=False, reason="다른 곳에서 온 요청"), 403
    slot, gen = seats.touch(request.cookies.get(COOKIE))
    if slot is None:
        return jsonify(ok=False, reason="조종 자리가 없습니다 — 비상정지를 쓰세요"), 403
    d = body()
    try:
        seq, press, on = int(d["seq"]), int(d["press"]), bool(d.get("on"))
    except (KeyError, TypeError, ValueError):
        return jsonify(ok=False, reason="형식 오류"), 400
    if not on:
        wishes[slot].put(gen, seq, "stop", press)
        return jsonify(ok=True, accepted=True, need_new_press=False, **status_json(slot))
    if not camera.enabled:
        return jsonify(ok=False, reason="카메라 없이(--no-camera) 라인 모드 못 씀"), 400
    if not controller_ok():
        return jsonify(ok=False, reason="제어부 이상 — 주행 거부"), 503
    accepted = wishes[slot].put(gen, seq, "line", press)
    st = status_json(slot)
    st.update(ok=True, accepted=accepted, need_new_press=wishes[slot].need_new_press(press))
    return jsonify(st)


@app.post("/api/stop")
def stop():
    if not same_origin():
        return jsonify(ok=False, reason="다른 곳에서 온 요청"), 403
    slot, gen = seats.touch(request.cookies.get(COOKIE))
    if slot is None:
        return jsonify(ok=False, reason="조종 자리가 없습니다 — 비상정지를 쓰세요"), 403
    d = body()
    try:
        seq, press = int(d["seq"]), int(d["press"])
    except (KeyError, TypeError, ValueError):
        return jsonify(ok=False, reason="형식 오류"), 400
    wishes[slot].put(gen, seq, "stop", press)
    if d.get("all"):            # 정지 버튼 · 스페이스: 누가 움직이고 있든 정지
        stop_everyone(f"{SLOT_NAME[slot]} 정지 버튼")
        log(f"정지 버튼: {SLOT_NAME[slot]}")
    return jsonify(ok=True, **status_json(slot))


@app.post("/api/estop")
def estop():
    # 비상정지: 조종 자리가 없어도 누구나
    if not same_origin():
        return jsonify(ok=False, reason="다른 곳에서 온 요청"), 403
    stop_everyone("비상정지")
    log(f"비상정지 요청: {request.remote_addr}")
    return jsonify(ok=True)


@app.post("/api/leave")
def leave():
    # 창 닫기 · 새로고침 (sendBeacon) → 그 자리 반납 + 정지
    if not same_origin():
        return jsonify(ok=False), 403
    slot = seats.release(request.cookies.get(COOKIE))
    if slot and ctl.driver == slot:
        stop_everyone(f"{SLOT_NAME[slot]} 창 닫음")
    return jsonify(ok=True)


@app.get("/api/status")
def status():
    slot, gen = seats.touch(request.cookies.get(COOKIE))
    if slot is None:
        return jsonify(ok=False, **status_json(None)), 403
    return jsonify(ok=True, **status_json(slot))


@app.get("/video")
def video():
    slot, gen = seats.touch(request.cookies.get(COOKIE))
    if slot is None:
        return Response("조종 자리가 없습니다", status=403)
    if not camera.enabled:
        return Response("camera off", status=404)
    my_stream = seats.new_stream(slot)     # 새 스트림이 열리면 이전 스트림은 끝남 (자리당 1개)

    def gen_frames():
        last_t = None
        while seats.stream_of(slot) == my_stream and seats.current_gen(slot) == gen:
            frame, t = camera.latest()
            if frame is not None and t != last_t:
                last_t = t
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            time.sleep(1.0 / CAM_FPS)

    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-store"})


@app.post("/api/_fault")
def fault():
    # 깨뜨리는 시험용 — --dry --fault 일 때만
    if not args.fault:
        return jsonify(ok=False), 404
    d = body()
    motors.fail_next = int(d.get("fail_writes", 0))
    motors.hang_next = float(d.get("hang", 0))
    if "camera_pause" in d:
        camera.paused = bool(d["camera_pause"])
    if "line_pattern" in d:                                   # dry 가짜 라인센서 ('0110' 같은 4글자 · None = 값 없음)
        motors.dry_line = None if d["line_pattern"] is None else line_encode(d["line_pattern"])
    if "ultra" in d:                                          # dry 가짜 초음파: mm 숫자 · "fail" · "torn"
        motors.dry_ultra = d["ultra"]
    if "vision" in d:                                         # 가짜 인식: [["person", 0.8], …] · "stale" · None(진짜로 돌아감)
        vision.fake = d["vision"]
    motors.sensor_fail_next = int(d.get("sensor_fail", motors.sensor_fail_next))
    motors.sensor_delay_next = float(d.get("sensor_delay", motors.sensor_delay_next))
    if "bb_write_delay" in d and recorder is not None:
        recorder.write_delay = float(d["bb_write_delay"])     # 블박 쓰기마다 n 초 멈춤 (SD 느림 흉내)
    if d.get("stall_camera_age"):
        # 제어부가 판단 도중(영상 나이 확인)에서 n 초 멈춤 — 블박 등이 카메라 잠금을 오래 잡은 상황 흉내
        orig_age, secs = camera.age, float(d["stall_camera_age"])

        def slow_age():
            if threading.current_thread().name == "controller":   # 제어 스레드에서만 멈춤 (웹 요청은 그대로)
                camera.age = orig_age
                time.sleep(secs)
            return orig_age()
        camera.age = slow_age
    if d.get("crash_controller_tick"):
        orig = ctl.tick

        def boom():
            ctl.tick = orig
            raise RuntimeError("주입된 제어 오류")
        ctl.tick = boom
    log(f"[고장 주입] {d}")
    return jsonify(ok=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    motors.write(ZERO)
    motors.write_reg(0x03, [0, 0])       # 불빛 끄기
    motors.write_reg(0x06, [0])          # 부저 끄기
    if motors.write_reg(0x07, [1]):      # 초음파 켜기 (지시서 05: 프로그램이 켜질 때 켜고 끝날 때 끔 · 1초 준비)
        ctl.judge.on_time = time.monotonic()
        log("초음파 켬 (1초 뒤 준비 끝)")
    else:
        log("!! 초음파 켜기 실패 → 라인 따라가기는 「초음파 준비 중」으로 출발 안 함")
        ctl.judge.on_time = float("inf")
    ctl.beat = time.monotonic()          # 시작 직전에 맞춰야 감시 스레드가 잘못 경보하지 않음
    ctl_thread.start()
    threading.Thread(target=guardian, daemon=True, name="guardian").start()
    log(f"웹 조종 시작 → http://raspibot-01.local:{PORT}"
        + ("   [dry: 바퀴 안 움직임]" if args.dry else "") + ("   [고장 주입 켬]" if args.fault else ""))
    # "::" = IPv4 와 IPv6 둘 다 받음 (핫스팟에서 IPv6 로만 통신하는 휴대폰도 접속 가능)
    app.run(host="::", port=PORT, threaded=True)
