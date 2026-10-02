# Recipe: STT 평가 (CER · RTF · STT→Action)

> 2026-10-02 공식 저장소와 학교 특강2 p.34~38([school-materials](../docs/school-materials.md))로 API·지원 언어·기본 파라미터를 확인했다. Mac 실행은 STT-01에서 확인했다(아래 [STT-01 결과](#stt-01-결과-mac)). 테스트 세트 측정(STT-05~07)은 아직 없다.
>
> 학교 보드 배포 이미지에는 `~/voice/models`에 **silero_vad.onnx, sherpa-onnx SenseVoice(int8), 한국어 VITS TTS**가 미리 들어 있다. 같은 모델을 Mac에서도 받아 쓴다.

## 개념 3줄

- **CER (Character Error Rate)**: 글자 단위 오류율. 한국어는 띄어쓰기 때문에 WER보다 CER이 공정하다.
- **RTF (Real Time Factor)**: 처리시간 ÷ 음성 길이. 1보다 작아야 실시간이다.
- **STT→Action 정확도**: 받아쓰기가 조금 틀려도 최종 명령이 맞으면 성공. 실사용 관점에서 가장 중요하다.

## 확인된 사실

| 항목 | 내용 |
|---|---|
| SenseVoice-Small 지원 언어 | 중국어(zh) · 광둥어(yue) · 영어(en) · 일본어(ja) · **한국어(ko)** |
| sherpa-onnx | 1.13.8, pip 휠: macOS arm64 · Linux aarch64 (Python 3.10~3.13) → Mac·보드 모두 설치 가능 |
| `language` 값 | `auto`, `zh`, `en`, `ja`, `ko`, `yue` |
| NPU(RKNN) 실행 | sherpa-onnx가 RK3588에서 SenseVoice·Silero VAD 등의 RKNN 실행을 지원. 단 **기본 PyPI 휠이 아니라 RKNN 빌드**가 따로 필요 |
| VAD | sherpa-onnx에 Silero VAD 포함 (`VadModelConfig`, `VoiceActivityDetector`) |
| CER 계산 | `jiwer.cer(reference, hypothesis)` (jiwer 4.0.0) |

## 1. 모델 실행 (Mac에서 먼저)

모델 받기와 실행 명령은 [audio_svc README](../services/audio_svc/README.md)가 source of truth다. `sherpa-onnx`·`numpy`는 `requirements.txt`에 있어 `python3 scripts/setup.py`로 같이 설치된다.

```bash
python -m services.audio_svc.transcribe <wav...> --language ko
```

코드에서는 `services.audio_svc.stt.SenseVoice`를 쓴다 (내부적으로 `sherpa_onnx.OfflineRecognizer.from_sense_voice`).

### STT-01 결과 (Mac)

2026-10-02, M1 Pro Mac · Python 3.11 · sherpa-onnx 1.13.8 · `sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17` · CPU 4스레드. **Mac 측정이고 테스트 세트가 아니다** — METRICS에 넣지 않는다.

입력: 모델에 들어 있는 `test_wavs/ko.wav`(사람 음성) 1개 + macOS `say -v Yuna`로 만든 합성 음성 명령 4개(사람 녹음 아님).

| 파일 | 정답 | `language=ko` | `language=auto` |
|---|---|---|---|
| ko.wav (4.6 s) | — | 조금만 생각을 하면서 살면 훨씬 편할 거야. | (ko와 같음) |
| c01 (1.4 s) | 자비스 후드 켜줘 | 자비스 후드 켜 줘. | **サビス 후드켜嬢。** (일본어로 감지) |
| c02 (1.7 s) | 자비스 2번 화구 꺼줘 | 자비스 2 화국꺼 죠. | 자비스 2 화국거 죠. |
| c03 (2.2 s) | 자비스 타이머 3분 맞춰줘 | 자비스 타이머 3분 맞추하 죠. | 자비스 타이머 3분 맞춰하 죠. |
| c04 (1.5 s) | 자비스 긴급 정지 | 자비스 긴급 정지. | 자비스 긴급 정지. |

- 처리 시간 36~78 ms, RTF 0.017~0.026 (Mac). 모델 로드 약 0.5~0.6 s.
- **`ko` 고정을 기본으로 한다**: `auto`는 짧은 명령에서 언어를 잘못 감지했다(c01).
- 합성 음성 기준으로도 "2번 화구" → "2 화국", "꺼줘·맞춰줘" → "꺼 죠·맞추하 죠" 같은 오인식이 나왔다. 숫자+단위, 짧은 어미가 약점 후보 → 사람 음성 테스트 세트(STT-05~07)에서 확인하고, 오인식 변형 데이터(STT-10)·규칙 파서(FUS-02) 키워드에 반영한다.

### VAD 기본 파라미터 (특강 p.36 예시값 — 주방 소음에서 STT-11로 조정)

| 파라미터 | 시작값 | 의미 |
|---|---|---|
| `threshold` | 0.5 | 음성 확률 임계값 |
| `min_silence_duration` | 0.5 s | 이만큼 조용하면 발화 끝 (반응성 vs 끊김) |
| `min_speech_duration` | 0.25 s | 이보다 짧은 소리는 무시 |
| `num_threads` (STT) | 4 | 보드 CPU 8코어 중 STT 4, TTS 2 (특강 p.34) |

## 2. 녹음 규칙

녹음 절차(대본·도구·소음 만드는 법·분할)는 [STT 테스트 세트 녹음](./stt-recording.md). 아래는 형식 규칙.

- 형식: 16kHz, mono, wav
  ```bash
  ffmpeg -i input.m4a -ar 16000 -ac 1 output.wav
  ```
- 소음 조건 4종: `quiet`, `hood`(환풍기), `frying`(튀김), `mixed`
- 화자마다 `speaker_id`를 부여하고, 분할은 화자 단위로 한다.
- 원본 wav는 git에 넣지 않는다 (각자 보관·직접 전달, [등록부](../docs/artifacts.md)). 매니페스트만 커밋한다.

## 3. 매니페스트 (`data/stt/manifest.csv`)

```text
utt_id,speaker_id,noise_type,mic,path,transcript,action_label,split
u0001,spk01,quiet,pin,stt/spk01/u0001.wav,자비스 후드 켜줘,<jarvis_1>(target=hood)<jarvis_end>,test
u0002,spk01,hood,pin,stt/spk01/u0002.wav,오늘 저녁 뭐 먹지,,test
```

- `path`: `data/` 기준 wav 경로 (wav는 git 제외, 매니페스트만 커밋)
- `transcript`: 실제로 말한 문장 (호출어 포함). 숫자는 SenseVoice ITN 출력처럼 아라비아 숫자로 쓴다 ("3분")
- `action_label`: 정답 명령의 **함수 토큰** ([interfaces](../docs/architecture/interfaces.md) §3). 호출어가 없는 발화(명령으로 처리되면 안 됨)는 비운다. 형식이 틀리면 측정 전에 오류로 알려 준다
- `split`: 화자 단위로 나눈다 (같은 화자가 train·test에 같이 들어가지 않게)

## 4. 지표 계산 — `bench/stt_eval.py`

```bash
python -m bench.stt_eval data/stt/manifest.csv --split test --csv out.csv
```

전체·소음·마이크·화자별로 아래 표를 낸다 (Markdown, METRICS·PR에 붙여 넣기 좋게). 발화별 결과는 `--csv`.

| 열 | 정의 |
|---|---|
| CER | 띄어쓰기·문장부호를 지운 글자 기준 (`jiwer.cer`, 묶음 전체 합산) |
| RTF | 인식 시간 합 / 음성 길이 합 |
| 호출어 인식 | 정답에 호출어가 있는 발화 중 받아쓴 문장도 호출로 판정된 비율 |
| 오호출 | 정답에 호출어가 없는데 호출로 판정된 비율 |
| STT→Action (전체 / action만) | 받아쓴 문장 → 호출어 판정 → 규칙 파서 결과가 정답 명령과 같은 비율 |
| 정답 문장→파서 | 정답 문장을 그대로 파서에 넣었을 때 — STT 오류를 뺀 파서 자체 정확도. 이 값과 STT→Action의 차이가 STT 탓 |

- 파일 전체를 한 번에 받아쓴다 (VAD 없이). 녹음 파일 하나 = 발화 하나.
- STT 엔진은 `Engine`(`transcribe_file`)만 맞추면 바꿔 끼울 수 있다 (STT-08 Whisper).
- 2026-10-02 합성 음성(macOS `say`) 18개로 동작만 확인했다 — 사람 음성 테스트 세트가 아니라 METRICS에 넣지 않는다.

### spk01 val 첫 결과 (2026-10-02)

MacBook 내장 마이크, 30cm 이내, `quiet`, 40문장 (명령 34 + 호출어 없음 6). **val 1명 — 조정 근거이고 METRICS 결과가 아니다.**

| 상태 | CER | 호출어 인식 | 오호출 | STT→Action | 정답 문장→파서 |
|---|---|---|---|---|---|
| 처음 (#58 첫 자음 규칙 포함) | 10.6% | 91.2% | 0% | 70.6% | 97.1% |
| + 오인식 사전 + "자비야" 호출 (#61) | 10.6% | 97.1% | 0% | **88.2%** | 97.1% |

- 틀린 주원인: **"N번 화구"** (숫자보다 "화구"라는 단어가 깨짐: 화국·번구·하고), "타이머"→"타임머", "자비스야"→"자비야". "이번 **불**"처럼 '불'은 잘 받아썼다.
- 남은 오류: "입 화구"(2번), "일 번 하고"(1번 화구), "산 분"(3분), "자이스"(자비스) — 흔한 말과 겹쳐 사전에 넣지 않음.
- 정답 문장→파서 97.1%의 1건은 "노래 틀어줘"(알려진 v0 한계).

## 5. 비교 실험

- 모델: SenseVoice vs Whisper(small/base) — 정확도는 Mac, **속도는 보드**
- 실행 장치: SenseVoice CPU vs NPU(RKNN 빌드) — NPU는 YOLO·LLM과 코어를 나눠 쓰므로 동시 구동 부하까지 측정 (BOARD-08)
- 마이크: 핀마이크 vs 웹캠 내장
- 결과는 [METRICS](../docs/METRICS.md)에 기록

## 출처 (2026-10-02 확인)

- https://github.com/FunAudioLLM/SenseVoice (README — 지원 언어)
- https://github.com/k2-fsa/sherpa-onnx (`python/sherpa_onnx/offline_recognizer.py`, `python-api-examples/vad-with-non-streaming-asr.py`, `sherpa-onnx/csrc/rknn/`)
- https://k2-fsa.github.io/sherpa/onnx/rknn/
- https://pypi.org/project/sherpa-onnx/
- https://github.com/jitsi/jiwer
