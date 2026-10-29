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

## llm_errors.py — 명령 해석 오류 유형 분류 (LLM-10)

`llm_eval.py --csv`로 만든 예측 CSV를 받아 틀린 예측을 유형별로 센다 (형식 깨짐 · 규칙 위반 · 빠진 값 채움 · 불필요한 되묻기 · 지원 외를 실행 · 지원 외로 거절 · 다른 함수 · 장치 틀림 · 값 틀림, 겹쳐 세는 표시: 대명사 실패 · 긴급 정지 오판 · 틀린 실행). 많이 틀린 가족(템플릿)도 보여 줘서 어느 문장을 보강할지 바로 이어진다. **val로만 쓴다.**

```bash
python -m bench.llm_eval --engine rule --split val --csv rule_val.csv
.venv-llm/bin/python -m bench.llm_eval --engine hf --finetuned --model runs/llm/<이름> --split val --csv lora_val.csv
python -m bench.llm_errors rule_val.csv lora_val.csv     # 나란히 비교 (열 이름 = 파일 이름)
```

## resources.py — 서비스별 CPU·메모리 (BOARD-08)

`-m services.*`로 뜬 프로세스를 1초마다 보고 서비스별 CPU 평균·최대와 메모리(RSS) 최대를 표로 낸다. 서비스를 먼저 띄워 둔다 (런처 등).

```bash
python -m bench.resources --duration 60                  # 60초 (서비스가 모두 끝나면 일찍 멈춤)
python -m bench.resources --duration 60 --csv out.csv    # 1초마다의 값
```

- CPU %는 그 1초 동안 쓴 CPU 시간 ÷ 1초 (100% = 코어 하나). `ps`의 `%cpu`는 Mac·Linux에서 뜻이 달라 쓰지 않고 누적 CPU 시간의 차이로 계산한다 — Mac·보드(Linux) 같은 방식.
- 메모리는 RSS다. mmap한 모델 파일(GGUF 등)과 공유 라이브러리가 들어가 서비스끼리 겹칠 수 있다.

## rehearsal.py — 시연 리허설 (DOC-09)

시연 대본([`rehearsal/demo.yaml`](rehearsal/demo.yaml): 문장 + Safety Guard가 내야 할 판정)을 합성 음성으로 만들어 노트북 시연 구성으로 흘리고, 녹화의 `guard/decision`을 기대와 **차례대로** 맞춘다. 코드를 바꾼 뒤 시연이 깨지지 않았는지 같은 조건으로 확인한다.

```bash
python -m bench.rehearsal make        # → data/stt/rehearsal/demo.wav (macOS say, 문장 사이 8초)
python3 scripts/launch.py --config scripts/launch_demo.yaml \
    --arg audio_svc="--input data/stt/rehearsal/demo.wav --realtime --session rehearsal"   # 마지막 응답 뒤 Ctrl+C
python -m bench.rehearsal check data/sessions/rehearsal.jsonl   # 단계별 통과 표, 모두 통과면 종료 코드 0
```

- 합성 음성(Yuna)은 사람 목소리와 받아쓰기 결과가 다르다 — 실패한 단계는 받아쓴 문장을 보고 시스템 문제인지 합성 음성 문제인지 가른다. 사람이 말하는 리허설(현장 조명·소음)은 따로 한다.
- 문장 사이는 음성 응답보다 길어야 한다 (재생 중 입력 무시). 6초에서는 긴 응답 뒤 첫 음절이 잘렸다.
