# models — 카메라로 물체를 알아보는 YOLO 모델

바꾸거나 지우지 마세요. 모델 파일(`*.onnx`)은 크기 때문에 **깃에는 올리지 않습니다** (`.gitignore`). 아래 「만드는 법」으로 언제든 똑같이 다시 만들 수 있습니다.

| 파일 | 무엇 | 있는 곳 | 확인된 것 |
|---|---|---|---|
| `yolo26n_320.onnx` | **YOLO26n · 입력 320 · 06 기본** | 노트북 · 라즈봇 (지문 같음 확인) | **라즈봇 OpenCV 4.10: 24.4장/초**(단독 · 중간 41ms) · 시험 사진 사람 3/4명 · 확신도 0.81~0.85 (노트북 OpenCV 5.0과 같음) |
| `yolo26n_640.onnx` | YOLO26n · 입력 640 · 작은 것(STOP 표지판 · 먼 사람)을 더 잘 봄 · 느림 | 노트북 · 라즈봇 | **라즈봇: 5.7장/초**(중간 177ms) · 사람 4/4명 · 0.67~0.90 |
| `gestures_yolo26n_320.onnx` | **손 모양 모델 (지시서 08)** · YOLO26n · 입력 320 · 라벨 5개 | 노트북 · (라즈봇 복사 대기) | 출력 `(1, 9, 2100)` · 라즈봇 확인 전 |
| `gestures_best.pt` | 위 모델의 원본 (Colab 학습 결과 · 다시 변환할 때) | 노트북 | — |
| `yolo11n_320.onnx` | YOLO11n · 입력 320 · 예전 기본 | 라즈봇 | 라즈봇 OpenCV DNN 약 16장/초 (2026-11-03 · `specs/02-follow-person.md`) |
| `yolo11n_640.onnx` | YOLO11n · 입력 640 | 라즈봇 | 속도 미측정 |

- `coco.txt`: 라벨 80가지 (한 줄에 하나 · **줄 번호 − 1 = 번호** · 0 `person` … 11 `stop sign` … 79 `toothbrush`). YOLO26n ONNX 안의 이름표(`names`)에서 그대로 뽑음 (2026-11-05) · 이 파일은 깃에 올림
- 06(`specs/06-person-stop.md`)은 **YOLO26n**을 쓴다 (조원 결정 2026-11-05). 찾는 것: `person`(0번) · `stop sign`(11번).
- 알아보는 것은 「무엇이 있다」까지입니다. COCO 80가지에 없는 모양(직접 그린 새 표지)은 못 찾습니다.
- 출력 모양: `(1, 84, 2100)`(320) · `(1, 84, 8400)`(640) = 상자 4개 값(cx · cy · w · h) + 80가지 점수 · NMS는 프로그램에서 (YOLO11과 같은 방식). 쓰인 연산은 기본 연산뿐 (`TopK` 없음 · 리뷰 #5 걱정 해당 없음).

## YOLO26n 출처 · 라이선스 · 만드는 법 (2026-11-05)
- 원본: Hugging Face **`Ultralytics/YOLO26`**의 `yolo26n.pt` (5,544,453 바이트)
  - SHA-256 `9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef` — Hugging Face에 적힌 값과 같음 확인
- 라이선스: **AGPL-3.0** (Hugging Face 표시) — 수업 · 레포에서 쓸 수 있음. 이 모델로 만든 서비스를 밖에 공개하려면 조건을 먼저 확인.
- 학습 데이터: COCO (물체 80가지)
- 만든 곳: **노트북** (라즈봇에는 아무것도 설치 안 함) — Python 3.12.10 · `ultralytics` 8.4.202 · `torch` 2.15.0+cpu · `onnx` 1.23.2
- 옵션: `YOLO("yolo26n.pt").export(format="onnx", imgsz=320 또는 640, opset=12, simplify=True, batch=1, dynamic=False)`
- 만든 파일 SHA-256
  - `yolo26n_320.onnx` (9,803,820 바이트) `02b7268c550575bb85a2ee421c02fc8261b0b1030f3d70cb5930029151c2e4ae`
  - `yolo26n_640.onnx` (9,929,954 바이트) `b2fb26c7391460c67985068bfdf241db05a77b97f795956c3a7368b441580cd3`
- 참고: 노트북 OpenCV(Windows)는 경로에 한글이 있으면 파일을 못 엶 → 파일을 메모리로 읽어 넘김 (`np.fromfile`). 라즈봇은 경로가 영어라 해당 없음.

## 손 모양 모델 (지시서 08) — 2026-11-05
- 만든 곳: **Colab 무료 T4** · `tools/colab/train_gestures.ipynb` · 기본 모델 `yolo26n.pt` · 입력 320
- 데이터: **HaGRID** (https://github.com/hukenovs/hagrid) 에서 `palm` · `fist` · `like` · `peace` 마다 학습 1,500장 · 검증 300장 + 같은 사진 속 `no_gesture` 상자 · 라이선스 **CC BY-SA 4.0 변형**
- 라벨: `0 palm` · `1 fist` · `2 like` · `3 peace` · `4 no_gesture` (ONNX 안 `names` 확인)
- 출력: `(1, 9, 2100)` = 상자 4개 값 + 5가지 점수 · opset 12
- SHA-256
  - `gestures_yolo26n_320.onnx` (9,729,766 바이트) `67bee24a8b14a8f2346cccd5f0359c5c7507b7b188885b76a296c5fec284ee82`
  - `gestures_best.pt` (5,411,653 바이트) `676293e099964f66e87df3cc1904dbefa64bf2c56dbee07e062f45b1d5eeedfa`
- 참고: 9번 셀을 두 번 실행해 ONNX가 두 개 받아졌음 → 가중치는 같고 안에 적힌 만든 시각만 다름 (지문이 다른 이유)

## YOLO11n
- 라즈봇에 2026-11-03부터 있음. 출처 · 라이선스 · 만든 방법은 아직 확인 안 함.
