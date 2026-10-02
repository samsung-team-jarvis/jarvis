# audio_svc — 음성 입력 (VAD · STT · 호출어)

마이크(또는 wav 파일) 음성을 발화 단위로 잘라 받아쓰고 `stt/text`로 발행한다. (PLAN STT-01, STT-03)

```text
마이크 / wav ──100 ms 청크──▶ Silero VAD ──발화 구간──▶ SenseVoice ──▶ stt/text 발행
                                                                    + system/heartbeat 1초마다
```

- **VAD (Voice Activity Detection)**: 소리 중에서 사람이 말하는 구간만 골라낸다. 말이 끝나고 `min_silence`(0.5 s)만큼 조용해져야 "발화 끝"으로 판단한다.
- 호출어는 Q-08 v0 규칙(받아쓴 문장이 "자비스"로 시작하면 `wake: true`)만 있다. 오인식 변형 허용·비호출 발화 무시 로그는 STT-04.

## 모델 받기 (한 번만)

학교 보드 배포 이미지의 `~/voice/models`와 같은 종류의 모델을 쓴다. `models/`는 git 제외다.

```bash
mkdir -p models && cd models
# STT: SenseVoice-Small int8 (zh·en·ja·ko·yue). 압축 약 160MB, 풀면 약 240MB
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
tar xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2 && rm *.tar.bz2
# VAD: Silero VAD (약 630KB)
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
cd ..
```

다른 위치(보드의 `~/voice/models/...`)에 있으면 `--model-dir`·`--vad-model` 또는 환경변수 `JARVIS_STT_MODEL_DIR`·`JARVIS_VAD_MODEL`로 지정한다. STT 폴더에는 `model.int8.onnx`와 `tokens.txt`만 있으면 된다.

> 배포 이미지에 든 SenseVoice가 `2024-07-17`판인지 `2025-09-09`판인지, VAD 파일이 같은지는 보드를 받은 뒤 파일 크기·sha256으로 확인한다 (확인 필요, STT-02).

보드(Ubuntu)에서 마이크를 쓰려면 PortAudio가 필요하다: `sudo apt install -y libportaudio2`.

## 실행

### 서비스 (`stt/text` 발행)

```bash
python -m services.audio_svc                                      # 마이크, 버스는 JARVIS_BUS (기본 MQTT)
python -m services.audio_svc --input data/stt/cmds.wav --realtime # wav를 마이크처럼 실제 속도로
python -m services.audio_svc --input data/stt/cmds.wav --bus memory://   # 기다리지 않고 결과만 확인
```

출력 예 (Mac, 합성 음성 wav, `--realtime`):

```text
[stt/text] wake=True '자비스 후드 켜 줘.' (음성 1478 ms · STT 120 ms · 발화 끝→발행 718 ms)
```

- 종료: Ctrl+C 또는 SIGTERM. 종료할 때 발행 개수를 출력한다.
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

`AudioService`(service.py)는 입력 청크·VAD·STT·버스를 밖에서 받는다. 테스트는 가짜 VAD·STT로 발행 내용을 확인한다 (`tests/audio/test_service.py`).

## Spec

| 항목 | 내용 |
|---|---|
| 역할 | 음성 청크 → VAD 발화 구간 → SenseVoice → `stt/text` 발행, `system/heartbeat` 1초마다 |
| 하지 않는 일 (아직) | 호출어 변형 허용·비호출 무시 로그(STT-04), TTS 재생 중 입력 무시(STT-12), 소음 대응 VAD 조정(STT-11) |
| 입력 | 마이크(`sounddevice`, 16kHz mono) / wav 파일(즉시 또는 `--realtime`) |
| 출력 | `stt/text` `{text, wake, audio_ms, stt_ms, speech_end_mono}` ([interfaces](../../docs/architecture/interfaces.md) §2). 받아쓴 결과가 빈 구간(잡음)은 발행하지 않는다 |
| `speech_end_mono` | 발화 마지막 샘플이 들어온 시각(`time.monotonic`). 지연 측정(INFRA-06)의 출발점. 마이크는 콜백 시각 기준이라 실제 녹음보다 입력 지연(수십 ms 수준)만큼 늦게 찍힌다 |
| 설정 | `--input`, `--device`, `--realtime`, `--bus`, `--session`(기본 `s_<시각>`), `--model-dir`, `--vad-model`, `--language`(기본 `ko`), `--threads`(기본 4, 특강 p.34) |
| VAD 기본값 | threshold 0.5, min_silence 0.5 s, min_speech 0.25 s, max_speech 20 s (특강 p.36) |
| 실행 장치 | CPU (sherpa-onnx PyPI 휠). NPU(RKNN) 실행은 별도 빌드가 필요해 STT 비교 실험에서 다룬다 |
| 실패 시 | 모델 파일이 없으면 어떤 파일이 없는지와 받는 방법을 알려 주고 종료(코드 1). wav 형식이 맞지 않으면 변환 명령을 알려 준다 |

발화 끝→발행 시간의 대부분은 VAD가 "말이 끝났다"고 판단하기까지 기다리는 `min_silence`(0.5 s)다. 반응 속도와 문장 중간 끊김 사이의 조정은 STT-11에서 측정으로 정한다.
