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
| 역할 | 시나리오 파일의 시간표대로 `sensor/reading`·`device/state`·`vision/objects`·`stt/text`·`system/heartbeat` 발행. 시나리오의 정답 State(`expected`)는 상황 인식 평가(FUS-07·08)용으로 읽기만 하고 발행하지 않는다 |
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

heaters:                       # 가열 장치별 세기 시간표 [시각, 세기 0~3] — 온도는 아래 규칙으로 계산
  burner_1: [[0, 0], [5, 3], [60, 0]]
  fryer: [[0, 0], [10, 2]]     # 적지 않은 가열 장치는 꺼진 채로 온도만 보낸다

sensor:                        # heaters 대신 온도를 직접 적을 때 (둘은 함께 쓸 수 없다)
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

expected:                      # 정답 State [시각, State] — 0초부터, 다음 항목 전까지 (발행하지 않음)
  - [0, IDLE]
  - [5, PREHEAT]
```

- `heaters`: 가상 주방과 같은 온도를 낸다 — 가열 장치 3개(`burner_1`·`burner_2`·`fryer`) 모두 1초에 한 번 `sensor/reading`, 실온에서 시작해 `common.kitchen_link.next_temperature`로 세기의 목표 온도에 다가가고, 켜진 장치가 265°C에 닿으면 시간표의 다음 세기 항목까지 꺼진다 ([interfaces](../../docs/architecture/interfaces.md) §4.4·§4.5). 세기 시간표는 "명령이 실행된 결과"다 — 시나리오의 발화와 맞춰 적는다 (Guard가 거부할 명령이면 세기를 바꾸지 않는다). 시간표는 가상 주방이 보낼 장치 상태(`device/state` — 가열 장치 3개의 `on`·`level`, 265°C 자체 차단이면 `safe_stop: true`)로 나간다: 바뀔 때와 5초마다, 자체 차단은 265°C를 넘은 온도가 나가는 시각에 (#139).
- `expected`: [State 판정 기준](../../docs/decisions/2026-11-09-state-rules.md)으로 정한 정답. 시각 `t`의 정답은 `scenario.expected_at(sc, t)`. 판정 기준으로 다시 계산해 비교하는 테스트가 `tests/simulator/test_expected.py`다 — 기준이나 시나리오를 고치면 `expected`도 같이 고친다.
- `heaters`로 온도를 내는 시나리오는 `kitchen_gw`·가짜 가상 주방과 함께 띄우지 않는다 (같은 `sensor/reading`·`device/state`를 두 곳에서 낸다).
- 비전 객체의 `conf`는 0.9, `bbox`는 고정값, 처리 시간(`*_ms`)은 0이다. 상황 판단 로직 개발용이라 위치·신뢰도는 의미가 없다.
- 가상 주방(메타버스)이 연결되기 전에 그 자리를 대신한다 — 같은 토픽(`sensor/reading` 등)을 내므로 서비스는 구분하지 못한다. `device_id`의 `esp32-1`은 이전 계획의 이름이며 값일 뿐이다 (HW-14에서 정리).
- 시나리오 값은 **개발용 가상 값**이다 (측정값 아님).

## 시나리오 (FUS-05, 26개)

정답 State의 흐름은 각 파일의 `expected`에 있다. 사람은 `person`(조리 구역에 사람 있음)으로만 표현한다 ([vision decision](../../docs/decisions/2026-10-29-vision-pretrained-person.md)).

| 종류 | 파일 (`scenarios/*.yaml`) | 상황 |
|---|---|---|
| 정상 | `normal_cooking` | 1번 화구 세기 2로 조리, 후드·타이머 명령, 호출어 없는 혼잣말 |
| 정상 | `normal_two_burners` | 화구 두 개를 시간차로 사용 |
| 정상 | `normal_fryer` | 튀김기 세기 2, 타이머로 꺼짐 |
| 정상 | `normal_simmer` | 약불(세기 1) — 예열이 30초 정도로 길다 |
| 정상 | `normal_short_absence` | 조리 중 20초 자리 비움 — 방치 아님, 주의만 (경계) |
| 정상 | `normal_idle` | 가열 없음, 조명·음악만, 사람이 오감 — 사람 없음만으로는 방치 아님 |
| 정상 | `normal_off_while_hot` | 센 불로 20초 볶고 끔 — 식는 동안 IDLE |
| 정상 | `normal_warn_peak` | 약 217°C까지 올라 주의, 중불로 낮춤 |
| 과열 | `overheat` | 센 불 유지 → 위험, "1번 불 더 세게"(Guard 거부), 265°C 자체 차단 → `SAFE_STOP` |
| 과열 | `overheat_turn_off` | 위험 → "1번 불 꺼줘" → 230°C 아래에서 해제 |
| 과열 | `overheat_emergency` | 화구 2개 중 1번 과열 → "자비스 멈춰" → `SAFE_STOP` → 식으면 IDLE |
| 과열 | `overheat_bare_stop` | 호출어 없는 "멈춰!"로 긴급 정지 |
| 과열 | `overheat_fryer` | 튀김기 과열, "약하게"는 거부되고 "꺼 줘"로 끔 |
| 과열 | `overheat_second_burner` | 두 화구 중 2번만 과열 → 2번만 끄고 1번으로 계속 조리 |
| 과열 | `overheat_near_miss` | 약 229°C에서 중불로 낮춰 위험까지 가지 않음 (경계) |
| 과열 | `overheat_restart` | 위험에서 끄고, 식은 뒤 다시 켜서 조리 |
| 방치 | `unattended` | 화구 켠 채 사람이 사라지고 돌아오지 않음 |
| 방치 | `unattended_returns` | 방치 판정 뒤 사람이 돌아와 다시 조리 |
| 방치 | `unattended_fryer` | 튀김기를 켜 둔 채 자리 비움 |
| 방치 | `unattended_voice_off` | 방치 중 화면 밖에서 "불 꺼줘" |
| 방치 | `unattended_flicker` | 15초마다 3초씩 사람 감지가 끊김 — 방치 아님 (경계, 오탐 확인) |
| 방치 | `unattended_overheat` | 센 불을 켜 둔 채 자리 비움 → 방치 → 위험 → 자체 차단 |
| 방치 | `unattended_on_from_afar` | 화면 밖에서 말로 켜고 오지 않음 (켜진 때부터 센다) |
| 켜짐 방치 | `forgotten_low_burner` | 약불로 줄여 놓고 잊은 채 떠남 |
| 켜짐 방치 | `forgotten_second_burner` | 1번만 끄고 2번 화구를 잊음 |
| 켜짐 방치 | `forgotten_fryer_closing` | 마감하며 조명·음악은 끄고 튀김기(보온)를 잊음 |

새 시나리오는 이 폴더에 추가하면 `tests/simulator`가 자동으로 형식·규격을 검사한다 (`heaters`·`expected` 필수).
