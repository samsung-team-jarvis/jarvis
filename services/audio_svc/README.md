# audio_svc — 음성 입력 (VAD · STT · 호출어)

마이크(또는 wav 파일) 음성을 발화 단위로 잘라 받아쓰고 `stt/text`로 발행한다. 명령 결과·위험 경고는 음성으로 읽어 준다. (PLAN STT-01, STT-03, STT-04, STT-12)

```text
마이크 / wav ──100 ms 청크──▶ Silero VAD ──발화 구간──▶ SenseVoice ──▶ stt/text 발행
                                                                    + system/heartbeat 1초마다
guard/decision · fusion/state(위험) ──▶ 응답 문장 ──▶ 한국어 VITS ──▶ 스피커 (재생 중 마이크 입력은 무음)
```

- **VAD (Voice Activity Detection)**: 소리 중에서 사람이 말하는 구간만 골라낸다. 말이 끝나고 `min_silence`(0.5 s)만큼 조용해져야 "발화 끝"으로 판단한다.
- 호출어: 받아쓴 문장이 "자비스"로 시작할 때만 `wake: true` (Q-08 v0). 아래 [호출어](#호출어) 참고.

## 모델 받기 (한 번만)

학교 보드 배포 이미지의 `~/voice/models`와 같은 종류의 모델을 쓴다. `models/`는 git 제외다.

```bash
mkdir -p models && cd models
# STT: SenseVoice-Small int8 (zh·en·ja·ko·yue). 압축 약 160MB, 풀면 약 240MB
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
tar xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2 && rm *.tar.bz2
# VAD: Silero VAD (약 630KB)
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
# TTS: 한국어 VITS (KSS, low) + espeak-ng-data. 압축 약 67MB
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-mimic3-ko_KO-kss_low.tar.bz2
tar xjf vits-mimic3-ko_KO-kss_low.tar.bz2 && rm *.tar.bz2
cd ..
```

다른 위치(보드의 `~/voice/models/...`)에 있으면 `--model-dir`·`--vad-model` 또는 환경변수 `JARVIS_STT_MODEL_DIR`·`JARVIS_VAD_MODEL`로 지정한다. STT 폴더에는 `model.int8.onnx`와 `tokens.txt`만 있으면 된다.

> 배포 이미지에 든 SenseVoice가 `2024-07-17`판인지 `2025-09-09`판인지, VAD 파일이 같은지, 한국어 VITS가 이 모델(`vits-mimic3-ko_KO-kss_low`)인지는 보드를 받은 뒤 파일 크기·sha256으로 확인한다 (확인 필요, STT-02). TTS 폴더 경로는 `--tts-model-dir` 또는 `JARVIS_TTS_MODEL_DIR`.

보드(Ubuntu)에서 마이크를 쓰려면 PortAudio가 필요하다: `sudo apt install -y libportaudio2`.

## 실행

### 서비스 (`stt/text` 발행)

```bash
python -m services.audio_svc                                      # 마이크, 버스는 JARVIS_BUS (기본 MQTT)
python -m services.audio_svc --input data/stt/cmds.wav --realtime # wav를 마이크처럼 실제 속도로
python -m services.audio_svc --input data/stt/cmds.wav --bus memory://   # 기다리지 않고 결과만 확인
```

출력 예 (Mac, 합성 음성 wav):

```text
[stt/text] 명령 '긴급 정지.' ← '자비스 긴급 정지.' (음성 1574 ms · STT 34 ms · 발화 끝→발행 591 ms)
[stt/text] 무시(호출어 없음) '오늘 저녁 뭐야 먹지?' (음성 1574 ms · STT 37 ms · 발화 끝→발행 566 ms)
```

- 종료: Ctrl+C 또는 SIGTERM. 종료할 때 발행 개수(호출 / 호출어 없어 무시)를 출력한다.
- 마이크 장치 선택: `--device <번호 또는 이름>` (목록: `python -c "import sounddevice; print(sounddevice.query_devices())"`). Mac에서는 처음 실행할 때 터미널 앱에 마이크 권한을 허용해야 한다.
- wav 입력은 **16kHz · 16-bit** 만 받는다 (VAD 제약). 변환: `ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 out.wav`
- 발행 확인은 다른 터미널에서 `python -m services.recorder` 또는 `mosquitto_sub -t 'stt/#' -v`.

### wav 파일 받아쓰기만 (VAD 없이 파일 전체)

```bash
python -m services.audio_svc.transcribe models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/ko.wav
python -m services.audio_svc.transcribe data/stt/*.wav --language ko --threads 4
```

파일별 텍스트, 음성 길이, 인식 시간, RTF(처리 시간 ÷ 음성 길이, 1보다 작으면 실시간)를 출력한다. 16kHz가 아닌 wav도 받는다(sherpa-onnx가 내부 변환).

- `--language`는 기본 `ko`(고정). `auto`는 짧은 명령을 다른 언어로 잘못 감지한 사례가 있다 ([STT 평가 recipe](../../recipes/stt-eval.md)의 STT-01 결과).
- `--no-itn`: ITN(Inverse Text Normalization — "삼 분"을 "3분"으로, 문장부호 추가) 끄기.

## 코드에서 쓰기

```python
from services.audio_svc.stt import SenseVoice

stt = SenseVoice("models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17", language="ko")
result = stt.transcribe_file("sample.wav")          # 또는 stt.transcribe(samples, 16000)
print(result.text, result.audio_ms, result.stt_ms, result.rtf)
```

규칙 파서(FUS-02) 등 `stt/text`를 받는 쪽은 `wake`가 `false`면 명령으로 처리하지 않고, 명령 부분은 `split_wake`로 얻는다:

```python
from services.audio_svc.wake import split_wake

split_wake("자비 스야 후드 켜 줘.")    # "후드 켜 줘."
split_wake("오늘 저녁 뭐 먹지?")       # None (호출 아님)
```

`AudioService`(service.py)는 입력 청크·VAD·STT·버스를 밖에서 받는다. 테스트는 가짜 VAD·STT로 발행 내용을 확인한다 (`tests/audio/test_service.py`).

## Spec

| 항목 | 내용 |
|---|---|
| 역할 | 음성 청크 → VAD 발화 구간 → SenseVoice → `stt/text` 발행, `system/heartbeat` 1초마다 |
| 하지 않는 일 (아직) | 호출어 오인식 변형 허용(STT-05 확인 후), TTS 재생 중 입력 무시(STT-12), 소음 대응 VAD 조정(STT-11) |
| 입력 | 마이크(`sounddevice`, 16kHz mono) / wav 파일(즉시 또는 `--realtime`) |
| 출력 | `stt/text` `{text, wake, audio_ms, stt_ms, speech_end_mono}` ([interfaces](../../docs/architecture/interfaces.md) §2). 받아쓴 결과가 빈 구간(잡음)은 발행하지 않는다. 호출어가 없는 발화도 `wake: false`로 발행해 recorder에 무시 기록이 남는다 |
| `speech_end_mono` | 발화 마지막 샘플이 들어온 시각(`time.monotonic`). 지연 측정(INFRA-06)의 출발점. 마이크는 콜백 시각 기준이라 실제 녹음보다 입력 지연(수십 ms 수준)만큼 늦게 찍힌다 |
| 설정 | `--input`, `--device`, `--realtime`, `--bus`, `--session`(기본 `s_<시각>`), `--model-dir`, `--vad-model`, `--language`(기본 `ko`), `--threads`(기본 4, 특강 p.34) |
| VAD 기본값 | threshold 0.5, min_silence 0.5 s, min_speech 0.25 s, max_speech 20 s (특강 p.36) |
| 실행 장치 | CPU (sherpa-onnx PyPI 휠). NPU(RKNN) 실행은 별도 빌드가 필요해 STT 비교 실험에서 다룬다 |
| 실패 시 | 모델 파일이 없으면 어떤 파일이 없는지와 받는 방법을 알려 주고 종료(코드 1). wav 형식이 맞지 않으면 변환 명령을 알려 준다 |

발화 끝→발행 시간의 대부분은 VAD가 "말이 끝났다"고 판단하기까지 기다리는 `min_silence`(0.5 s)다. 반응 속도와 문장 중간 끊김 사이의 조정은 STT-11에서 측정으로 정한다.

## 호출어

`wake.py` — Q-08: 받아쓴 문장이 호출어로 **시작할 때만** 호출.

- 호출어: "자비스"와 **첫 자음 오인식 변형** — 첫 글자가 자·다·바·차·짜·사·타 + "비스" (`WAKE_WORDS`). "서비스"처럼 흔한 말과 겹치지 않게 모음이 ㅏ인 첫 글자만 허용한다.
- 비교할 때 띄어쓰기·문장부호를 무시한다. SenseVoice가 "자비스야"를 "자비 스야"로 받아쓴 사례가 있어서다.
- 호출어 바로 뒤 호격 조사 "야/아"는 명령 부분에서 뺀다 ("자비스야 후드 켜 줘" → "후드 켜 줘"). '야'가 단어의 일부면 남긴다 ("자비스야채 썰어" → "야채 썰어").
- "저기 자비스 후드 켜 줘"처럼 중간에 나오면 호출이 아니다.
- 호출어만 말한 경우("자비스.")는 호출이지만 명령 부분이 비어 있다. 다음 발화를 이어 받는 동작은 아직 없다.

확인된 오인식 (SenseVoice int8, Mac):

| 말한 것 | 출력 | 음성 | 지금 처리 |
|---|---|---|---|
| 자비스 후드 켜줘 | **다비스** 후드 켜줘. | 사람 (MacBook 내장 마이크, 2026-10-02) | 호출 (변형 규칙, #57) |
| 자비스 타이머 3분 맞춰줘 | **다비스** 타이머 3분 맞춰줘. | 사람 | 호출 |
| 자비스 긴급 정지 | **바비스** 긴급정지 아 물어볼까? | 사람 | 호출 |
| 자비스 2번 화구 꺼줘 | **다비** 이번 화구 꺼줘. | 사람 | **놓침** ('스'까지 빠짐) |
| 자비스 | 차비스. | 합성 | 호출 |
| 자비스야 후드 켜줘 | 잡비야 후드 켜줘. | 합성 + 잡음 | 놓침 |
| 자비스야 후드 켜줘 | 자비 스야 후드 켜 줘. | 합성 | 호출 (띄어쓰기 무시) |

**거리 비교** (같은 화자·같은 5문장, MacBook 내장 마이크, 2026-10-02, 규칙 적용 후 기준):

| 거리 | 호출 인식 (명령 4건) | 명령 부분 받아쓰기 | 명령까지 맞음 |
|---|---|---|---|
| 1차 (자연스러운 거리) | 3 (다비스·다비스·바비스) / 놓침 1 (다비) | 정확 | 3 |
| 2차 (멀리, 50cm~1m) | 2 / 놓침 2 (아비스·다위스) | **깨짐** ("2번 화구" → "입 번구", "3분" → "선") | 0 |
| 3차 (가까이, 30cm 이내) | 3 / 놓침 1 (다비 이 번 화구) | 정확 ("삼 분"도 파서가 처리) | 3 |

- **거리가 가장 큰 요인**이다 — 멀면 호출어뿐 아니라 명령 부분도 깨진다. 시연에서는 핀마이크를 말하는 사람 가까이 둔다 (핀마이크로 다시 확인 필요).
- "자비스 2번 화구"는 두 번 모두 "다비 이(번)"으로 '스'가 빠졌다 (숫자 '이' 앞). STT-05 녹음(대본 s06)으로 반복되는지 본다.
- 일반 대화("오늘 저녁 뭐 먹지")는 매번 무시됐다 (오호출 0/3).

사람 음성 첫 확인에서 변형 규칙 전에는 **명령 4건 모두 호출로 인식되지 않았다**. 규칙을 늘릴수록 일반 대화를 호출로 잘못 받을 위험도 커지므로, STT-05 녹음의 val 화자로 호출어 인식률과 오호출을 함께 확인하고 조정한다 (test 화자를 보고 고치지 않는다).

## 음성 응답 (TTS)

`audio_svc`가 `guard/decision`과 `fusion/state`를 구독해 정해진 문장(`responses.py`)을 한국어 VITS(`tts.py`, CPU 2스레드)로 읽는다. 합성·재생은 별도 스레드(`speaker.py`)에서 하고, **재생하는 동안과 끝난 뒤 0.3초는 마이크 입력을 무음으로 바꿔** 스피커 소리를 다시 명령으로 받지 않게 한다 (건너뛰지 않고 무음으로 넣어 발화 끝 시각 계산은 유지).

| 입력 | 문장 예 |
|---|---|
| ALLOW `TURN_ON hood` | 후드를 켰습니다. |
| ALLOW `SET_TIMER 210 s, burner_1` | 3분 30초 뒤에 1번 화구를 끕니다. |
| ALLOW `ASK_CLARIFY TURN_ON / target` | 어느 장치를 켤까요? |
| REJECT `TURN_ON burner_1` + reason | 지금은 1번 화구를 제어할 수 없어요. {reason} |
| ASK (Guard가 확인 요청) | 정말 1번 화구를 제어할까요? |
| `fusion/state` risk가 warn·danger로 **올라갈 때만** | 주의하세요… / 위험 상황이에요. 불을 확인해 주세요. |

```bash
python -m services.audio_svc --no-play --tts-out data/tts     # 소리 없이 응답을 wav로만 (확인용)
python -m services.audio_svc --no-tts                         # 음성 응답 끄기
python -m services.audio_svc.speak "후드를 켰습니다." --out a.wav --no-play   # 문장 하나만
```

- TTS 모델이 없으면 경고만 내고 응답 없이 STT는 계속 동작한다.
- `CHECK_STATUS`·`CHECK_RISK`는 장치 상태·위험도를 아직 읽을 곳이 없어 "준비 중" 문장을 읽는다 (FUS-08 이후).
- 숫자는 아라비아 숫자로 쓴다 ("3분" — 한글 수보다 정확히 읽음). `?`·`!`는 이 모델이 읽지 못해 마침표로 바꾼다.
- **품질 (Mac 확인, 2026-10-02)**: 문장 하나 합성 0.1~0.2초. 같은 문장도 합성마다 발음이 조금씩 다르다(VITS 무작위성). 합성 음성을 SenseVoice로 다시 받아쓴 CER 평균 0.15~0.17 (응답 문장 6개×5회, `noise_scale` 0~0.667·`length_scale` 1.0~1.15 사이 차이는 작음) — 사람이 듣는 명료도 측정은 아니다. 품질 개선이 필요하면 학교 제공 모델과 비교한다.
