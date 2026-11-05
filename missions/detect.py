#!/usr/bin/env python3
# 지시서: specs/06-person-stop.md (사람 · STOP 표지판) · specs/08-hand-gesture.md (손 모양)
# 카메라 장면 1장 → 「무엇이 어디에 · 확신도」만 돌려준다. 바퀴 · 웹을 모른다 (화면 표시용 · 07에서 재사용).
# 모델: models/yolo26n_320.onnx (COCO 80가지 중 person · stop sign) · models/gestures_yolo26n_320.onnx (손 모양 5가지)
# 라즈봇 OpenCV DNN 으로만 돈다 (추가 설치 없음).
import os
import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(os.path.dirname(HERE), "models")

SHOW_THR = 0.5     # 화면 표시용 임시 값 (지시서 06 · 08 「보임」 기준은 조원 결정 전)
NMS_THR = 0.45

COCO_FILE = os.path.join(MODELS, "yolo26n_320.onnx")
GESTURE_FILE = os.path.join(MODELS, "gestures_yolo26n_320.onnx")
GESTURE_NAMES = ["palm", "fist", "like", "peace", "no_gesture"]   # ONNX 안 names 와 같은 순서 (models/README.md)
COCO_WANT = {0: "person", 11: "stop sign"}                          # 06 에서 보는 것만


class Model:
    def __init__(self, path, names, size=320, want=None):
        self.net = cv2.dnn.readNetFromONNX(path)
        self.names, self.size, self.want = names, size, want
        self.path = path

    def detect(self, img, thr=SHOW_THR):
        """BGR 장면 → [dict(label, conf, box=(x, y, w, h) 0~1 비율)] (확신도 높은 순)"""
        blob = cv2.dnn.blobFromImage(img, 1 / 255.0, (self.size, self.size), swapRB=True)
        self.net.setInput(blob)
        p = self.net.forward()[0].T                     # (N, 4 + 분류 수): cx cy w h + 점수
        scores = p[:, 4:]
        cls, conf = scores.argmax(1), scores.max(1)
        keep = conf > thr
        if self.want is not None:
            keep &= np.isin(cls, list(self.want))
        if not keep.any():
            return []
        p, cls, conf = p[keep], cls[keep], conf[keep]
        s = float(self.size)
        boxes = [[float((c[0] - c[2] / 2) / s), float((c[1] - c[3] / 2) / s), float(c[2] / s), float(c[3] / s)] for c in p]
        idx = np.array(cv2.dnn.NMSBoxes(boxes, conf.tolist(), thr, NMS_THR)).flatten()
        out = []
        for i in idx:
            x, y, w, h = boxes[i]
            x, y = max(0.0, x), max(0.0, y)
            out.append(dict(label=self.names[int(cls[i])], conf=round(float(conf[i]), 2),
                            box=(round(x, 4), round(y, 4), round(min(w, 1 - x), 4), round(min(h, 1 - y), 4))))
        return sorted(out, key=lambda d: -d["conf"])


def load_models(log=print):
    """있는 모델만 불러온다. [(이름, Model)] — 하나도 없으면 빈 목록."""
    models = []
    names = [l.strip() for l in open(os.path.join(MODELS, "coco.txt"), encoding="utf-8")] if os.path.exists(os.path.join(MODELS, "coco.txt")) else None
    for tag, path, nm, want in (("coco", COCO_FILE, names, COCO_WANT), ("gesture", GESTURE_FILE, GESTURE_NAMES, None)):
        if not os.path.exists(path) or nm is None:
            log(f"인식: {os.path.basename(path)} 없음 → 이 모델은 끔")
            continue
        try:
            models.append((tag, Model(path, nm, 320, want)))
            log(f"인식: {os.path.basename(path)} 불러옴")
        except Exception as e:
            log(f"!! 인식: {os.path.basename(path)} 불러오기 실패: {e}")
    return models
