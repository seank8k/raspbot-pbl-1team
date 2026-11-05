# 라즈봇 프로젝트 — 1조

대구대 「AI 자율주행 알고리즘 PBL」 1조 폴더입니다.
Yahboom RASPBOT-V2 + Raspberry Pi 5(`raspibot-01`)를 **웹 화면으로 조종하고, 라인 따라가기 · 블박 녹화 · 장애물 정지를 합친 자율주행**으로 만들어 가고 있습니다.

조원: 조장 · 운전석 · 트랙·표지 · 측정 · 기록·발표 (이름 대신 역할)

## 일하는 방식
- 조가 `specs/`에 **지시서**(무엇을 · 왜 · 규칙표 · 숫자 성공 기준 · 안전)를 쓰고, AI가 `missions/`에 코드를 만든다. 작업 수칙은 `AGENTS.md`.
- 지시서는 만들기 전에 **Codex 적대적 리뷰**를 받는다 → 원문은 `docs/reviews/`, 반영한 결정은 지시서에.
- 실제로 어떻게 움직였는지는 지시서 맨 아래 「결과」 표 · `results/` · `log.md`에 남긴다.
- 고칠 때는 **지시서부터** 고치고, 바퀴 없이 하는 자동 시험(`tools/test_*.py`)을 다시 돌린 뒤 실물로 시험한다.

## 만든 것
| 번호 | 지시서 | 프로그램 | 하는 일 |
|---|---|---|---|
| 01 | `specs/01-webabb.md` | `missions/webabb.py` · `missions/webabb/index.html` | 휴대폰 · 노트북 브라우저로 조종 (버튼 · 키보드 · 카메라 화면 · 정지 · 비상정지). 아래 03 · 04 · 05가 여기에 붙어 있음 |
| 02 | `specs/02-follow-person.md` | — | 사람 따라가기 (지시서만 · 구현 안 함) |
| 03 | `specs/03-blackbox.md` | `missions/blackbox.py` | 블박 녹화 (`results/blackbox/` · 3분 파일 · 폴더 2GB 한도) |
| 04 | `specs/04-line-tracer.md` | `missions/line.py` | 라인 따라가기 (웹 「라인 따라가기」 버튼 · 속도 80 · 제자리 회전 40) |
| 05 | `specs/05-obstacle-stop.md` | `missions/obstacle.py` | 라인 중 장애물 15cm 안 → 잠깐 멈춤 · 치우면 1초 뒤 재출발 · 줄이 안 보이면 옆걸음으로 찾기 (라인과 같이 켜짐) |
| 06 | `specs/06-person-stop.md` | — | 사람 · STOP 표지판 찾으면 화면에 STOP (YOLO26n · 라즈봇 24장/초 확인 · 만들기 전) |
| 08 | `specs/08-hand-gesture.md` | `tools/colab/train_gestures.ipynb` (학습) | 손 모양 4가지(보 · 주먹 · 엄지척 · 브이) 알아보기 · HaGRID로 Colab 학습 (학습 · 연결 전) |
| 07 | — | — | 자율주행 합치기 (지시서 쓰기 전) |

## before → after (실제 시험)
| 항목 | before | after |
|---|---|---|
| 라인 따라가기 (바닥) | 출발 0.5초 만에 줄 놓침 · 180° 회전 | 코너 통과 · 테이프 끝까지 · 조원 「성공」 |
| 장애물 정지 | 속도 90에서 **충돌** | 속도 80에서 충돌 0 (136mm에서 멈춰 85mm에서 섬) |
| 자동 시험 (바퀴 안 씀) | — | 라인 59/59 · 장애물 판단 29/29 · 웹 깨뜨리는 시험 18/18 |

## 실행 (라즈봇 안 이 폴더에서)
- 웹 조종 (라인 · 장애물 · 블박 포함): `python3 missions/webabb.py` → 같은 핫스팟에서 `http://raspibot-01.local:5000`
- 바퀴 없이 시험: `python3 missions/webabb.py --dry` · 자동 시험 `python3 tools/test_line.py` · `python3 tools/test_obstacle.py`
- 키보드 조종: `python3 tools/teleop.py` (사람이 VS Code 터미널에서 직접)
- 점검: `tools/motor_test.py` · `servo_center.py` · `sensor_test.py` · `drive_test.py` (AGENTS.md 「점검 프로그램」)

## 폴더
| 자리 | 무엇 |
|---|---|
| `specs/` | 지시서 `NN-이름.md` · 틀 `00-template.md` |
| `missions/` | 지시서대로 만든 프로그램 (서로 불러 쓰는 부품이라 파일 이름에 번호를 안 붙임 · 번호 짝은 위 「만든 것」 표 · 조원 결정 2026-11-05) |
| `tools/` | 점검 프로그램 · 자동 시험 `test_*.py` · 측정 도구 · 드라이버 압축 |
| `results/` | 측정 결과 `날짜-이름` · 블박 `blackbox/` · 영상 샘플 `videos/` (영상은 레포에 안 올림) |
| `docs/` | 진행상황 정리 · Codex 리뷰 원문 `reviews/` |
| `models/` | YOLO 모델 (라즈봇에만 있음 · `models/README.md`) |
| `log.md` | 문제 · 원인 추정 · 시도 · 결과 · 누가 |

## 안전 규칙
- 바퀴 속도: 라인 **80** · 프로젝트 한계 150. 바퀴 돌리기 전에 **바닥 · 사방 1m 비움 · 확장보드 전원 스위치 옆에 사람**.
- 라인 모드 중 라즈봇을 **들기 전에는 꼭 라인을 끈다** (멈춰 있다가 내려놓으면 자동 출발할 수 있음).
- 장애물 시험은 상자 · 스티로폼만 (사람 몸 X). 줄 양옆 10cm 안에는 물건을 두지 않는다.
- 사람 얼굴이 나온 사진 · 영상, 비밀번호 · API 키는 레포에 올리지 않는다.
