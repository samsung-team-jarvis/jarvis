# audio_svc — 음성 입력·응답

마이크 음성을 발화 단위로 잘라 받아쓰고(`stt/text`), 명령 결과·위험 경고를 음성으로 읽어 준다. (PLAN STT-01·03·04·12)

```text
마이크 / wav ─▶ Silero VAD ─(발화 구간)─▶ SenseVoice STT ─▶ 호출어 판정 ─▶ stt/text
guard/decision · fusion/state ─▶ 응답 문장 ─▶ 한국어 VITS ─▶ 스피커   (재생 중 마이크 입력은 무음)
```

## 빠른 실행

```bash
python -m services.audio_svc                                       # 마이크 → stt/text (버스: JARVIS_BUS)
python -m services.audio_svc --input cmds.wav --bus memory://       # wav로 결과만 확인
python -m services.audio_svc.transcribe a.wav                       # 파일 하나 받아쓰기 (VAD 없이)
python -m services.audio_svc.speak "후드를 켰습니다." --out a.wav --no-play   # 응답 문장 하나 합성
```

모델이 없으면 무엇이 없는지와 받는 방법을 알려 주고 끝난다 → [모델 받기](#모델-받기-한-번만).

## 모델 받기 (한 번만)

학교 보드 이미지(`~/voice/models`)와 같은 종류다. `models/`는 git 제외.

```bash
mkdir -p models && cd models
# STT: SenseVoice-Small int8 (압축 약 160MB)
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
tar xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2 && rm *.tar.bz2
# VAD: Silero (약 630KB)
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
# TTS: 한국어 VITS + espeak-ng-data (압축 약 67MB)
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-mimic3-ko_KO-kss_low.tar.bz2
tar xjf vits-mimic3-ko_KO-kss_low.tar.bz2 && rm *.tar.bz2
cd ..
```

| 모델 | 기본 경로 | 바꾸기 |
|---|---|---|
| STT | `models/sherpa-onnx-sense-voice-…-int8-2024-07-17/` (`model.int8.onnx`, `tokens.txt`) | `--model-dir` / `JARVIS_STT_MODEL_DIR` |
| VAD | `models/silero_vad.onnx` | `--vad-model` / `JARVIS_VAD_MODEL` |
| TTS | `models/vits-mimic3-ko_KO-kss_low/` | `--tts-model-dir` / `JARVIS_TTS_MODEL_DIR` |

- 보드 이미지에 든 모델이 이 판과 같은지는 보드 수령 후 sha256으로 확인한다 (확인 필요, STT-02).
- 보드(Ubuntu)에서 마이크를 쓰려면 `sudo apt install -y libportaudio2`. Mac은 처음 실행할 때 터미널에 마이크 권한을 허용한다.

## 실행 옵션

| 옵션 | 기본 | 설명 |
|---|---|---|
| `--input` | `mic` | `mic` 또는 wav 경로 (16kHz·16-bit — 변환: `ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 out.wav`) |
| `--realtime` | 꺼짐 | wav를 마이크처럼 실제 속도로 (지연 측정용) |
| `--device` | 기본 장치 | 마이크 번호·이름 (`python -c "import sounddevice; print(sounddevice.query_devices())"`) |
| `--bus` / `--session` | `JARVIS_BUS` / `s_<시각>` | 버스 주소 / 세션 ID |
| `--language` / `--threads` | `ko` / 4 | `auto`는 짧은 명령을 다른 언어로 잘못 감지한 사례가 있어 `ko` 고정 |
| `--no-tts` / `--no-play` / `--tts-out` | | 음성 응답 끄기 / 재생하지 않기 / 응답을 wav로 저장 |

종료는 Ctrl+C 또는 SIGTERM. 종료할 때 발행 개수(호출 / 호출어 없어 무시)를 출력한다.

```text
[stt/text] 명령 '긴급 정지.' ← '자비스 긴급 정지.' (음성 1574 ms · STT 34 ms · 발화 끝→발행 591 ms)
[stt/text] 무시(호출어 없음) '오늘 저녁 뭐야 먹지?' (음성 1574 ms · STT 37 ms · 발화 끝→발행 566 ms)
```

## 동작

### VAD

소리 중 말하는 구간만 골라낸다. 말이 끝나고 `min_silence`(0.5 s)만큼 조용해야 "발화 끝"이다. 발화 끝 → 발행 시간의 대부분이 이 대기다 (조정은 STT-11).

### 호출어

`wake.py` (Q-08) — 받아쓴 문장이 호출어로 **시작할 때만** 명령으로 본다.
- 호출어: "자비스" + 첫 자음 오인식 변형(첫 글자 자·다·바·차·짜·사·타 + "비스") + "자비야"·"자비 쓰야". "서비스"처럼 흔한 말과 겹치지 않게 모음 ㅏ만.
- 띄어쓰기·문장부호는 무시하고 비교한다. 호출어 바로 뒤 "야/아"는 뺀다 ("자비스야 후드 켜 줘" → "후드 켜 줘").
- "저기 자비스 후드 켜 줘"처럼 중간에 나오면 호출이 아니다. 호출어 없는 발화도 `wake: false`로 발행해 녹화에 남는다.
- 시연에서는 마이크 가까이에서 "야" 없이 "자비스"로 부른다 (아래 확인 기록).

### 음성 응답

`responses.py` → `tts.py` → `speaker.py` — `guard/decision`과 `fusion/state`를 받아 정해진 문장을 읽는다. 합성·재생은 별도 스레드, **재생 중 + 0.3초는 마이크 입력을 무음으로** 바꿔 스피커 소리를 명령으로 다시 받지 않게 한다.

| 입력 | 문장 |
|---|---|
| ALLOW `TURN_ON hood` | 후드를 켰습니다. |
| ALLOW `SET_TIMER 210 s, burner_1` | 3분 30초 뒤에 1번 화구를 끕니다. |
| ALLOW `ASK_CLARIFY TURN_ON / target` | 어느 장치를 켤까요? |
| REJECT `TURN_ON burner_1` + reason | 지금은 1번 화구를 제어할 수 없어요. {reason} |
| ASK (Guard가 확인 요청) | 정말 1번 화구를 제어할까요? |
| `fusion/state` risk가 warn·danger로 **올라갈 때만** | 주의하세요… / 위험 상황이에요. 불을 확인해 주세요. |

TTS 모델이 없으면 경고만 내고 STT는 계속 동작한다. `CHECK_STATUS`·`CHECK_RISK`는 읽을 상태가 아직 없어 "준비 중" 문장 (FUS-08 이후).

## Spec

| 항목 | 내용 |
|---|---|
| 입력 | 마이크(`sounddevice`, 16kHz mono) / wav · `guard/decision` · `fusion/state` |
| 출력 | `stt/text` `{text, wake, audio_ms, stt_ms, speech_end_mono}` ([interfaces](../../docs/architecture/interfaces.md) §2), `system/heartbeat` 1초마다, 스피커 |
| `speech_end_mono` | 발화 마지막 샘플이 들어온 시각(`time.monotonic`) — 지연 측정의 출발점. 마이크는 콜백 시각 기준이라 실제보다 수십 ms 늦다 |
| VAD | threshold 0.5, min_silence 0.5 s, min_speech 0.25 s, max_speech 20 s (특강 p.36) |
| 실행 장치 | CPU — STT 4스레드, TTS 2스레드 (특강 p.34). NPU는 LLM·YOLO 몫 |
| 실패 시 | 모델 없음 → 원인·받는 방법 안내 후 종료(코드 1). 빈 받아쓰기(잡음)는 발행하지 않음. 마이크 입력이 3초간 완전히 0이면 권한 경고 |
| 아직 안 하는 일 | 호출어만 말한 뒤 다음 발화를 이어 받기, 소음 대응 VAD 조정(STT-11) |

## 코드에서 쓰기

```python
from services.audio_svc.stt import SenseVoice
from services.audio_svc.wake import split_wake

stt = SenseVoice("models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17", language="ko")
result = stt.transcribe_file("sample.wav")      # 또는 stt.transcribe(samples, 16000)
print(result.text, result.audio_ms, result.stt_ms, result.rtf)

split_wake("자비 스야 후드 켜 줘.")             # "후드 켜 줘."  (호출 아니면 None)
```

`AudioService`는 입력 청크·VAD·STT·버스를 밖에서 받아 가짜로 바꿔 끼울 수 있다 (`tests/audio/`).

## 확인 기록 (Mac, 2026-10-02)

사람 음성은 본인(spk01) MacBook 내장 마이크. **보드·핀마이크는 아직 — 수치는 참고값.** 40문장 평가 결과는 [STT 평가 recipe](../../recipes/stt-eval.md#spk01-val-첫-결과-2026-10-02).

**호출어 오인식** — 지금 규칙으로의 처리:

| 말한 것 | SenseVoice 출력 | 음성 | 처리 |
|---|---|---|---|
| 자비스 후드 켜줘 | **다비스** 후드 켜줘. | 사람 | 호출 (#57) |
| 자비스 긴급 정지 | **바비스** 긴급정지 아 물어볼까? | 사람 | 호출 (#57) |
| 자비스야 2번 불 켜줘 | **자비야** 이번 불 켜줘. | 사람 | 호출 (#61) |
| 자비스야 | **자비 쓰야**. | 사람 | 호출 (#61) |
| 자비스 | 차비스. | 합성 | 호출 |
| 자비스야 후드 켜줘 | 자비 스야 후드 켜 줘. | 합성 | 호출 (띄어쓰기 무시) |
| 자비스 2번 화구 꺼줘 | **다비** 이번 화구 꺼줘. | 사람 | 놓침 ('스'가 숫자 '이' 앞에서 빠짐, 2회) |
| 자비스 노래 틀어줘 | **자이스** 노래 틀어 줘. | 사람 | 놓침 |
| 자비스야 후드 켜줘 | 잡비야 후드 켜줘. | 합성 + 잡음 | 놓침 |

**마이크 거리** (같은 5문장): 자연스러운 거리 3/4 · **멀리(50cm~1m) 0/4** — 명령 부분까지 깨짐("2번 화구"→"입 번구", "3분"→"선") · 가까이(30cm 이내) 3/4. 일반 대화는 매번 무시(오호출 0). → **거리가 가장 큰 요인**, 시연은 핀마이크를 말하는 사람 가까이.

**TTS 품질** — 문장 하나 합성 0.1~0.2초. 같은 문장도 합성마다 발음이 조금씩 다르다(VITS 무작위성). 합성 음성을 다시 받아쓴 CER 0.15~0.17 (`noise_scale`·`length_scale`을 바꿔도 차이 작음, 사람 명료도 측정 아님). 숫자는 아라비아 숫자가 더 정확히 읽히고, `?`·`!`는 이 모델이 읽지 못해 마침표로 바꾼다.

**언어 설정** — `language=auto`는 "자비스 후드 켜줘"(합성)를 일본어로 감지했다 → `ko` 고정 ([recipe](../../recipes/stt-eval.md#stt-01-결과-mac)).
