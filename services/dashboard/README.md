# dashboard — 화면에 겹쳐 띄울 정보 (UI-01)

버스의 상태·들은 말·판단 근거·경고를 모아 가상 주방(Unity)으로 `kitchen/overlay`를 보낸다 (PLAN UI-01, #170). 화면에 그리는 것은 Unity다 (UI-02). 형식: [interfaces](../../docs/architecture/interfaces.md) §4.6 — **Unity 쪽 합의 대기** (제안대로 먼저 만들었다).

```text
fusion/state    ─┐  State·risk·근거(장치별 켜짐·온도, 사람)
device/state    ─┤  상태 확인 응답 문장용
stt/text        ─┼▶ Overlay ─▶ kitchen/overlay (봉투 없는 JSON, 바뀔 때 + 1초마다)
guard/decision  ─┤  응답 문장·판정·이유 (자동 차단 근거 포함)
vision/objects  ─┘  AI가 본 화면 (사람 bbox)
```

## 실행

```bash
python -m services.dashboard              # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.dashboard --print      # 바뀔 때마다 터미널에도 출력 (Unity 없이 로컬 화면 대신)
```

`scripts/launch_demo.yaml`에 들어 있다.

## 동작

- 문장은 `audio_svc.responses`를 그대로 쓴다 (`reply_for_decision`, 위험 경고, 상태 끊김 안내) — 화면 글자와 음성이 같은 말을 한다.
- 들은 말(호출어가 있는 것만)과 응답은 10초 동안 남긴다. 화면 인식 결과는 1초 지나면 비운다.
- 바뀜 판단에서 인식 결과는 보이는 종류(`cls`)만 본다. conf·bbox는 화면마다 흔들려서, 사람이 나타나거나 사라질 때만 바로 보내고 위치는 1초마다 보낼 때 갱신된다.
- `fusion/state`가 3초 넘게 없으면 `stale: true`로 상태·장치 정보를 비우고 끊김 안내를 띄운다 (Safety Guard FUS-12와 같은 기준).

## Spec

| 항목 | 내용 |
|---|---|
| 입력 | `fusion/state`, `device/state`, `stt/text`, `guard/decision`, `vision/objects` |
| 출력 | 연결 토픽 `kitchen/overlay` (바뀔 때 + 1초마다), `system/heartbeat` 1초 |
| 설정 | `--bus`, `--session`, `--print` |
| 자원 | CPU 무시할 수준, 모델 없음 |
| 이 서비스가 멈추면 | 화면 정보만 멈춘다. 판정·제어·안전에는 영향 없음 (아무것도 제어하지 않는다) |

## 확인 기록

| 날짜 | 장소 | 확인한 것 |
|---|---|---|
| 2026-11-17 | Windows PC, `memory://` | `tests/dashboard`: 상태·장치 표시, 들은 말·응답 10초 유지, 거부 이유·자동 차단 근거, 방치 경고, 상태 끊김·없음, 인식 결과 만료, 발행 주기. Unity는 미검증 (합의 대기) |
