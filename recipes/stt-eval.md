# Recipe: STT 평가 (CER · RTF · STT→Action)

> ⚠️ **검증 전 초안.** STT-01, STT-05, STT-06을 진행하면서 실제 명령으로 교체한다.

## 개념 3줄

- **CER (Character Error Rate)**: 글자 단위 오류율. 한국어는 띄어쓰기 때문에 WER보다 CER이 공정하다.
- **RTF (Real Time Factor)**: 처리시간 ÷ 음성 길이. 1보다 작아야 실시간이다.
- **STT→Action 정확도**: 받아쓰기가 조금 틀려도 최종 명령이 맞으면 성공. 실사용 관점에서 가장 중요하다.

## 1. 모델 실행 (Mac에서 먼저)

```bash
pip install sherpa-onnx soundfile jiwer
```

sherpa-onnx 문서의 SenseVoice 모델 다운로드 안내에 따라 모델(int8)과 `tokens.txt`를 받는다.

```python
import sherpa_onnx, soundfile as sf

rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(
    model="model.int8.onnx", tokens="tokens.txt", use_itn=True)   # 언어 옵션 확인 필요
samples, sr = sf.read("sample.wav", dtype="float32")
stream = rec.create_stream()
stream.accept_waveform(sr, samples)
rec.decode_stream(stream)
print(stream.result.text)
```

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
cer = jiwer.cer(references, hypotheses)   # 소음 조건별로 따로 계산
```

- RTF = 전체 처리시간 / 전체 음성 길이
- STT→Action: STT 결과를 파서(규칙 또는 LLM)에 넣고 `action_label`과 비교

## 5. 비교 실험

- 모델: SenseVoice vs Whisper(small/base) — 정확도는 Mac, **속도는 보드**
- 마이크: 핀마이크 vs 웹캠 내장
- 결과는 [METRICS](../docs/METRICS.md)에 기록
