# Decision: 주방 상태(State) 판정 기준 — 온도 구간·방치 시간·긴급 정지 해제

## Status
- Accepted

## Date
- 2026-11-09

## Context
- interfaces §2.3의 State 6개(`IDLE, PREHEAT, COOKING, UNATTENDED, DANGER, SAFE_STOP`)는 정했지만 바뀌는 조건은 FUS-05로 남겨 두었다. 주의·위험 온도는 200°C·240°C가 후보였다 (§4.5).
- 정답 State가 있어야 FUS-07(단일 조건 Baseline)·FUS-08(State Machine)의 State F1과 위험 미탐율을 계산할 수 있다.
- Safety Guard는 `UNATTENDED`·`DANGER`·`SAFE_STOP`에서 가열 장치를 켜거나 세기를 바꾸는 명령을 거부한다 (FUS-03). 그래서 `SAFE_STOP`이 풀리는 조건이 없으면 다시 조리할 수 없다.
- 가상 온도 규칙(§4.5)으로 계산하면 세기 3으로 켰을 때 200°C까지 약 25초, 240°C까지 약 41초, 가상 주방이 스스로 끄는 265°C(L0)까지 약 76초가 걸린다. 실제 조리 온도를 잰 값이 아니고 시연용 설계값이다.

## Options
- 온도 구간: (A) 주의 200 · 위험 240 / (B) 주의 220 · 위험 250 (265°C 자체 차단까지 여유가 적다) / (C) 주의 180 · 위험 230 (세기 2의 목표 180°C에서 계속 주의가 뜬다)
- 방치 시간 (가열 장치가 켜진 채 사람이 없는 시간): (A) 30초 / (B) 15초 (손님 응대 한 번에도 방치) / (C) 60초 (시연에서 기다리기 길다)
- `SAFE_STOP` 해제: (A) 가열 장치가 모두 꺼져 있고 모두 100°C 아래로 식으면 / (B) 정해진 시간 뒤 / (C) 사람이 해제를 말할 때 (새 Action 필요 — 스키마·LLM 데이터 변경)

## Decision
- 선택한 안: 온도 A, 방치 A, 해제 A (결정: 최지환)
- 판정 규칙 (1초마다, 위에서부터 먼저 맞는 것):

  | 우선 | State | 들어가는 조건 | 나오는 조건 |
  |---|---|---|---|
  | 1 | `SAFE_STOP` | 긴급 정지(FUS-04) 또는 가상 주방의 자체 차단(§4.4 `safe_stop`) | 가열 장치가 모두 꺼져 있고 모두 **100°C** 아래 |
  | 2 | `DANGER` | 가열 장치 하나라도 **240°C** 이상 | 모두 **230°C** 아래 (경계에서 상태가 깜빡이지 않게 10°C 차이를 둔다) |
  | 3 | `UNATTENDED` | 가열 장치가 켜진 채 사람(`person`)이 **30초** 연속 없음 — 켜진 때부터 센다 | 사람이 보이거나 가열 장치가 모두 꺼짐 |
  | 4 | `COOKING` | 켜진 가열 장치 중 하나라도 **100°C** 이상 | |
  | 5 | `PREHEAT` | 가열 장치가 켜져 있고 모두 100°C 아래 | |
  | 6 | `IDLE` | 가열 장치가 모두 꺼짐 (식는 중이어도) | |

- `risk`(`fusion/state`): `DANGER`·`UNATTENDED`는 `danger`. 아니면 가열 장치 하나라도 **200°C** 이상이거나 켜진 채 사람이 **10초** 이상 없으면 `warn`. 그 밖은 `none`.
- 상태는 주방 전체에 하나다. 가열 장치가 여러 개면 가장 위험한 장치를 기준으로 한다.
- 선택 이유:
  - 200 → 240 → 265가 세기 3 기준 약 15초·35초 간격이라 주의 → 위험 → 자체 차단이 시연에서 차례로 보인다.
  - 30초면 잠깐 카운터에 다녀오는 일은 방치로 보지 않고, 시연에서도 기다릴 만하다. 10초부터 주의를 띄워 미리 알린다.
  - 100°C는 예열/조리를 나누는 기준과 같아서 기준값이 하나 줄어든다. 240°C에서 끄면 약 20초 뒤 풀린다.

## Consequences
- 장점: 정답 State를 같은 규칙으로 계산할 수 있다 (시나리오 26개의 `expected`, [simulator](../../services/simulator/README.md)). FUS-08은 이 표를 구현한다.
- 단점: 정답과 State Machine이 같은 규칙에서 나오므로, 시나리오 F1은 "규칙을 맞게 구현했는가"를 본다. 실제 상황을 잘 판단하는지는 가상 주방 녹화(FUS-10)로 본다.
- 열린 문제 (FUS-08에서 정함): 보드가 "가열 장치가 켜졌다"와 "가상 주방이 스스로 껐다(`safe_stop`)"를 어디서 아는가. `kitchen/state`는 지금 버스로 옮겨지지 않는다 (`kitchen_gw`는 온도만 `sensor/reading`으로 옮긴다). → 2026-11-11 `kitchen_gw`가 `kitchen/state`를 버스 `device/state`로 옮기기로 정했다 (합의: 이현종, #139).
- 영향: [interfaces](../architecture/interfaces.md) §2.3·§4.5, [simulator](../../services/simulator/README.md), [`safety_guard`](../../services/safety_guard/README.md) (규칙 변경 없음), PLAN FUS-05·07·08·09

## Verification
- `tests/simulator`: 시나리오 26개가 모두 읽히고 규격에 맞는 메시지를 낸다. 정답 State는 0초 `IDLE`로 시작한다. 가열 장치 온도는 `common.kitchen_link.next_temperature`와 같고, 265°C에서 스스로 꺼진다.
- `tests/simulator/test_expected.py` (2026-11-11, #139): 위 표를 시나리오 시간표에서 바로 다시 계산해 26개의 `expected`와 1초마다 비교한다 — 정답을 만든 규칙. State Machine(`fusion_svc`)과 따로 구현했다.
- 실제 가상 주방(Unity)과 보드에서는 미검증이다.

## Revisit
- 가상 주방(HW-19)의 온도 변화가 시연에서 너무 빠르거나 느릴 때
- 사람 감지(`person`)가 가상 주방 화면에서 자주 끊겨 방치 오탐이 날 때 (`unattended_flicker` 시나리오)
- State Machine(FUS-08)이나 가상 주방 녹화(FUS-10)에서 위험 미탐이 나올 때
