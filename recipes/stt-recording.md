# Recipe: STT 테스트 세트 녹음 (STT-05)

팀원이 직접 읽고 따라 하는 녹음 안내다. 녹음한 음성으로 STT 정확도(CER), 호출어 인식, "음성 → 명령" 정확도를 잰다 ([STT 평가](./stt-eval.md)).

## 한눈에

| 항목 | 내용 |
|---|---|
| 화자 | 4~6명 (팀원 4명 + 동의한 지인). 이름 대신 `spk01`… ID를 쓴다 |
| 대본 | [`data/stt/script.csv`](../data/stt/script.csv) 40문장 (명령 34 + 호출어 없는 문장 6) |
| 소음 | 4종: `quiet` · `hood` · `frying` · `mixed` |
| 분량 | 화자 1명 = 40문장 × 4소음 = 160발화, **약 20~30분**. 5명이면 800발화 |
| 결과 | `data/stt/<화자>/<소음>_<마이크>/<문장>.wav` + `data/stt/manifest.csv` |

## 1. 준비 (한 번)

```bash
python3 scripts/setup.py                 # 개발 환경 (처음이면)
python -c "import sounddevice; print(sounddevice.query_devices())"   # 마이크 번호 확인
```

- **마이크**: 시연에 쓸 USB 핀마이크(`--mic pin`). 마이크 비교(STT-09)를 할 때만 같은 문장을 다른 마이크로 한 번 더 (노트북 내장 마이크는 `--mic macbook`).
- **위치**: 마이크를 보드를 놓을 자리(조리대 옆)에 고정하고, 화자는 조리하는 위치(마이크에서 50cm~1m)에서 말한다. 녹음 중에 거리를 바꾸지 않는다.
- **Mac**: 처음 녹음할 때 터미널에 마이크 권한을 허용해야 한다 (시스템 설정 > 개인정보 보호 및 보안 > 마이크 → 터미널 켜고 터미널 재시작). 권한이 없으면 도구가 "소리가 전혀 안 들어왔어요"라고 알려 준다.
- **동의**: 지인 화자는 "팀 프로젝트 평가용으로만 쓰고 팀 밖에 공유하지 않는다"는 데 동의를 받는다.

## 2. 소음 만드는 법

| 소음 | 방법 | 주의 |
|---|---|---|
| `quiet` | 조용한 방 (에어컨·음악 끄기) | |
| `hood` | 주방 후드(환풍기)를 **최대**로 켬. 후드가 없으면 선풍기 최대를 마이크에서 1m | 매번 같은 세기 |
| `frying` | 프라이팬에 기름을 두르고 실제로 볶거나 튀기는 소리. 어려우면 튀김 소리 녹음을 휴대폰으로 마이크에서 1m 거리, 중간 음량으로 재생 | 불 옆을 떠나지 않는다. 녹음하는 사람과 조리하는 사람을 나눈다 |
| `mixed` | `hood` + `frying` 동시에 | |

소음 원본(재생용 파일)을 쓰면 무엇을 썼는지 PR에 적는다 (같은 소음으로 다시 재기 위해).

## 3. 녹음

```bash
python -m bench.record_stt --speaker spk02 --noise quiet --mic pin
python -m bench.record_stt --speaker spk02 --noise hood  --mic pin
python -m bench.record_stt --speaker spk02 --noise frying --mic pin
python -m bench.record_stt --speaker spk02 --noise mixed --mic pin
```

- 화면에 문장이 나오면 **Enter → 문장을 말함 → Enter**. 길이·크기를 보여 주면 **Enter=저장 / r=다시**.
- `s`=이 문장 건너뛰기, `q`=그만. 중간에 그만둬도 같은 명령을 다시 실행하면 **남은 문장부터** 이어서 한다.
- 너무 짧거나 작거나 잘리면(클리핑) 도구가 알려 주고 다시 녹음한다.
- 문장은 **적힌 대로** 자연스럽게 읽는다. 숫자는 편하게 읽는다 ("3분" → "삼 분"). 틀리게 읽었으면 `r`.
- 마이크 장치가 기본값이 아니면 `--device <번호>`.

## 4. 분할 (화자 단위)

| 화자 | split | 용도 |
|---|---|---|
| `spk01` 1명 | `val` (`--split val`) | VAD·호출어 변형·정규화를 **조정할 때만** 본다 (STT-10·11) |
| 나머지 | `test` (기본) | 최종 비교에만 쓴다 (STT-07~09, FUS-06) |

**test 녹음을 보고 규칙 파서·호출어 목록·LLM 데이터를 고치지 않는다.** 고치면 그 test로 잰 정확도가 부풀려진다 ([experiment](../docs/workflows/experiment.md) 원칙 2). 고칠 근거는 `val`에서 찾는다.

화자 ID와 실제 이름의 대응은 저장소에 적지 않는다 (녹음 담당자만 보관).

## 5. 끝나면

```bash
python -m bench.stt_eval data/stt/manifest.csv --split test       # 바로 측정해 보기
cd data && zip -r ../data_stt_test_v1_spk02.zip stt/spk02 && cd ..
python3 scripts/artifact_info.py data_stt_test_v1_spk02.zip          # 등록부 한 줄
```

- wav는 git에 넣지 않는다 (자동으로 막힘). 압축 파일을 이현종에게 직접 전달하고 [등록부](../docs/artifacts.md)에 한 줄 추가한다.
- `data/stt/manifest.csv`는 커밋한다 (경로·문장·정답만 들어 있음). 여러 명이 동시에 녹음하면 각자 PR에서 manifest 충돌이 날 수 있으니 한 명씩 머지한다.
