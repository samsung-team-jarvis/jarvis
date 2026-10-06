# Decision: 가상 주방은 연결 토픽으로 붙고, 보드의 kitchen_gw가 버스로 옮긴다

## Status
- Accepted ([open-questions](./open-questions.md) Q-12·13 답. [Unity 결정](./2026-10-05-unity-virtual-kitchen.md)의 "HW-14에서 정한다"를 채운다)

## Date
- 2026-10-06

## Context
- 가상 주방은 Unity이고 MQTT 클라이언트로 보드의 브로커에 접속한다 ([decision](./2026-10-05-unity-virtual-kitchen.md)).
- 버스의 모든 메시지는 봉투(`ts`·`mono`·`session_id`)를 가진다. **시각은 보드 한 대의 시계로 찍는다**는 규칙이 있고 ([overview](../architecture/overview.md) §5), 지연 분해(`bench/latency.py`)는 `control/command`와 `control/result`의 `mono` 차이로 왕복 시간을 낸다.
- Unity 담당은 Unity·C#을 처음 배운다. 가상 주방 쪽에서 해야 할 일이 적을수록 좋다.
- Unity가 없을 때도 보드 쪽 서비스(안전 판단, 상황 인식)를 개발·테스트할 수 있어야 한다.

## Options
- Option A: Unity가 버스 토픽(`control/command` 구독, `control/result`·`sensor/reading` 발행)을 봉투 형식 그대로 쓴다
- Option B: Unity는 봉투 없는 짧은 JSON을 `kitchen/*` 연결 토픽으로 주고받고, 보드의 `kitchen_gw`가 버스 메시지로 옮긴다
- Option C: MQTT 대신 HTTP·WebSocket 전용 통신을 새로 만든다

## Decision
- 선택한 안: **B** (제안: 이현종. 이 PR의 머지로 확정)

| 항목 | 결정 |
|---|---|
| 연결 토픽 | `kitchen/cmd` · `kitchen/ack` · `kitchen/temp` · `kitchen/heartbeat` · `kitchen/state` · `kitchen/frame` ([interfaces](../architecture/interfaces.md) §4.2) |
| 재시도 | 0.5초 안에 확인이 없으면 같은 `seq`로 한 번 다시 보낸다. 가상 주방은 같은 `seq`를 두 번 실행하지 않는다 |
| 캡처 화면 | JPEG 640×360, 1초에 4장. `vision_svc`가 직접 구독한다 (버스 봉투로 옮기지 않는다) |
| 생존 신호 | 보드가 1초에 한 번. 3초 끊기면 가상 주방이 가열 장치를 끈다 |
| 가상 온도 | 1초마다 목표 온도와의 차이의 5%씩 이동. 목표 25·120·180·270°C. 265°C에 닿으면 가상 주방이 스스로 끈다 |
| 전류 | 가상 주방에 없다 → `sensor/reading`의 `current_a`를 선택 필드로 |

- 선택 이유:
  - A는 버스 메시지의 `ts`·`mono`가 가상 주방 PC의 시계로 찍힌다. 왕복 지연이 서로 다른 두 시계의 차이가 되어 측정이 깨진다. B는 `kitchen_gw`가 받은 순간에 보드 시계로 찍는다.
  - B는 Unity가 봉투·`session_id`·재시도 계산을 몰라도 된다. 받은 명령대로 장치를 바꾸고 확인만 보내면 된다.
  - B는 연결 토픽만 맞추면 되므로, Unity 대신 같은 토픽을 쓰는 가짜 가상 주방으로 보드 쪽을 먼저 개발할 수 있다 (HW-17).
  - C는 이미 있는 브로커와 따로 통신을 하나 더 만들게 된다.
- 캡처 화면만 예외로 봉투 없이 직접 받는다: 1초에 4장의 이미지를 JSON 봉투에 넣으면 크기와 변환 시간이 늘어난다. `vision_svc`가 받은 시각을 찍어 `vision/objects`를 낸다.

## Consequences
- 장점: 시각 규칙이 지켜지고 지연 측정이 그대로 동작한다. Unity 쪽 일이 줄어든다. 보드 쪽은 Unity 없이 개발할 수 있다.
- 단점:
  - 보드에 서비스가 하나 더 생긴다 (`kitchen_gw`). 메시지가 한 번 더 거쳐 가므로 왕복 시간에 `kitchen_gw`의 처리 시간이 들어간다 (HW-21에서 측정).
  - 가상 온도와 자체 안전장치의 수치(5%, 270°C, 265°C, 3초)는 **시연용 설계값**이다. 실제 조리 온도를 잰 값이 아니다.
  - 브로커가 같은 네트워크의 접속을 받도록 설정해야 한다. 인증 없이 여는 설정이라 인터넷에 연결된 망에서는 쓰지 않는다.
- 영향: [interfaces](../architecture/interfaces.md) §2·§4, `common/kitchen_link.py`, `common/messages.py`(`sensor/reading`), PLAN HW-16~21, [recipe](../../recipes/unity-kitchen-link.md)

## Verification
- 이 PR: 연결 메시지 검사와 온도 규칙의 단위 테스트 (Mac). 문서의 예시가 코드 검사를 통과하는지 테스트로 확인
- **미검증**: Unity와 실제로 주고받기(HW-16), 캡처 화면 전송 속도(HW-20), 브로커 설정(보드)

## Revisit
- 640×360 · 1초에 4장 전송이 네트워크나 보드에 부담이 될 때 → 크기·빈도 조정
- 0.5초 안에 확인이 자주 안 올 때 → 타임아웃·재시도 횟수 조정 (HW-22)
- 온도 규칙이 시연에 맞지 않을 때 (너무 빠르거나 느림)
