# simulator — 시나리오 기반 가짜 메시지 생성기

보드·센서·카메라·마이크 없이 다른 서비스를 개발·테스트하기 위해, 시나리오 파일대로 가짜 메시지를 버스에 흘려 준다. (PLAN INFRA-04)

## 실행

```bash
python -m services.simulator services/simulator/scenarios/overheat.yaml                 # 실제 속도, MQTT
python -m services.simulator services/simulator/scenarios/overheat.yaml --speed 10      # 10배속
python -m services.simulator services/simulator/scenarios/overheat.yaml --speed 0 --bus memory://   # 대기 없이 확인
mosquitto_sub -t '#' -v      # 다른 터미널에서 발행되는 메시지 보기 (또는 python -m common.demo sub)
```

## Spec

| 항목 | 내용 |
|---|---|
| 역할 | 시나리오 파일의 시간표대로 `sensor/reading`·`vision/objects`·`stt/text`·`system/heartbeat` 발행 |
| 하지 않는 일 | 판단·제어 (그건 ③ fusion·guard의 일), 실제 장치 입력 |
| 입력 | 시나리오 YAML (아래 형식) |
| 출력 | interfaces.md §2 토픽, `source: "simulator"`, `session_id: sim_<이름>_<시각>` (`--session`으로 지정 가능) |
| 설정 | `--bus`(기본 `JARVIS_BUS`), `--speed`(배속, 0 = 대기 없음), `--session`, `--quiet` |
| 자원 | CPU 무시할 수준, 하드웨어 불필요 |
| 실패 시 | 시나리오 형식이 틀리면 어느 키가 틀렸는지 출력하고 종료(코드 1). 버스 연결 실패 시 종료 |

## 시나리오 형식

```yaml
name: overheat                 # 필수, session_id에 들어감
description: 설명
duration_s: 90                 # 필수, 재생 길이(초)
heartbeat_hz: 1                # system/heartbeat 주기 (기본 1)

sensor:                        # 없으면 센서 메시지를 보내지 않음
  device_id: esp32-1
  hz: 1
  temperature_c:               # [시각, 값] — 사이는 직선 보간, 범위 밖은 끝 값 유지
    - [0, 25]
    - [40, 180]
  current_a:
    - [0, 0.0]
    - [2, 1.5]

vision:                        # 없으면 비전 메시지를 보내지 않음
  fps: 2
  objects:                     # [시각, [클래스...]] — 그 시각부터 다음 항목 전까지 보임
    - [0, [pot, burner_on, person]]
    - [30, [pot, burner_on]]   # 사람이 사라짐

stt:                           # [시각, "발화"] — "자비스"로 시작하면 wake=true (audio_svc와 같은 판정)
  - [20, "자비스 후드 세게 틀어줘"]

category: overheat             # 선택: normal | overheat | unattended | left_on (위험 미탐율을 분류별로 셀 때)
expect:                        # 선택: 정답 State [시각, State] — 0초부터, 그 시각부터 다음 항목 전까지
  - [0, PREHEAT]
  - [41, DANGER]
```

- `category`·`expect`는 발행하지 않는다. 상황 인식(FUS-07·08)의 판정과 비교할 정답이다 (`Scenario.state_at(t)`).

- 비전 객체의 `conf`는 0.9, `bbox`는 고정값, 처리 시간(`*_ms`)은 0이다. 상황 판단 로직 개발용이라 위치·신뢰도는 의미가 없다.
- 가상 주방(메타버스)이 연결되기 전에 그 자리를 대신한다 — 같은 토픽(`sensor/reading` 등)을 내므로 서비스는 구분하지 못한다. `device_id`의 `esp32-1`은 이전 계획의 이름이며 값일 뿐이다 (HW-14에서 정리).
- 시나리오 값은 **개발용 가상 값**이다. State 정답 기준은 [FUS-05 decision](../../docs/decisions/2026-10-09-state-criteria.md).

## 예시 시나리오

| 파일 | 상황 |
|---|---|
| `scenarios/normal_cooking.yaml` | 예열 → 조리 → 불 끔, 음성 명령 2개 + 호출어 없는 혼잣말 |
| `scenarios/overheat.yaml` | 온도가 계속 올라 과열, 과열 중 "불 더 세게" 요청 |
| `scenarios/unattended.yaml` | 화구 켠 채 30초 뒤 사람이 사라짐 |

새 시나리오는 이 폴더(하위 폴더 포함)에 추가하면 `tests/simulator`가 자동으로 형식·규격을 검사한다.

## 온도 시나리오 (FUS-05, `scenarios/temp/`)

정답 State(`expect`)가 붙은 25개. **직접 고치지 않고** [`temp_scenarios.py`](./temp_scenarios.py)의 사건 목록을 고친 뒤 다시 만든다 (테스트가 `--check`로 확인한다).

```bash
python -m services.simulator.temp_scenarios           # 다시 만들기
python -m services.simulator services/simulator/scenarios/temp/t12_overheat_estop.yaml --speed 10
```

| 분류 | 개수 | 내용 |
|---|---|---|
| `normal` | 8 | 중불·약불·센불 후 낮춤·튀김기, 15초 자리 비움, 팬 잠깐 듦, 끄고 식힘, 200°C(주의)까지만 |
| `overheat` | 6 | 센불 방치(265°C에서 가상 주방이 끔), 튀김기, 나중에 센불로, 과열 중 긴급 정지·직접 끔, 자리 비운 사이 과열 |
| `unattended` | 6 | 떠나서 안 돌아옴, 45초 뒤 돌아옴, 튀김기, 약불, 25초씩 두 번(방치 아님), 끄고 떠남(방치 아님) |
| `left_on` | 5 | 팬만 내리고 켜 둠, 빈 화구 켜 놓음, 40초 뒤 팬을 다시 올림(방치 아님), 팬 내리고 떠남, 튀김기 켜 둔 채 떠남 |

- 온도는 가상 주방과 같은 규칙(`common.kitchen_link.next_temperature`)으로 1초씩 계산해 5초 간격 점으로 적었다. 센불(세기 3)로 켜 두면 약 24초에 200°C, 41초에 240°C를 넘고 76초에 265°C에서 가상 주방이 끈다.
- 화면 물체는 `pan`(튀김기는 `fryer_basket`), `burner_on`·`burner_off`(화구만), `person`이다. 가열 장치는 시나리오마다 하나(`burner_1` 또는 `fryer`)다.
