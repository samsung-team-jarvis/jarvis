# fusion_svc — 상황 인식 (State Machine v1)

온도·화면·장치 상태·음성 근거를 묶어 주방 상태(State)를 판정하고 `fusion/state`로 낸다 (PLAN FUS-08, #139). 판정 기준은 [State 판정 기준 decision](../../docs/decisions/2026-11-09-state-rules.md), 메시지 형식은 [interfaces](../../docs/architecture/interfaces.md) §2.3.

```text
device/state     ─┐  가열 장치 켜짐·세기, 가상 주방의 자체 차단 (kitchen_gw)
sensor/reading   ─┤  가열 장치 온도
vision/objects   ─┼▶ StateMachine ─▶ fusion/state {state, prev_state, evidence, risk}
stt/text         ─┤  긴급어 (Safety Guard 빠른 경로와 같은 판단)
guard/decision   ─┘  허용된 EMERGENCY_STOP
```

받는 쪽: `safety_guard`(위험 상태에서 가열 거부), `llm_svc`(LLM context의 `state`), `audio_svc`(`risk`가 오르면 음성 경고).

## 실행

```bash
python -m services.fusion_svc                 # 버스는 JARVIS_BUS (기본 MQTT). State가 바뀔 때마다 출력
python -m bench.fusion_eval --judge fusion --split test   # 버스 없이 simulator 시나리오로 평가
```

Unity 없이 볼 때는 브로커 → `fusion_svc` → `python -m services.simulator services/simulator/scenarios/overheat.yaml` (simulator가 온도·장치 상태·화면·발화를 모두 낸다. 이때 `kitchen_gw`·가짜 가상 주방은 띄우지 않는다). `scripts/launch.yaml`·`launch_demo.yaml`에 들어 있다.

## 판정

`state_machine.py`의 `StateMachine`. 근거는 `update(t, topic, payload)`로만 바뀌고 `state(t)`·`risk(t)`·`evidence(t)`는 읽기만 한다 — 같은 근거와 시각이면 몇 번을 불러도 같은 답이다. 버스·시계와 무관해서 평가 도구(`bench/fusion_eval.py`)가 그대로 쓴다.

| 우선 | State | 이 서비스가 보는 것 |
|---|---|---|
| 1 | `SAFE_STOP` | 긴급 정지 근거, 또는 `device/state`의 `safe_stop`이 `false → true`로 바뀜. 가열 장치가 모두 꺼지고 모두 100°C 아래인 것을 **확인하면** 풀린다 |
| 2 | `DANGER` | 믿을 수 있는 온도 중 240°C 이상 (장치마다 230°C 아래로 내려가야 풀림) |
| 3 | `UNATTENDED` | 가열 장치가 켜진 채 사람이 30초 — 켜진 때와 사람이 안 보이기 시작한 때 중 늦은 때부터 |
| 4 | `COOKING` | 켜진 가열 장치 중 100°C 이상 |
| 5 | `PREHEAT` | 가열 장치가 켜져 있음 |
| 6 | `IDLE` | 가열 장치가 모두 꺼짐 |

- `safe_stop`은 가상 주방이 새 명령을 받을 때까지 `true`로 남는다. 그래서 `true`가 계속 와도 다시 `SAFE_STOP`에 들어가지 않는다.
- 장치 상태를 받기 전에는 모두 꺼진 것으로 본다 (가상 주방은 모두 꺼진 채 시작한다, §4.4).

## 오래된 근거 (stale context)

| 근거 | 믿는 시간 | 끊기면 |
|---|---|---|
| 화면 (`vision/objects`) | 2초 | 사람이 없는 것으로 본다 (마지막 화면부터 방치 시간을 센다) — 카메라가 죽어도 방치를 놓치지 않게. `evidence.person = null` |
| 온도 (`sensor/reading`) | 3초 | 그 장치의 온도를 모른다: `DANGER`·`COOKING` 판정에 쓰지 않고, `SAFE_STOP`을 풀지 않고, 켜져 있으면 `risk`를 `warn`으로 |
| 장치 상태 (`device/state`) | 12초 | 마지막 값을 유지하고 `stale`에 `devices`로 표시만 한다 (바뀔 때마다 오는 메시지라, 끊겼다는 것은 `kitchen_gw`·가상 주방이 멈췄다는 뜻 — 그때는 가상 주방이 생존 신호 끊김으로 가열 장치를 끈다) |

시간 값은 v1 값이다 (화면 2~4장/초, 온도 1초, 장치 상태 5초 주기 기준). 보드·가상 주방에서 써 보고 조정한다.

## Spec

| 항목 | 내용 |
|---|---|
| 입력 | `device/state`, `sensor/reading`, `vision/objects`, `stt/text`, `guard/decision` |
| 출력 | `fusion/state` — State·`risk`가 바뀌면 바로, 아니면 1초마다. `system/heartbeat` 1초마다 |
| 설정 | `--bus`, `--session`, `--quiet`. 판정 기준·근거 만료 시간은 `state_machine.py` 상수 (규격이라 실행 옵션으로 두지 않았다) |
| 자원 | CPU, 모델 없음 |
| 입력이 끊기면 | 위 표. 서비스는 계속 판정한다. 값이 이상한 메시지는 경고만 남기고 버린다 |
| 이 서비스가 멈추면 | `fusion/state`가 끊긴다. Safety Guard는 마지막 State를 계속 쓴다 (만료는 FUS-09에서 검토). 가상 주방의 자체 안전장치(L0)는 그대로 동작한다 |
| 하지 않는 일 | 장치 제어 (`control/command`는 Safety Guard만 낸다), 위험 시 자동 차단 (FUS-09) |

## 확인

- `tests/fusion`: simulator 시나리오 26개 재생 결과가 정답 State(`expected`)와 1초마다 같다, 판정 표의 경계값, 근거 만료, `SAFE_STOP` 진입·해제, 버스 발행(바뀔 때·1초마다), Safety Guard가 `fusion/state`를 받아 화구 켜기를 허용, simulator → 버스 → `fusion_svc` 재생.
- 평가 결과는 [METRICS](../../docs/METRICS.md) (FUS-08). 정답과 같은 규칙이라 "규칙을 맞게 구현했는가"를 본다 — 실제 상황 판단은 가상 주방 녹화(FUS-10)로 본다.
- 2026-11-11 Windows 11 노트북, `memory://` 버스. **MQTT·보드·Unity 미검증** (이 PC에 브로커 없음).
