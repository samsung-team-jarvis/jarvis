# webview — 시연 화면 (UI-03)

보드에서 일어나는 일(들은 말 → 명령 해석 → Safety Guard → 가상 주방 → 응답)과 응답 시간을 브라우저에 실시간으로 보여 준다 (PLAN UI-03, #174). Unity 가상 주방 화면(UI-02)이 준비되지 않았을 때의 시연 대안이고, 함께 띄워도 된다. 장치는 제어하지 않는다. 화면 위의 버튼으로 마이크·스피커 테스트를 요청하고 기록을 비울 수 있다 (UI-04, #186).

```text
stt/text · llm/function_call · guard/decision · control/result   ─┐  한 번의 말 = 턴 하나
device/state · fusion/state · system/heartbeat                    ─┼▶ Feed ─▶ HTTP  /            화면
                                                                    ┘           /view.json   지금 정보
                                                                                /events      실시간 (SSE)
```

## 실행

```bash
python -m services.webview                # http://0.0.0.0:8090 — 같은 공유기의 PC에서 http://<보드 IP>:8090
python -m services.webview --port 9000
```

`scripts/launch_demo.yaml`·`scripts/launch.yaml`에 들어 있다. 파이썬 표준 라이브러리만 쓴다 (새 의존성 없음).

## 동작

- **턴**: 호출어가 있는 말, 긴급어, 물어본 질문("결제할까요?")에 대한 대답이 새 턴을 연다. 15초 안에 온 `llm/function_call`·`guard/decision`·`control/result`를 그 턴에 붙인다. 호출어 없는 다른 말은 보이지 않는다.
- **긴급 빠른 경로**(`reason` "긴급 빠른 경로")와 **자동 차단**(`reason` "자동 차단: …")은 LLM을 거치지 않았다고 따로 보인다. 빠른 경로 뒤에 늦게 온 LLM 결과는 붙이지 않는다.
- **응답 시간**: 말 끝 → 받아쓰기 발행(`stt/text`의 `mono − speech_end_mono`) · LLM 생성(`gen_ms`) · 가상 주방 확인(`rtt_ms`) · 말 끝 → 장치 확인(`control/result`의 `mono − speech_end_mono`). 모두 실행 기기의 단조 시계 하나로 잰다 ([bench/latency.py](../../bench/latency.py)와 같은 정의).
- 응답·경고 문장은 `audio_svc.responses`를 그대로 쓴다 — 화면 글자와 음성이 같은 말을 한다.
- `fusion/state`가 3초 넘게 없으면 상태·온도를 비우고 "상태 모름"으로 보인다 (Safety Guard `STATE_STALE_S`와 같은 기준).
- 화면 머리에 실행 기기를 적는다. 보드면 device tree 모델명, 아니면 "참고값 (보드 아님)".
- `/events`는 바뀔 때 바로, 바뀐 게 없어도 1초마다 지금 정보를 보낸다.
- **버튼 (UI-04)**: `POST /reset`은 현재 턴과 최근 기록을 비운다 (서비스를 다시 띄우지 않는다. 장치·상황 인식 상태는 버스에서 다시 오므로 둔다). `POST /test/mic`·`/test/speaker`는 `audio/test`를 낸다 — 마이크·스피커는 audio_svc가 쥐고 있어 웹 화면은 요청만 보낸다. 마이크 테스트는 audio_svc가 5초 동안 보내는 `audio/level`로 음량 막대를 그리고, 최대 음량이 -35 dBFS 이상이면 "소리 들어옴"으로 보인다 (근거: 보드 USB 마이크 말소리 -11~-34 dBFS, 잡음 -38~-60 dBFS). audio_svc가 꺼져 있으면 테스트 버튼을 막는다.

## Spec

| 항목 | 내용 |
|---|---|
| 입력 | `stt/text`, `llm/function_call`, `guard/decision`, `control/result`, `device/state`, `fusion/state`, `system/heartbeat`, `audio/level` · HTTP `POST /reset`·`/test/mic`·`/test/speaker` |
| 출력 | HTTP `/`·`/view.json`·`/events` · 버스에는 `system/heartbeat`와 버튼을 눌렀을 때의 `audio/test` |
| 설정 | `--bus`, `--host`(기본 0.0.0.0), `--port`(기본 8090), `--session` |
| 자원 | CPU 무시할 수준, 모델 없음 |
| 이 서비스가 멈추면 | 화면만 멈춘다. 판정·제어·안전에는 영향 없음 |

## 확인 기록

| 날짜 | 장소 | 확인한 것 |
|---|---|---|
| 2026-11-23 | Mac, MQTT(Docker mosquitto) | `tests/webview` 10개. 시연 구성(가짜 가상 주방, 비전 제외)에 합성 음성 wav 3명령: 후드 켜기 턴(말 끝 → 장치 확인 1,323 ms), 타이머, 긴급 빠른 경로(416 ms)가 화면에 바로 바뀜 — **Mac 참고값**. 보드는 미검증 (다음 연결 때) |
