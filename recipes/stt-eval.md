# Recipe: STT 평가 (CER · RTF · STT→Action)

> 2026-10-02 공식 저장소와 학교 특강2 p.34~38([school-materials](../docs/school-materials.md))로 API·지원 언어·기본 파라미터를 확인했다. 실제 실행 결과(STT-01, STT-05~07)는 아직 없다.
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

```bash
pip install sherpa-onnx soundfile jiwer
```

sherpa-onnx 문서의 SenseVoice 모델 다운로드 안내에 따라 모델(int8)과 `tokens.txt`를 받는다.

```python
import sherpa_onnx
import soundfile as sf

rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
    model="model.int8.onnx", tokens="tokens.txt", language="ko", use_itn=True
)
samples, sr = sf.read("sample.wav", dtype="float32")
stream = rec.create_stream()
stream.accept_waveform(sr, samples)
rec.decode_stream(stream)
print(stream.result.text)
```

`language="ko"`(고정)와 `"auto"`(자동 감지)를 둘 다 측정해 보고 결정한다.

### VAD 기본 파라미터 (특강 p.36 예시값 — 주방 소음에서 STT-11로 조정)

| 파라미터 | 시작값 | 의미 |
|---|---|---|
| `threshold` | 0.5 | 음성 확률 임계값 |
| `min_silence_duration` | 0.5 s | 이만큼 조용하면 발화 끝 (반응성 vs 끊김) |
| `min_speech_duration` | 0.25 s | 이보다 짧은 소리는 무시 |
| `num_threads` (STT) | 4 | 보드 CPU 8코어 중 STT 4, TTS 2 (특강 p.34) |

## 2. 녹음 규칙

- 형식: 16kHz, mono, wav
  ```bash
  ffmpeg -i input.m4a -ar 16000 -ac 1 output.wav
  ```
- 소음 조건 4종: `quiet`, `hood`(환풍기), `frying`(튀김), `mixed`
- 화자마다 `speaker_id`를 부여하고, 분할은 화자 단위로 한다.
- 원본 wav는 git에 넣지 않는다 (Drive). 매니페스트만 커밋한다.

## 3. 매니페스트 (`data/stt/manifest.csv`)

```text
utt_id,speaker_id,noise_type,mic,path,transcript,action_label,split
u0001,spk01,quiet,pin,stt/spk01/u0001.wav,자비스 후드 켜줘,TURN_ON:hood,test
```

## 4. 지표 계산

```python
import jiwer

cer = jiwer.cer(references, hypotheses)  # 소음 조건별로 따로 계산
```

- RTF = 전체 처리시간 / 전체 음성 길이
- STT→Action: STT 결과를 파서(규칙 또는 LLM)에 넣고 `action_label`과 비교

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
