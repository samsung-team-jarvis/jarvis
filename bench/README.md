# bench — 측정 스크립트

결과는 [METRICS](../docs/METRICS.md)에 기록한다 (절차: [experiment](../docs/workflows/experiment.md)).

## latency.py — 지연 분해 (INFRA-06)

recorder 녹화에서 호출어가 있는 발화 한 건마다 구간별 지연(ms)을 계산한다.

```bash
python -m services.recorder                            # 녹화하면서 서비스를 돌린 뒤
python -m bench.latency data/sessions/<세션>.jsonl [...] --csv out.csv
```

출력: 발화별 구간 표, 구간별 n·평균·p50·p95·최대 (Markdown 표 — PR·METRICS에 붙여 넣기 좋게).

| 구간 | 의미 | 계산 |
|---|---|---|
| `vad_wait` | 발화 끝 → STT 시작. 대부분 VAD가 "말이 끝났다"고 판단하는 대기(`min_silence`) | `stt/text.mono − speech_end_mono − stt_ms` |
| `stt` | STT 인식 | `stt/text.stt_ms` |
| `to_call` | stt/text 발행 → 명령 발행 (버스 전달 + 파서/LLM) | `llm/function_call.mono − stt/text.mono` |
| `to_guard` | 명령 → Safety Guard 판정 | `guard/decision.mono − llm/function_call.mono` |
| `to_command` | 판정 → 제어 명령 | `control/command.mono − guard/decision.mono` |
| `to_ack` | 제어 명령 → ESP32 ACK (BLE 왕복 포함) | `control/result.mono − control/command.mono` |
| `e2e` | 발화 끝 → 녹화된 마지막 단계 | |

- **연결 방법**: 메시지에 상관관계 ID가 없어서, 같은 `session_id` 안에서 시간 순으로 이어 붙인다 (`control/result`만 `seq`로 맞춘다). 그래서 다른 메시지를 받아 만든 메시지는 원래 `session_id`를 이어 써야 한다 ([interfaces](../docs/architecture/interfaces.md) §1). 한 세션에서 발화가 겹치면(앞 명령 처리 중 다음 발화) 잘못 이어질 수 있다.
- **시각**: `mono`는 서비스가 발행할 때 찍은 `time.monotonic()`. 같은 기기의 단조 시계라 프로세스가 달라도 뺄 수 있다. ESP32 시각은 쓰지 않는다.
- **`speech_end_mono`는 VAD 구간의 끝**이라 실제로 말이 끝난 순간보다 조금 늦다 → `vad_wait`·`e2e`는 실제보다 약간 작게 나온다.
- 아직 없는 서비스의 구간은 `-`로 비워 둔다. Guard·ble_gw가 생기면 같은 명령으로 전 구간이 나온다.
