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
| `to_ack` | 제어 명령 → 가상 주방의 결과 확인 (왕복 포함) | `control/result.mono − control/command.mono` |
| `e2e` | 발화 끝 → 녹화된 마지막 단계 | |

- **연결 방법**: 메시지에 상관관계 ID가 없어서, 같은 `session_id` 안에서 시간 순으로 이어 붙인다 (`control/result`만 `seq`로 맞춘다). 그래서 다른 메시지를 받아 만든 메시지는 원래 `session_id`를 이어 써야 한다 ([interfaces](../docs/architecture/interfaces.md) §1). 한 세션에서 발화가 겹치면(앞 명령 처리 중 다음 발화) 잘못 이어질 수 있다.
- **시각**: `mono`는 서비스가 발행할 때 찍은 `time.monotonic()`. 같은 기기의 단조 시계라 프로세스가 달라도 뺄 수 있다. 다른 기기(가상 주방 PC)의 시각은 쓰지 않는다.
- **`speech_end_mono`는 VAD 구간의 끝**이라 실제로 말이 끝난 순간보다 조금 늦다 → `vad_wait`·`e2e`는 실제보다 약간 작게 나온다.
- 아직 없는 서비스의 구간은 `-`로 비워 둔다. Guard·kitchen_gw가 생기면 같은 명령으로 전 구간이 나온다.

## stt_eval.py — STT 평가 (STT-06)

STT 매니페스트로 CER·RTF·호출어 인식·STT→Action 정확도를 소음·마이크·화자별로 낸다. 매니페스트 형식과 지표 정의는 [STT 평가 recipe](../recipes/stt-eval.md) §3·§4.

```bash
python -m bench.stt_eval data/stt/manifest.csv --split test --csv out.csv
```

## record_stt.py — STT 테스트 세트 녹음 (STT-05)

대본 문장을 하나씩 보여 주고 Enter로 녹음 → wav + 매니페스트. 팀원용 절차는 [STT 테스트 세트 녹음](../recipes/stt-recording.md).

```bash
python -m bench.record_stt --speaker spk02 --noise quiet --mic pin
```

## llm_eval.py — 명령 해석 평가 (LLM-06 · FUS-06)

LLM 분할의 test(일반 + Hard Negative)로 규칙 파서·기본 모델의 명령 해석을 잰다. 데이터: [training/llm](../training/llm/README.md) — 기본은 데이터 v2(장치 8종 · 함수 14개).

```bash
python -m bench.llm_eval --engine rule                                          # 규칙 파서
python -m bench.llm_eval --engine rule --split val --csv val.csv                # 오류 분석은 val로
.venv-llm/bin/python -m bench.llm_eval --engine hf --model Qwen/Qwen3-0.6B      # 기본 모델 + 프롬프트
python -m bench.llm_eval --engine rule --data v1                                # 데이터 v1 (장치 3종 고정본)
.venv-llm/bin/python -m bench.llm_eval --engine hf --finetuned --model runs/llm/<이름>   # 학습한 모델 (짧은 지시문, 예시 없음)
```

| 지표 | 정의 |
|---|---|
| Action Acc | action이 정답과 같은 비율 (형식이 틀린 출력은 오답) |
| Entity Acc | 파라미터까지 모두 같은 비율 |
| Valid Rate | 출력이 함수 토큰 형식·스키마를 통과한 비율 |
| Unsafe (Guard 전) | Hard Negative 중 Guard가 거절해야 할 위험 명령(`expect_guard: REJECT`)에 켜기·세기 올림을 낸 비율 — LLM은 말 그대로 해석하므로 설계상 높다 |

- HF 엔진: 함수 토큰을 설명하는 시스템 프롬프트(지시문 v0.2) + **train에서만** 고른 few-shot 17개(되묻기를 뺀 함수 13개에 하나씩 + 되묻기 2개·대명사·장치 타이머), greedy, `<jarvis_end>`에서 자른다. HF 모델은 분리된 가상환경(`.venv-llm`)에서 돌린다.
- 지시문은 v0.2 하나뿐이다. 2026-10-02의 v1 수치는 지시문 v0.1(함수 10개 · few-shot 13개)로 잰 것이라, 지금 `--data v1`로 모델을 다시 재도 같은 조건이 아니다 (규칙 파서는 지시문을 쓰지 않는다).
