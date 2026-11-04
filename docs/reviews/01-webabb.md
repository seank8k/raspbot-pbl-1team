이상

1. **[치명] 정지한 뒤, 늦게 도착한 이동 요청으로 재출발할 수 있다.**  
   **근거:** [화면:92](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:92), [화면:134](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:134), [화면:150](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:150), [서버:233](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:233).  
   **시나리오:** 이동 요청들이 처리 중인 상태에서 손을 떼거나 스페이스바를 누른다. 정지 요청이 먼저 처리되고 이전 이동 요청이 나중에 처리되면 다시 움직인다. 서버는 요청 순서·유효기간을 확인하지 않고, 도착한 이동 요청마다 데드맨 시간을 갱신한다. 탭 전환·blur·pointercancel 처리도 이 문제를 막지 못한다.  
   **고칠 방법:** 명령 순번·조작 세대·유효기간을 검증하고, 정지 이전의 이동 요청은 폐기하며 새로 누르기 전까지 재출발을 금지한다.

2. **[치명] 정지 명령 도중 오류가 나면 나머지 바퀴 정지를 시도하지 않는다.**  
   **근거:** [서버:66](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:66), [서버:78](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:78), [서버:184](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:184), [기획서:49](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:49).  
   **시나리오:** `stop()`은 실제 정지보다 먼저 `state=None`으로 바꾼다. 첫 번째 바퀴 호출에서 예외가 발생하면 뒤의 세 바퀴에는 정지를 보내지 않고, 데드맨은 이미 정지 상태라고 판단한다. 이동 중 예외도 Flask 요청 오류로 끝날 뿐 즉시 전체 정지를 보장하지 않는다. 드라이버가 오류를 삼키는 경우에는 실패 자체를 감지하지 못한다.  
   **고칠 방법:** 바퀴별 실패와 관계없이 네 바퀴 모두 정지를 시도하고, 실패 시 이동을 잠그며 독립된 모터 차단 수단을 둔다.

3. **[치명] 데드맨 스레드가 죽거나 모터 호출이 멈추면 안전장치도 함께 사라진다.**  
   **근거:** [서버:69](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:69), [서버:79](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:79), [서버:184](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:184), [서버:292](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:292).  
   **시나리오:** 데드맨 내부의 정지·로그 호출에서 예외가 나면 스레드는 끝난다. 모터 호출이 잠금을 잡은 채 반환하지 않으면 데드맨과 종료 처리도 같은 잠금에서 기다린다. 프로세스 강제 종료·전체 멈춤에는 `finally`와 `atexit`도 정지를 보장하지 못한다.  
   **고칠 방법:** 데드맨 생존 확인과 호출 시간 제한을 추가하고, 프로그램이 멈춰도 정지하는 보드 측 타임아웃 또는 독립 차단 장치를 마련한다.

4. **[높음] 권한 확인과 실제 이동이 분리되어 있어, 자리를 잃은 사람의 명령이 실행될 수 있다.**  
   **근거:** [서버:165](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:165), [서버:172](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:172), [서버:235](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:235).  
   **시나리오:** A의 이동 요청이 권한 확인을 통과한 직후 대기한다. 다른 요청에서 A가 자리를 반납하고 B가 자리를 얻는다. 이후 A의 요청이 계속 실행되어 바퀴를 돌린다. `seat.lock`은 확인 순간만 보호한다.  
   **고칠 방법:** 단일 제어 처리부에서 실행 직전 조종 토큰·자리 세대·명령 유효성을 다시 검사하고 자리 교체와 정지를 함께 처리한다.

5. **[높음] 연결이 복구되면 새로 누르지 않아도 자동 재출발한다.**  
   **근거:** [화면:134](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:134), [화면:141](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:141).  
   **시나리오:** 방향을 누르는 중 짧게 통신이 끊겨 데드맨으로 멈춘다. 전송 실패 처리는 안내 문구만 바꾸고 `active`와 반복 전송을 유지한다. 자리가 만료되기 전에 통신이 돌아오면 기존 조작으로 다시 출발한다.  
   **고칠 방법:** 통신 이상이나 데드맨 정지 후에는 조작을 해제하고, 연결 회복 뒤 새로 누른 입력만 받는다.

6. **[높음] 정지 버튼이 실패해도 사용자에게 실패를 알리지 않는다.**  
   **근거:** [화면:150](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:150), [서버:250](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:250).  
   **시나리오:** 화면은 정지 요청의 응답·실패를 확인하지 않는다. 서버도 잘못된 토큰의 정지 요청에 `200 / ok=True`를 반환한다. 사용자는 정지가 거절되거나 전달되지 않았다는 사실을 알 수 없고, 다른 조원의 거절 화면에는 정지 수단도 없다.  
   **고칠 방법:** 정지 거절은 403으로 구분하고 정지 응답·실제 제어 상태를 표시하며, 조종 자리와 별개인 비상정지 수단을 정한다.

7. **[높음] 같은 핫스팟의 기기는 브라우저 없이 자리를 선점하고 계속 움직일 수 있다.**  
   **근거:** [기획서:50](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:50), [서버:217](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:217), [서버:233](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:233), [서버:290](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:290).  
   **시나리오:** 다른 기기가 직접 `/api/claim`으로 토큰을 얻고 이동 요청을 반복한다. 손을 누르고 있는지 서버는 구분할 수 없다. 비밀번호를 쓰지 않는 결정에 비인가 조종·무기한 자리 점유의 대응 규칙이 빠져 있다.  
   **고칠 방법:** 비밀번호를 생략한다면 최소한 로봇 앞에서 조원이 승인하는 조종 허용 절차와 강제 회수·비상정지를 둔다.

8. **[높음·추정] 카메라와 HTTP 부하가 커질 때 제어 지연의 상한이 없다.**  
   **근거:** [서버:267](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:267), [서버:290](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:290), [화면:147](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:147).  
   **시나리오:** MJPEG 연결은 요청 스레드를 오래 점유하고, 같은 토큰으로 여러 스트림을 열 수도 있다. 이동 요청은 이전 응답을 기다리지 않고 계속 생성된다. 카메라 연결 수·요청 수·대역폭 제한이 없어 지연과 오래된 명령 적체가 발생할 수 있다. 스레드 방식이므로 스트림 하나가 모든 명령을 막는다고 단정할 수는 없지만, 안전 시간 보장도 없다. Flask 역시 개발 서버의 안정성·효율성을 보장하지 않는다. [공식 문서](https://flask.palletsprojects.com/en/stable/server/)  
   **고칠 방법:** 제어부를 영상·웹 처리와 분리하고 연결 수·대기 요청을 제한하며 카메라 부하 상태에서 최악 지연을 측정한다.

9. **[높음] 카메라가 멈춰도 마지막 화면과 조종은 계속 남을 수 있다.**  
   **근거:** [서버:119](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:119), [서버:130](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:130), [서버:275](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:275), [화면:123](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:123).  
   **시나리오:** 카메라 읽기가 계속 실패하면 이전 `frame`이 남는다. 스트림은 새 사진 없이 연결을 유지할 수 있어 화면의 `onerror`도 발생하지 않을 수 있다. 조종자는 멈춘 영상을 현재 모습으로 오인한다.  
   **고칠 방법:** 촬영 시각·프레임 번호로 화면 나이를 감시하고, 영상이 오래됐을 때 경고·정지 여부와 직접 눈으로 조종하는 예외를 지시서에 정한다.

10. **[높음] ‘0.4초 데드맨’은 현재 구현의 보장 시간이 아니다.**  
    **근거:** [기획서:20](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:20), [서버:184](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:184), [기획서:91](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:91).  
    **시나리오:** 0.05초 간격으로 검사하므로 지연이 없어도 판정은 약 0.4~0.45초 뒤다. 이후 잠금 대기·네 바퀴 명령·물리적 감속 시간이 더해진다. 결과 표의 0.43초는 0.4초 정지 보장의 증거가 아니다.  
    **고칠 방법:** 신호 만료 시간·정지 명령 완료 시간·실제 바퀴 정지 시간을 구분하고, 요구 상한에서 검사와 구동 지연을 뺀 값으로 타임아웃을 정한다.

11. **[중간] 3초 자리 만료를 권한 검사 자체에서 확인하지 않는다.**  
    **근거:** [서버:154](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:154), [서버:165](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:165), [서버:190](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:190), [화면:106](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:106).  
    **시나리오:** 아무 버튼도 누르지 않는 정상 조종자는 1초 ping으로 자리를 유지한다. 그러나 3초를 넘긴 토큰도 데드맨 스레드가 지우기 전에 요청하면 `check()`가 살려 준다. 스레드가 죽으면 기존 토큰이 계속 유효할 수 있다. 반대로 백그라운드·화면 꺼짐으로 ping이 중단되면 사람이 보고 있어도 자리를 잃는다.  
    **고칠 방법:** 모든 권한 검사에서 만료를 직접 확인하고, ‘자리 비움’을 입력 없음인지 연결 확인 없음인지 명시한다.

12. **[중간] 새로고침·같은 사람 두 탭·자동 자리 획득 규칙이 빠져 있다.**  
    **근거:** [기획서:24](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:24), [화면:96](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:96), [화면:189](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:189).  
    **시나리오:** 토큰은 탭 메모리에만 있다. 새로고침 때 반납 요청이 늦거나 실패하면 본인이 409를 받고, 반납되면 대기하던 다른 탭이 먼저 차지할 수 있다. 거절된 탭도 매초 재시도하므로 실제 기준은 ‘먼저 접속한 사람’보다 ‘빈 순간 먼저 요청한 탭’이다.  
    **고칠 방법:** 자리 단위를 사람·브라우저·탭 중 하나로 정하고 새로고침 복구와 대기 순서·자동 획득 여부를 명시한다.

13. **[중간] 복수 입력에서 방향 선택과 손 뗌의 의미가 정해져 있지 않다.**  
    **근거:** [기획서:17](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:17), [화면:87](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:87), [화면:159](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:159), [화면:179](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:179).  
    **시나리오:** W와 A를 누른 채 화면의 오른쪽 버튼을 누르고 A를 떼면, 키 해제 처리가 W 방향을 다시 실행한다. 오른쪽 버튼은 계속 누르고 있어도 방향이 바뀐다. 같은 버튼을 두 손가락으로 누른 뒤 하나만 떼면 나머지 손가락이 있어도 멈춘다.  
    **고칠 방법:** 키·포인터별 눌림 상태를 관리하고 복수 입력의 우선순위와 해제 시 동작을 지시서에 정한다.

14. **[중간·추정] CSRF로 기존 조종자를 바로 탈취하는 위험과 자리 방해 위험이 구분되지 않았다.**  
    **근거:** [서버:217](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:217), [서버:261](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:261).  
    **시나리오:** 토큰이 자동 전송되는 쿠키가 아니므로 외부 페이지가 기존 조종자의 이동 명령을 바로 위조한다고 단정할 수는 없다. 하지만 `/api/claim`은 토큰·본문·Origin 검사 없이 POST를 받는다. 브라우저의 사설망 접근 정책이 허용하는 환경에서는 외부 페이지가 빈 자리를 점유해 정상 접속을 방해할 수 있다.  
    **고칠 방법:** 변경 요청의 Origin·Host와 요청 형식을 검증하고, 직접 HTTP 공격에는 별도의 조종 승인 절차를 적용한다.

15. **[중간] 토큰 추측보다 URL·평문 노출에 대한 대책이 부족하다.**  
    **근거:** [서버:161](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:161), [화면:128](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:128), [기획서:65](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:65).  
    **시나리오:** 토큰은 64비트 난수여서 단순 추측을 가장 큰 위험으로 보기는 어렵다. 반면 영상 URL에 토큰을 넣어 접근 로그 등에 남기며 HTTP로 전송한다. 로그 접근이나 트래픽 관찰이 가능한 사람이 토큰을 얻으면 같은 조종자로 요청할 수 있다. 같은 핫스팟이라는 사실만으로 도청 가능성을 확정할 수는 없다.  
    **고칠 방법:** 토큰을 로그·URL에서 숨기고 자리 종료 시 폐기하며, 네트워크 신뢰 범위에 맞춰 암호화와 토큰 수명을 정한다.

16. **[중간] 시간 측정 방법이 입력부터 실제 바퀴까지의 지연을 입증하지 못한다.**  
    **근거:** [기획서:36](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:36), [기획서:41](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:41), [기획서:44](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:44), [서버:76](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:76).  
    **시나리오:** 서버 수신 시각으로는 손을 뗀 시각과 물리적 정지를 알 수 없다. 30fps 영상도 입력과 바퀴가 같은 시간축에 보여야 하며 약 33ms의 프레임 간격 때문에 경계값 판정에 오차가 있다. 카메라 지연 1초를 눈대중으로 판정하는 방식은 재현하기 어렵다.  
    **고칠 방법:** 시작·종료 사건과 허용 오차를 정의하고 입력·바퀴를 함께 촬영하며, 카메라 지연은 실물 시계와 수신 화면을 함께 기록해 측정한다.

17. **[중간] 반복 횟수와 시험 조건이 안전 실패를 드러내기에 부족하다.**  
    **근거:** [기획서:36](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:36), [기획서:38](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:38), [기획서:41](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:41).  
    **시나리오:** 10회·3회 성공만으로 간헐적인 요청 역전이나 경쟁 조건을 배제할 수 없다. 카메라와 휴대폰 항목은 횟수도 미정이다. IME 전환·키 반복·키를 누른 채 창 전환·화면 잠금·터치 취소·두 버튼 동시 누름의 합격 기준도 없다. `e.code` 사용만으로 모든 IME 환경을 검증한 것은 아니다. [키 이벤트 참고](https://developer.mozilla.org/en-US/docs/Web/API/Element/keydown_event)  
    **고칠 방법:** 실제 사용할 기기·브라우저별로 위 사건과 영상 부하·지연·요청 역전 조건을 포함하고 반복 횟수와 실패 허용치를 정한다.

18. **[중간] ‘와이파이 끊기’ 시험이 데드맨 시험이 되도록 정의되지 않았다.**  
    **근거:** [기획서:38](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:38), [기획서:86](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:86), [화면:187](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:187).  
    **시나리오:** 와이파이 설정 화면으로 이동하면서 blur·visibilitychange가 먼저 정지 요청을 보내면, 실제로는 브라우저의 정상 정지를 시험하고도 데드맨 성공으로 기록할 수 있다. 정지 상태에서 연결을 끊어도 같은 문제가 생긴다.  
    **고칠 방법:** 이동 중 정지 요청이 전달되지 않도록 통신을 차단하고, 서버의 마지막 이동 수신부터 실제 정지까지와 연결 복구 후 재출발 여부를 기록한다.

19. **[중간] 1단계 결과 표가 시험하지 않은 사건까지 확인한 것처럼 적혀 있다.**  
    **근거:** [기획서:91](C:/Users/박시현/Desktop/raspbot/specs/webabb.md:91), [서버:73](C:/Users/박시현/Desktop/raspbot/missions/webabb.py:73), [화면:189](C:/Users/박시현/Desktop/raspbot/missions/webabb/index.html:189).  
    **시나리오:** PC의 직접 요청으로 `/api/release`를 시험해도 실제 창 닫기의 `sendBeacon` 전달은 검증되지 않는다. `--dry --no-camera`는 모터 통신·바퀴 정지·영상 부하를 모두 건너뛴다. 결과의 ‘화면 정상’, ‘창 닫으면 자리 비움’, ‘0.43초 데드맨 정지’는 각각 브라우저 동작과 물리적 정지를 입증하지 못한다.  
    **고칠 방법:** 결과를 ‘직접 HTTP 응답·내부 상태 확인’으로 한정하고 브라우저·휴대폰·실제 바퀴·카메라 부하 검증을 별도 합격 항목으로 남긴다.

**이대로 진행해도 되는가: 아니오.** 정지 후 재출발과 정지 실패를 방치하는 경로를 먼저 막고, 독립된 정지 수단과 실제 바퀴 검증을 갖춰야 한다.