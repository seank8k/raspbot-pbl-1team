이상.

1. **[치명] 별도 스레드만으로 정지 경로를 보호한다는 가정이 성립하지 않는다.**  
   **근거:** [specs/03-blackbox.md:35](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:35), [missions/webabb.py:175](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:175), [missions/webabb.py:385](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:385).  
   **시나리오:** 블박이 `Camera.lock`을 잡은 채 시각 그리기·인코딩·파일 쓰기를 하면, SD 쓰기가 2초 걸릴 때 제어부의 `camera.age()`도 2초 막힌다. 잠금을 풀어도 CPU 경쟁과 GIL 영향은 남는다. 단, OpenCV 연산 전체가 GIL을 계속 잡는다고 단정할 수는 없다. 일반적인 Python 스레드는 CPU 작업의 독립 실행을 보장하지 않는다. [Python 문서](https://docs.python.org/3.13/library/threading.html)  
   **고칠 방법:** 카메라 잠금 안에서는 프레임 참조와 시각만 전달하고, 용량 제한이 있는 비차단 전달 경로·프레임 폐기 규칙·정지 지연 상한을 정하며, 충족하지 못하면 녹화 프로세스 분리를 검토한다.

2. **[치명] 녹화 때문에 제어부가 막혔다 풀리면 감시 정지 뒤 다시 움직일 수 있다.**  
   **근거:** [missions/webabb.py:378](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:378), [missions/webabb.py:438](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:438), [missions/webabb.py:494](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:494).  
   **시나리오 — 추정:** 이동 요청을 읽은 제어부가 카메라 잠금에서 멈추면, 감시는 0.3초 뒤 바퀴에 0을 보낸다. 그러나 감시는 누름 번호를 무효화하거나 주행 잠금을 남기지 않는다. 잠금이 풀리고 새 영상이 있으면 제어부가 앞서 읽은 이동을 이어서 출력할 수 있다.  
   **고칠 방법:** 감시 개입 시 기존 이동을 무효화하고 새 누름을 요구하며, 실제 모터 출력 직전에 명령 유효성을 다시 확인하도록 통합 조건에 명시한다.

3. **[치명] “쓰기 지연 시 녹화만 멈춤”을 실행할 장치가 없다.**  
   **근거:** [specs/03-blackbox.md:21](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:21), [specs/03-blackbox.md:48](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:48), [기록/01-진행상황-2026-11-02.md:98](C:/Users/박시현/Desktop/raspbot/기록/01-진행상황-2026-11-02.md:98).  
   **시나리오 — 추정:** 녹화 스레드가 `write()` 안에서 수 초 멈추면 그 스레드 자신의 느림 감지 코드도 실행되지 않는다. 프레임을 계속 쌓으면 메모리가 증가하고, 같은 프로세스가 죽으면 제어부·감시도 함께 사라진다. 보드가 스스로 정지하는지는 아직 미확인이다.  
   **고칠 방법:** 별도 감시자의 녹화 진행 시각, 큐 상한, 지연 판정 시간, 추가 프레임 차단, 멈춘 작업자의 처리 방법과 보드 정지 검증을 정한다.

4. **[높음] 현재 카메라는 실제 10fps를 보장하지 않아 영상으로 시간을 재면 틀릴 수 있다.**  
   **근거:** [missions/webabb.py:171](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:171), [missions/webabb.py:182](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:182), [specs/03-blackbox.md:11](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:11), [specs/03-blackbox.md:52](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:52).  
   **시나리오:** 현재 루프는 읽기·JPEG 인코딩을 마친 뒤 다시 0.1초 잔다. 실제 수신이 7fps인데 새 프레임만 10fps 파일에 쓰면, 실제 180초가 재생 시 약 126초가 된다. 반대로 같은 프레임을 반복하면 정지 화면이 늘어난다.  
   **고칠 방법:** 단조 시계 기준 저장 슬롯과 누락·중복 정책을 정하고, 원본 프레임 번호·촬영 시각을 별도 기록해 실제 시간과 재생 시간을 검증한다.

5. **[높음] 설계 그림에 있는 블박 입력이 현재 `Camera`에는 없다.**  
   **근거:** [specs/03-blackbox.md:47](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:47), [missions/webabb.py:173](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:173), [missions/webabb.py:190](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:190).  
   **시나리오:** `latest()`는 원본 영상 배열이 아닌 JPEG 바이트를 준다. 그대로 이용하면 JPEG 디코딩 → 시각 그리기 → MJPG 재인코딩 비용과 화질 손실이 생긴다. 원본을 추가 공유하면 웹 인코딩·향후 YOLO와 동시에 같은 배열을 수정할 위험이 생긴다.  
   **고칠 방법:** JPEG 재사용과 원본 전달 중 하나를 정하고, 원본 전달 시 복사 책임·수명·수정 금지·전달 비용을 명시한다.

6. **[높음] 녹화 시각으로 오래된 프레임을 새 영상처럼 보이게 만들 수 있다.**  
   **근거:** [missions/webabb.py:176](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:176), [missions/webabb.py:192](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:192), [specs/03-blackbox.md:18](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:18).  
   **시나리오:** 카메라가 끊겨도 `latest()`에는 마지막 JPEG가 남는다. 이를 10번씩 읽고 현재 시각만 새로 찍으면, 실제로는 멈춘 영상이 계속 촬영된 것처럼 보인다. 현재 `frame_time`도 센서 촬영 시각이 아니라 JPEG 생성 완료 시각이다.  
   **고칠 방법:** 새 프레임 여부와 프레임 나이를 검사하고, 표시 시각의 의미를 정하며, 녹화 동작이 카메라 생존 시각을 갱신하지 못하게 한다.

7. **[높음] 녹화 성공을 판정할 근거가 부족하다.**  
   **근거:** [specs/03-blackbox.md:21](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:21), [specs/03-blackbox.md:55](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:55), [specs/03-blackbox.md:60](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:60).  
   **시나리오:** MJPG 열기에 성공했어도 이후 디스크 부족·입출력 오류로 저장이 실패할 수 있다. `VideoWriter.write()`는 성공 여부를 반환하지 않고, `isOpened()`도 초기화 성공 확인이다. 예외가 없다는 이유로 ● 녹화 중을 계속 표시할 수 있다. [OpenCV 4.10 문서](https://docs.opencv.org/4.10.0/dd/d9e/classcv_1_1VideoWriter.html)  
   **고칠 방법:** 실제 Pi의 백엔드·MJPG·프레임 크기를 시험하고, 쓰기 진행·파일 증가·완료 파일 디코딩을 조합한 실패 판정과 감지 한계를 정한다.

8. **[높음] “AVI는 꺼지기 직전까지 VLC로 볼 수 있다”는 보장이 과하다.**  
   **근거:** [specs/03-blackbox.md:28](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:28), [specs/03-blackbox.md:53](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:53).  
   **시나리오 — 추정:** 인덱스·헤더 갱신이나 프레임 쓰기 도중 죽으면 마지막 AVI가 정상 탐색되지 않거나 복구를 요구할 수 있다. 재생기가 일부 프레임을 찾아준다는 것과 마지막 순간까지 보존됐다는 것은 다르다. FFmpeg AVI 구현에도 종료 시 인덱스·헤더를 마무리하는 처리가 있다. [FFmpeg 소스](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/avienc.c)  
   **고칠 방법:** 완료 파일과 미완료 파일의 보장을 나누고, 마지막 허용 손실 시간·복구 허용 여부·끝부분 실제 디코딩을 성공 기준으로 정한다.

9. **[높음] 현재 종료 방식에 녹화 파일 마무리가 들어갈 자리가 정의되지 않았다.**  
   **근거:** [missions/webabb.py:512](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:512), [missions/webabb.py:517](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:517), [missions/webabb.py:523](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:523), [specs/03-blackbox.md:51](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:51).  
   **시나리오:** Ctrl+C·SIGTERM도 현재는 `os._exit(0)`로 끝난다. 녹화 스레드의 `finally`나 객체 소멸자에 `release()`를 넣어도 실행을 보장하지 못한다. 반대로 녹화 종료를 먼저 기다리면 바퀴 정지를 늦춘다. `_exit()`는 정리 처리기를 실행하지 않는다. [Python 문서](https://docs.python.org/3.13/library/os.html#os._exit)  
   **고칠 방법:** 바퀴 정지를 먼저 수행하고, 녹화 마무리는 제한 시간 안에서만 기다리며, 시간 초과 시 미완료로 남기는 순서를 정한다.

10. **[높음] 프로그램 강제 종료 시험으로 전원 차단 내구성을 주장할 수 없다.**  
    **근거:** [specs/03-blackbox.md:17](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:17), [specs/03-blackbox.md:28](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:28), [specs/03-blackbox.md:64](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:64).  
    **시나리오 — 추정:** 프로세스만 죽이면 운영체제는 남아 캐시를 SD에 기록할 수 있다. 전원을 끊으면 그 캐시도 사라져 앞서 닫은 파일까지 영향을 받을 수 있다. “강제 종료”가 SIGTERM인지 SIGKILL인지도 불명확하다.  
    **고칠 방법:** 정상 종료·SIGKILL·전원 차단의 보장 범위를 분리하고, 전원 차단을 시험하지 않는다면 해당 내구성은 미검증으로 명시한다.

11. **[높음] 2GB 규칙은 검사 시점·현재 파일·초과 허용량이 없어 실행 가능한 규칙이 아니다.**  
    **근거:** [specs/03-blackbox.md:19](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:19), [specs/03-blackbox.md:30](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:30), [specs/03-blackbox.md:36](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:36).  
    **시나리오:** 파일 교체 때만 검사하면 한 파일 크기만큼 넘는다. 100MB 시험에서는 현재 파일 하나만으로 한도를 넘을 수도 있다. 녹화 중 파일을 삭제하면 Linux에서는 쓰기가 이어질 수 있고, 폴더 합계만 줄어 공간이 확보됐다고 오판할 수 있다.  
    **고칠 방법:** GB의 바이트 값·검사 주기·활성 파일 포함 여부·활성 파일 삭제 금지·파일 크기 상한·삭제 실패 처리를 정한다.

12. **[높음] 블박 폴더 2GB 제한은 SD 전체 공간 부족을 막지 못한다.**  
    **근거:** [specs/03-blackbox.md:36](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:36), [specs/03-blackbox.md:54](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:54), [AGENTS.md:18](C:/Users/박시현/Desktop/raspbot/AGENTS.md:18).  
    **시나리오:** 다른 사진·제출 영상·로그가 SD를 채우면 블박이 100MB만 사용해도 쓰기가 실패한다. 공간 확보를 위해 `results/` 전체의 오래된 파일을 지우면 제출물까지 잃는다.  
    **고칠 방법:** 파일시스템 최소 여유 공간과 부족 시 녹화 중단 규칙을 추가하고, 삭제 대상을 블박이 소유한 파일로 제한한다.

13. **[높음] 시계 보정과 파일명 충돌이 기록 덮어쓰기·삭제 순서를 망칠 수 있다.**  
    **근거:** [specs/03-blackbox.md:19](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:19), [specs/03-blackbox.md:29](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:29), [specs/03-blackbox.md:49](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:49).  
    **시나리오 — 추정:** 같은 초에 재시작하거나 시스템 시계가 뒤로 보정되면 파일명이 겹쳐 기존 영상을 덮어쓸 수 있다. 파일명 시각이나 수정 시각만으로 정렬하면 실제 오래된 순서와 달라진다. 시각 동기화가 안 된 부팅에서 1초 정확도도 보장할 수 없다. 참고로 Pi 5에는 RTC가 내장되어 있어 “RTC 없음”은 하드웨어 사실과 맞지 않으며, 실제 시각 유지 상태를 확인해야 한다. [Raspberry Pi 문서](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#real-time-clock-rtc)  
    **고칠 방법:** 충돌 없는 실행 ID·파일 순번과 덮어쓰기 방지를 쓰고, 분할은 단조 시계로 처리하며, 시각 미검증·보정 발생을 기록한다.

14. **[높음] “조종에 영향 없음” 시험은 지연 사고가 생기는 순간을 겨냥하지 않는다.**  
    **근거:** [specs/03-blackbox.md:31](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:31), [specs/03-blackbox.md:65](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:65), [specs/webabb.md:40](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:40), [기록/01-진행상황-2026-11-02.md:97](C:/Users/박시현/Desktop/raspbot/기록/01-진행상황-2026-11-02.md:97).  
    **시나리오:** 평상시 버튼을 몇 번 눌러 통과해도 파일 교체·대량 삭제·SD 수 초 지연과 겹친 정지 요청은 놓친다. 비교 기준인 기존 실제 바퀴 시험과 카메라 지연 측정도 아직 끝나지 않았다.  
    **고칠 방법:** 기존 실측 기준선을 먼저 확보하고, 쓰기·교체·삭제 지연 중 손 떼기·비상정지·영상 단절을 겹쳐 시험해 최대 정지 시간과 잘못된 정지 횟수를 판정한다.

15. **[높음] 블박 단독 30분·80°C 기준으로 07 통합 운행을 승인할 수 없다.**  
    **근거:** [specs/03-blackbox.md:4](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:4), [specs/03-blackbox.md:32](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:32), [specs/03-blackbox.md:41](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:41).  
    **시나리오 — 추정:** 쿨러 없는 상태에서 나중에 YOLO·라인 인식·웹 전송까지 돌리면 온도와 CPU 경쟁이 증가한다. 스로틀링으로 제어 주기와 영상 갱신이 느려져도 단독 시험은 통과한다. 공식 문서상 80~85°C에서 CPU가 점진적으로 제한된다. [Raspberry Pi 문서](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#frequency-management-and-thermal-control)  
    **고칠 방법:** 예정된 동시 부하·주변 온도·운행 시간에서 온도뿐 아니라 스로틀링 이력·클럭·프레임 간격·제어 지연을 측정하고, 과부하 시 녹화 축소·중단 기준을 정한다.

16. **[높음] 파일을 나누는 것만으로 07 재사용 구조가 만들어지지 않는다.**  
    **근거:** [specs/03-blackbox.md:51](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:51), [missions/webabb.py:75](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:75), [missions/webabb.py:143](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:143), [missions/webabb.py:200](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:200).  
    **시나리오:** 현재 `webabb.py`는 가져오기만 해도 인자 해석과 모터·카메라 생성이 일어난다. 07이 카메라를 얻으려고 가져오면 자기 인자와 충돌하거나 장치를 중복 소유할 수 있다. 녹화기 두 개가 같은 폴더를 관리하면 서로의 활성 파일을 삭제할 수도 있다.  
    **고칠 방법:** 카메라·녹화기의 단일 소유자, 장치와 무관한 프레임 입력 인터페이스, 시작·종료 책임, 폴더 관리자의 단일 실행 규칙을 정한다.

17. **[중간] 화면 없음·느림·실패·복구의 상태 규칙이 비어 있다.**  
    **근거:** [specs/03-blackbox.md:16](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:16), [specs/03-blackbox.md:20](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:20), [specs/03-blackbox.md:21](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:21).  
    **시나리오:** 카메라가 2분 끊겼다 돌아올 때 기존 파일을 이어 쓸지, 빈 구간을 보존할지 정해져 있지 않다. 잠깐의 쓰기 지연 뒤 영구 중단할 수도 있고, 무제한 재시도로 SD 부하를 키울 수도 있다. “느림”이 한 장 누락인지 수 초 정체인지도 불명확하다.  
    **고칠 방법:** 대기·녹화·영상 없음·저장 실패·비활성 상태와 전이 조건, 재시도 간격·횟수, 빈 구간 정책을 규칙표에 추가한다.

18. **[중간] 상태 표시를 추가하다 조종 HTTP 경로에 디스크 작업을 넣을 위험이 있다.**  
    **근거:** [specs/03-blackbox.md:55](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:55), [missions/webabb.py:542](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:542), [missions/webabb.py:594](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:594), [missions/webabb/index.html:165](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:165).  
    **시나리오 — 추정:** 폴더 용량을 보여주려고 `status_json()`에서 매번 디렉터리를 훑으면 이동 응답도 SD 상태에 묶인다. 브라우저는 미완료 이동 요청이 세 개면 추가 전송을 멈추므로, 상태 표시 때문에 신호가 끊겨 잘못 정지할 수 있다.  
    **고칠 방법:** 상태 API에는 메모리에 저장된 스냅샷만 넣고, 디스크 조회·작업자 대기 없이 상태와 상태 갱신 시각을 표시한다.

19. **[중간] “파일 사이 1초 이내”를 현재 표시 방식으로는 충분히 검증할 수 없다.**  
    **근거:** [specs/03-blackbox.md:18](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:18), [specs/03-blackbox.md:27](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:27), [specs/webabb.md:52](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:52).  
    **시나리오:** 초 단위 글자와 AVI 재생 시간만 비교하면 실제 누락·중복 프레임을 구별하기 어렵다. 파일이 네 개 생겨도 경계마다 영상이 끊겼을 수 있다. 앞을 보는 10fps 블박 영상만으로는 키를 뗀 시각과 바퀴 정지 시각도 함께 볼 수 없다.  
    **고칠 방법:** 이전 파일의 마지막 원본 프레임과 다음 파일의 첫 원본 프레임 시각으로 간격을 재고, 실제 정지는 기존 외부 촬영 방식으로 별도 판정한다.

20. **[중간] 용량·재생 시험 횟수가 위험 범위를 덮지 못한다.**  
    **근거:** [specs/03-blackbox.md:27](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:27), [specs/03-blackbox.md:28](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:28), [specs/03-blackbox.md:30](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:30), [specs/03-blackbox.md:53](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:53).  
    **시나리오:** 3회 종료가 모두 파일 중간에서만 일어나면 생성·교체·삭제 중 실패는 미검증이다. MJPG 크기는 장면에 따라 달라지므로 정적인 화면에서 얻은 “약 50MB”와 “약 1시간 40분”도 움직임·노이즈가 많은 상황의 보존량을 보장하지 못한다.  
    **고칠 방법:** 생성·쓰기·교체·삭제 경계별 실패 시험과 장면별 크기 측정을 추가하고, 예상 보존 시간은 실측 범위로 표시한다.

21. **[중간] 사람이 찍히는 연속 녹화의 열람·보관·반출 규칙이 없다.**  
    **근거:** [specs/03-blackbox.md:4](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:4), [specs/03-blackbox.md:16](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:16), [specs/03-blackbox.md:19](C:/Users/박시현/Desktop/raspbot/specs/03-blackbox.md:19).  
    **시나리오:** 사람 STOP 시험 중 얼굴이 계속 저장되고 학생 PC로 복사될 수 있다. 이후 사용하지 않으면 2GB에 도달하지 않아 파일이 무기한 남고, 복사본에는 순환 삭제가 적용되지 않는다.  
    **고칠 방법:** 촬영 범위·주변 사람 안내·열람자·보관 기간·공유 및 삭제 책임을 조원이 정한다.

**이대로 구현을 시작해도 되는가: 아니오 — 정지 경로 격리, 지연·실패 처리, 시간 보존과 파일 안정성의 계약을 먼저 지시서에 정해야 한다.**