# audio_svc — 음성 입력 (VAD · STT · 호출어)

마이크 음성을 받아써서 `stt/text`로 발행하는 서비스. 지금은 **STT-01 단계로 wav 파일 받아쓰기만** 있다. 마이크 → VAD → 발행은 STT-03, 호출어는 STT-04에서 붙인다.

## 모델 받기 (한 번만)

학교 보드 배포 이미지의 `~/voice/models`와 같은 SenseVoice-Small **int8** 모델(zh·en·ja·ko·yue)을 쓴다. 약 160MB 압축, 풀면 약 240MB. `models/`는 git 제외다.

```bash
mkdir -p models && cd models
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
tar xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2 && rm *.tar.bz2
cd ..
```

다른 위치(보드의 `~/voice/models/...`)에 있으면 `--model-dir` 또는 `JARVIS_STT_MODEL_DIR`로 지정한다. 폴더에 `model.int8.onnx`와 `tokens.txt`만 있으면 된다.

> 배포 이미지에 든 모델이 `2024-07-17`판인지 `2025-09-09`판인지는 보드를 받은 뒤 파일 크기·sha256으로 확인한다 (확인 필요, STT-02).

## 실행

```bash
python -m services.audio_svc.transcribe models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/test_wavs/ko.wav
python -m services.audio_svc.transcribe data/stt/*.wav --language ko --threads 4
```

출력: 파일별 받아쓴 텍스트, 음성 길이(`audio`), 인식 시간(`stt`), RTF(처리 시간 ÷ 음성 길이, 1보다 작으면 실시간).

- 입력은 **16-bit PCM wav**. 16kHz mono를 권장하고, 다른 샘플레이트는 sherpa-onnx가 내부에서 변환한다. 스테레오는 채널 평균으로 mono로 바꾼다.
  - 변환: `ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 out.wav`
- `--language`는 기본 `ko`(고정). `auto`는 짧은 명령을 다른 언어로 잘못 감지한 사례가 있다 ([STT 평가 recipe](../../recipes/stt-eval.md)의 STT-01 결과).
- `--no-itn`: ITN(Inverse Text Normalization — "삼 분"을 "3분"으로, 문장부호 추가) 끄기.

## 코드에서 쓰기

```python
from services.audio_svc.stt import SenseVoice, read_wav

stt = SenseVoice("models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17", language="ko")
result = stt.transcribe_file("sample.wav")          # 또는 stt.transcribe(samples, 16000)
print(result.text, result.audio_ms, result.stt_ms, result.rtf)
```

`Transcript`의 `text`·`audio_ms`·`stt_ms`는 [interfaces](../../docs/architecture/interfaces.md)의 `stt/text` payload 필드 이름과 같다. 모델 로드는 한 번만 하고 `transcribe()`를 반복 호출한다.

## Spec (STT-01 범위)

| 항목 | 내용 |
|---|---|
| 역할 | float32 mono 샘플 또는 wav 파일 → 받아쓴 텍스트 + 처리 시간 |
| 하지 않는 일 (아직) | 마이크 입력, VAD(발화 구간 자르기), 호출어 판단, 버스 발행 — STT-03·04 |
| 설정 | `--model-dir`(기본 `JARVIS_STT_MODEL_DIR` → `models/...int8-2024-07-17`), `--language`(기본 `ko`), `--threads`(기본 4, 특강 p.34 배치), `--no-itn` |
| 실행 장치 | CPU (sherpa-onnx PyPI 휠). NPU(RKNN) 실행은 별도 빌드가 필요해 STT 비교 실험에서 다룬다 |
| 실패 시 | 모델 파일이 없으면 어떤 파일이 없는지와 받는 방법을 알려 주고 종료(코드 1). wav가 아니거나 16-bit가 아니면 변환 명령을 알려 준다 |
