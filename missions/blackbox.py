#!/usr/bin/env python3
# 지시서: specs/03-blackbox.md  (Codex 적대적 리뷰 반영판 · 2026-11-03)
# 블랙박스 녹화기 — 카메라를 직접 열지 않는다. 「장면 + 받은 시각」을 넣어 주면 녹화만 한다.
# (웹 조종 missions/webabb.py 에서 쓰고, 07 자율주행에서도 그대로 쓴다)
#
# 안전 약속: 조종 쪽(카메라 스레드 · 제어 스레드)을 절대 기다리게 하지 않는다.
#  - submit() 은 대기 줄(최대 5장)에 넣어 보기만 한다. 꽉 차 있으면 그 장면을 버리고 바로 돌아간다.
#  - 시각 그리기 · 압축 · 파일 쓰기 · 지우기는 모두 블박 스레드에서만 한다.
#  - status() 는 메모리에 적어 둔 값만 돌려준다 (폴더를 훑지 않는다).
import os
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time

MiB = 1024 ** 2
GiB = 1024 ** 3
NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_[0-9a-f]{5}_\d{3,})\.(avi|csv)$")
ORDER_FILE = "order.log"      # 파일을 만든 순서 (시계가 뒤로 바뀌어도 「오래된 순서」가 안 꼬이게)
LOCK_FILE = ".lock"           # 같은 폴더를 두 프로그램이 동시에 관리하지 않게

LABELS = {
    "starting": "― 녹화 준비 중",
    "recording": "● 녹화 중",
    "no_video": "● 녹화 중 (영상 없음)",
    "stalled": "■ 녹화 멈춤",
    "failed": "■ 녹화 멈춤 (다시 시도 대기)",
    "no_space": "■ 저장 공간 부족",
    "off": "― 녹화 안 함",
}


class Recorder:
    def __init__(self, folder, fps=10, segment_s=180, folder_limit=2 * GiB, file_limit=200 * MiB,
                 min_free=1 * GiB, queue_max=5, no_video_after=0.3, stall_s=3.0, retry_s=10.0,
                 max_failures=3, check_s=10.0, size=(640, 480), log=print):
        self.folder = folder
        self.fps = fps
        self.segment_s = segment_s
        self.folder_limit = folder_limit
        self.file_limit = file_limit
        self.min_free = min_free
        self.no_video_after = no_video_after
        self.stall_s = stall_s
        self.retry_s = retry_s
        self.max_failures = max_failures
        self.check_s = check_s
        self.size = size
        self.log = log

        self.write_delay = 0.0          # 고장 주입: 쓰기마다 n 초 멈춤
        self.q = queue.Queue(maxsize=queue_max)
        self.run_id = secrets.token_hex(3)[:5]
        self.seg = 1
        self._lock = threading.Lock()   # 상태 기록용 — 이 잠금을 잡은 채 파일 일을 하지 않는다
        self._st = dict(state="starting", file=None, folder_mb=0.0, dropped=0, written=0,
                        skipped=0, clock_ok=None, note="")
        self.last_write = time.monotonic()
        self._stop = threading.Event()
        self._lockf = None

        self.vw = self.csv = None
        self.cur_base = None
        self.cur_started = 0.0
        self.cur_size = 0
        self.thread = threading.Thread(target=self._run, daemon=True, name="blackbox")
        self.thread.start()

    # ---------------- 조종 쪽에서 부르는 것 (절대 기다리지 않음) ----------------
    def submit(self, img, t_mono, t_wall):
        try:
            self.q.put_nowait((img, t_mono, t_wall))
        except queue.Full:
            with self._lock:
                self._st["dropped"] += 1

    def status(self):
        with self._lock:
            st = dict(self._st)
            lw = self.last_write
        if st["state"] in ("recording", "no_video") and time.monotonic() - lw > self.stall_s:
            st["state"] = "stalled"
        st["label"] = LABELS[st["state"]]
        return st

    def close(self, timeout=1.0):
        """녹화 마무리를 최대 timeout 초만 기다린다. 못 끝내면 그대로 둔다(바퀴 정지는 이미 끝난 뒤에 부를 것)."""
        self._stop.set()
        self.thread.join(timeout)
        return not self.thread.is_alive()

    # ---------------- 블박 스레드 ----------------
    def _set(self, **kw):
        with self._lock:
            self._st.update(kw)

    def _state(self):
        with self._lock:
            return self._st["state"]

    def _run(self):
        try:
            import cv2
            import numpy as np
            self.cv2, self.np = cv2, np
            os.makedirs(self.folder, exist_ok=True)
            if not self._take_lock():
                self.log("블박: 다른 프로그램이 이 폴더에 녹화 중 → 녹화 안 함")
                self._set(state="off", note="다른 프로그램이 녹화 중")
                return
            self._check_clock()
            self._housekeep()
            self._loop()
        except Exception as e:
            self.log(f"!! 블박 오류: {e} → 녹화 안 함")
            self._set(state="off", note=str(e))
        finally:
            self._close_file()

    def _take_lock(self):
        try:
            import fcntl
        except ImportError:          # 윈도우(개발용 PC)에서는 잠금 없이
            return True
        self._lockf = open(os.path.join(self.folder, LOCK_FILE), "a")
        try:
            fcntl.flock(self._lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _check_clock(self):
        ok = None
        try:
            out = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
                                 capture_output=True, text=True, timeout=2).stdout.strip()
            ok = out == "yes"
        except Exception:
            pass
        self._set(clock_ok=ok)
        if not ok:
            self.log("블박: 라즈봇 시각이 맞춰졌는지 확인 못 함 → 영상 속 시각은 「시각 미확인」")

    def _loop(self):
        period = 1.0 / self.fps
        next_t = time.monotonic()
        latest = None                # (img, t_mono, t_wall) — 가장 최근에 받은 장면
        last_written_t = None
        last_check = time.monotonic()
        failures = 0
        retry_at = 0.0
        size_check_at = time.monotonic() + self.stall_s
        size_at_check, writes_since_check = 0, 0
        check_base = None
        self._set(state="recording")

        while not self._stop.is_set():
            now = time.monotonic()
            if now < next_t:
                time.sleep(next_t - now)
                continue
            if now - next_t > 1.0:   # 1초 넘게 밀림(쓰기가 멈췄었음) → 그 칸들은 건너뜀
                missed = int((now - next_t) / period)
                with self._lock:
                    self._st["skipped"] += missed
                next_t = now
            next_t += period

            try:                     # 대기 줄에서 가장 새 장면만
                while True:
                    latest = self.q.get_nowait()
            except queue.Empty:
                pass

            if now - last_check >= self.check_s:
                last_check = now
                self._housekeep()

            state = self._state()
            if state in ("no_space", "off"):
                continue
            if state == "failed":
                if now < retry_at:
                    continue
                self._set(state="recording")

            # 0.1초 칸에 넣을 장면: 새 장면 → 그 장면 / 0.3초 안의 장면 → 그 장면(받은 시각 그대로) / 그 밖 → 「영상 없음」
            if latest is not None and now - latest[1] <= self.no_video_after:
                img, t_mono, t_wall = latest
                kind = "new" if t_mono != last_written_t else "dup"
            else:
                img, t_mono, t_wall, kind = None, None, time.time(), "none"

            try:
                if not self._write(img, t_mono, t_wall, kind):
                    continue         # 파일을 바꾸다 빈 공간 부족을 알게 됨
                writes_since_check += 1
                if t_mono is not None:
                    last_written_t = t_mono
                with self._lock:
                    self.last_write = time.monotonic()
                    self._st["written"] += 1
                    self._st["state"] = "no_video" if kind == "none" else "recording"
                # 파일이 실제로 커지는지 (VideoWriter.write 는 실패를 알려 주지 않음)
                if self.cur_base != check_base:      # 새 파일로 바뀌었으면 그 파일 기준으로 다시 잼
                    check_base, size_at_check, writes_since_check = self.cur_base, self.cur_size, 0
                    size_check_at = time.monotonic() + self.stall_s
                elif time.monotonic() >= size_check_at:
                    grown = self.cur_size > size_at_check
                    if not grown and writes_since_check >= 10:
                        raise OSError("파일 크기가 3초 동안 안 늘어남")
                    size_at_check, writes_since_check = self.cur_size, 0
                    size_check_at = time.monotonic() + self.stall_s
                    if grown:
                        failures = 0
            except Exception as e:
                self._close_file()
                failures += 1
                if failures >= self.max_failures:
                    self.log(f"!! 블박 쓰기 실패 {failures}번 연속 ({e}) → 프로그램을 다시 켤 때까지 녹화 안 함")
                    self._set(state="off", note=f"{failures}번 연속 실패: {e}")
                else:
                    self.log(f"!! 블박 쓰기 실패 ({e}) → {self.retry_s:.0f}초 뒤 새 파일로 다시 시도")
                    self._set(state="failed", note=str(e))
                    retry_at = time.monotonic() + self.retry_s
                size_at_check, writes_since_check = 0, 0
                size_check_at = time.monotonic() + self.stall_s

    def _write(self, img, t_mono, t_wall, kind):
        now = time.monotonic()
        if self.vw is not None and (now - self.cur_started >= self.segment_s or self.cur_size > self.file_limit):
            self._close_file()
            self._housekeep()
            if self._state() == "no_space":
                return False
        if self.vw is None:
            self._open()
        frame = self._stamp(img, t_wall, kind)
        if self.write_delay:
            time.sleep(self.write_delay)
        self.vw.write(frame)
        self.csv.write(f"{kind},{'' if t_mono is None else f'{t_mono:.3f}'},{t_wall:.3f},{time.time():.3f}\n")
        try:
            self.cur_size = os.path.getsize(self._path(self.cur_base, "avi"))
        except OSError:
            pass
        return True

    def _path(self, base, ext):
        return os.path.join(self.folder, f"{base}.{ext}")

    def _open(self):
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        while True:                  # 같은 이름이 있으면 절대 덮어쓰지 않는다
            base = f"{stamp}_{self.run_id}_{self.seg:03d}"
            self.seg += 1
            if not os.path.exists(self._path(base, "avi")) and not os.path.exists(self._path(base, "csv")):
                break
        csv = open(self._path(base, "csv"), "x", encoding="utf-8", buffering=1)
        csv.write("kind,capture_mono,capture_wall,write_wall\n")
        vw = self.cv2.VideoWriter(self._path(base, "avi"), self.cv2.VideoWriter_fourcc(*"MJPG"), self.fps, self.size)
        if not vw.isOpened():
            csv.close()
            raise OSError("MJPG 영상 파일을 열 수 없음")
        with open(os.path.join(self.folder, ORDER_FILE), "a", encoding="utf-8") as f:
            f.write(base + "\n")
        self.vw, self.csv, self.cur_base = vw, csv, base
        self.cur_started, self.cur_size = time.monotonic(), 0
        self._set(file=base + ".avi")
        self.log(f"블박: 새 파일 {base}.avi")

    def _close_file(self):
        if self.vw is not None:
            try:
                self.vw.release()
            except Exception:
                pass
        if self.csv is not None:
            try:
                self.csv.close()
            except Exception:
                pass
        self.vw = self.csv = None
        self.cur_base = None

    def _stamp(self, img, t_wall, kind):
        cv2, np = self.cv2, self.np
        w, h = self.size
        if img is None:
            frame = np.zeros((h, w, 3), np.uint8)
            cv2.putText(frame, "NO VIDEO", (w // 2 - 110, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
        elif (img.shape[1], img.shape[0]) != (w, h):
            frame = cv2.resize(img, (w, h))
        else:
            frame = img.copy()       # 카메라가 준 장면은 건드리지 않는다
        text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t_wall)) + f".{int(t_wall * 10) % 10}"
        if self._st.get("clock_ok") is False or self._st.get("clock_ok") is None:
            text += " (clock?)"
        org = (10, h - 12)
        cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        return frame

    # ---------------- 용량 관리 (블박 스레드에서만) ----------------
    def _housekeep(self):
        try:
            groups = {}              # 이름 → [크기 합, 파일들, 고친 시각]
            for name in os.listdir(self.folder):
                m = NAME_RE.match(name)
                if not m:
                    continue         # 블박 파일이 아닌 것은 절대 건드리지 않는다
                p = os.path.join(self.folder, name)
                try:
                    stt = os.stat(p)
                except OSError:
                    continue
                g = groups.setdefault(m.group(1), [0, [], stt.st_mtime])
                g[0] += stt.st_size
                g[1].append(p)
            total = sum(g[0] for g in groups.values())

            if total > self.folder_limit:
                order = []
                try:
                    with open(os.path.join(self.folder, ORDER_FILE), encoding="utf-8") as f:
                        order = [line.strip() for line in f if line.strip()]
                except OSError:
                    pass
                rank = {b: i for i, b in enumerate(order)}
                # 순서 기록에 없는 파일이 가장 오래된 것으로 (그 안에서는 고친 시각 순)
                olds = sorted((b for b in groups if b != self.cur_base),
                              key=lambda b: (b in rank, rank.get(b, 0), groups[b][2]))
                for b in olds:
                    if total <= self.folder_limit:
                        break
                    for p in groups[b][1]:
                        try:
                            os.remove(p)
                        except OSError as e:
                            self.log(f"!! 블박 파일 지우기 실패 {p}: {e}")
                    total -= groups[b][0]
                    self.log(f"블박: 용량 {self.folder_limit / MiB:.0f}MB 넘음 → 가장 오래된 {b} 지움")
                    groups.pop(b)
                with open(os.path.join(self.folder, ORDER_FILE), "w", encoding="utf-8") as f:
                    f.writelines(b + "\n" for b in order if b in groups)
            self._set(folder_mb=round(total / MiB, 1))

            free = shutil.disk_usage(self.folder).free
            state = self._state()
            if free < self.min_free:
                if state != "no_space":
                    self.log(f"!! 블박: SD 빈 공간 {free / MiB:.0f}MB (< {self.min_free / MiB:.0f}MB) → 녹화 멈춤")
                    self._close_file()
                    self._set(state="no_space")
            elif state == "no_space":
                self.log("블박: 빈 공간 회복 → 새 파일로 녹화 다시 시작")
                self._set(state="recording")
        except Exception as e:
            self.log(f"!! 블박 용량 검사 오류: {e}")
