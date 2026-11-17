# Decision: Safety Guard의 State 만료 — 끊긴 fusion/state를 믿지 않는다

## Status
- Accepted

## Date
- 2026-11-16

## Context
- Safety Guard는 `fusion/state`의 마지막 값을 계속 썼다. `fusion_svc`가 멈추면 마지막 State가 `COOKING`인 채로 남아, 그 뒤 실제로 과열·방치가 되어도 화구 켜기·세기 올림을 허용한다. FUS-09 자동 차단도 `fusion/state`의 근거로만 동작해 같이 멈춘다 (#144 Risk).
- 가상 주방의 생존 신호 끊김 차단(L0)은 `kitchen_gw`의 생존 신호가 기준이라, `fusion_svc`만 멈춘 경우는 잡지 못한다.
- `fusion/state`는 1초마다 온다 (FUS-08). 음성 응답은 5초 넘게 끊기면 "상태를 알 수 없어요"라고 답한다 (#148).

## Options
- 만료 시간: (A) 3초 (발행 주기의 3배) / (B) 5초 (음성 응답과 같게)
- 끊긴 동안 이미 켜진 가열 장치: (A) 끄지 않고, 새로 켜거나 세기를 바꾸는 명령만 거부 + 로그 경고 / (B) 자동으로 끈다

## Decision
- 선택한 안: 만료 A(3초), 켜진 장치 A (결정: 최지환, #151)
- `fusion/state`를 받은 적이 있는데 3초 넘게 새 값이 없으면, 마지막 State와 상관없이 가열 장치 켜기·세기 바꾸기를 거부한다 (이유: "상황 인식이 끊겨서 지금은 켤 수 없어요."). 끄기·긴급 정지·그 밖의 명령은 그대로 허용한다. 새 `fusion/state`가 오면 바로 원래대로 판정한다.
- 개발용 가정 상태(`--assume-state`)는 `fusion_svc` 없이 쓰는 것이라 만료시키지 않는다. `fusion/state`를 한 번 받은 뒤부터 만료를 본다.
- 선택 이유:
  - 끊긴 동안에는 실제로 위험한지 알 근거가 없다. 근거 없이 끄면 정상 조리를 끄는 오탐이 되고, 판단을 근거로만 한다는 원칙(안전 3계층)에서도 벗어난다.
  - 실제 과열·방치 차단은 `fusion/state`가 돌아오면 FUS-09가 다시 맡고, 보드 전체가 멈추면 L0가 맡는다. FUS-12는 그 사이에 Guard가 오래된 State로 가열을 허용하는 공백만 막는다.

## Consequences
- 장점: `fusion_svc`가 멈춰도 위험할 수 있는 명령(가열 켜기·올림)은 나가지 않는다.
- 단점: 끊긴 동안 이미 켜진 가열 장치는 그대로 켜져 있다 (자동 차단도 멈춤). 가상 주방의 265°C 자체 차단(L0)이 마지막 안전장치다.
- 영향: [`safety_guard`](../../services/safety_guard/README.md) (`service.py`·`rules.py`), PLAN FUS-12

## Verification
- `tests/safety_guard`: 끊긴 뒤 켜기·세기 거부, 끄기·긴급 정지 허용, 다시 받으면 회복, 가정 상태는 만료되지 않음 (Windows 노트북, `memory://`).
- MQTT·보드·가상 주방에서 `fusion_svc`를 실제로 멈춰 보는 확인은 하지 않았다.

## Revisit
- 시연·녹화에서 `fusion_svc`가 멈추는 일이 생기거나, 끊긴 동안 켜진 장치를 끄지 않는 것이 문제가 될 때
