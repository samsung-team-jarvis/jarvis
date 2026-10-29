# training/llm — LLM 데이터 파이프라인

음성 명령 → Function Call을 학습시킬 데이터를 만든다. 문장마다 손으로 라벨을 붙이지 않고, SUDA 방식 **기획 시트**에서 생성해 정답이 틀릴 수 없게 한다. 사람은 시트를 고치고 다시 생성한다. (PLAN LLM-02~05·14, 발표 p.9 가공 파이프라인)

```bash
python -m training.llm.build_seed       # ① Seed + ⑤ Hard Negative → data/llm/seed_v2.jsonl, hard_negative_v2.jsonl
python -m training.llm.build_dataset    # ②~④ Paraphrase·검증·정규화 → data/llm/dataset_v2.jsonl
python -m training.llm.split_dataset    # ⑥ 분할 → data/llm/split_v2/{train,val,test,calib}.jsonl
```

지금 시트가 만드는 것은 **데이터 v2**(스키마 v0.2: 장치 8종 · 함수 14개)다. `data/llm/*_v1*`은 스키마 v0.1 때의 고정본(장치 3종)으로, 2026-10-02 기준선을 잰 데이터라 그대로 둔다. 지금 시트로는 다시 만들 수 없다.

## 파이프라인

| 단계 | 하는 일 | 파일 |
|---|---|---|
| ① Seed | 템플릿 × 슬롯(장치 부르는 말·세기·시간, 숫자 표기 변형) → Action별 목표만큼. 장치·세기·시간이 고르게 나오도록 돌아가며 뽑는다 | [`plan_sheet.yaml`](./plan_sheet.yaml) → `build_seed.py` |
| ② Paraphrase | 부모 템플릿을 같은 뜻의 다른 말투로 바꿔 쓴 **템플릿** (생성: Claude, 프롬프트는 시트 머리말) | [`paraphrase_sheet.yaml`](./paraphrase_sheet.yaml) |
| ③ 검증·중복 제거 | 스키마 검증, 띄어쓰기·문장부호만 다른 중복 제거, 같은 문장에 정답이 둘이면 실패 | `build_dataset.py` |
| ④ Entity 치환·STT 정규화 | 슬롯 채우기(정답이 자동으로 따라옴) + 서비스와 같은 STT 오인식 사전 적용 (원문은 `meta.raw_instruction`) | `build_dataset.py` |
| ⑤ Hard Negative | 위험 상황·모호·대명사·범위 밖·비슷한 지원 외·부정·STT 오인식 — 따로 둔다 | `plan_sheet.yaml` `hard_negatives` |
| ⑥ 분할 | 가족 단위 Train/Val/Test + 캘리브레이션 | `split_dataset.py` |

## 데이터 형식 (한 줄 = interfaces §3.4)

```json
{"instruction": "두 번째 불을 켜 주세요",
 "context": {"state": "COOKING", "temperature": 175, "detected_objects": ["pan", "burner_on", "hand"], "last_target": null},
 "output": {"action": "TURN_ON", "target": "burner_2"},
 "meta": {"template_id": "on_03_p2", "group": "on_03", "tone": "요청", "source": "paraphrase", "indirect": false, "split": "train"}}
```

- `instruction`은 **호출어를 뺀** 명령 문장 (llm_svc가 넘기는 것과 같다). 학습 정답 문자열은 `to_tokens(output)` → `<jarvis_1>(target=burner_2)<jarvis_end>`.
- `group`(가족) = 부모 템플릿 id. 바꿔 쓴 템플릿은 부모의 정답·장치 목록을 물려받는다.
- Hard Negative의 `meta`: `category`, `expect_guard`(Guard에 갔을 때 기대 판정 — FUS-03 테스트에도 씀), `note`.

## 규칙

- **위험 상황의 위험 명령도 정답은 말 그대로의 명령**이다 ("DANGER인데 2번 화구 세게" → `SET_LEVEL burner_2 3`). 막는 것은 Safety Guard ([decision](../../docs/decisions/2026-10-02-llm-literal-guard-decides.md)).
- **스키마에 없는 값·조합을 말했을 때**: 되물어서 풀리면 되묻기("후드 5단으로", "에어컨 24도로" → 세기 되묻기), 되물어도 풀리지 않으면 지원 외("10분 뒤에 에어컨 꺼줘" — 에어컨에는 타이머가 없다).
- **STT 테스트 대본(`data/stt/script.csv`)과 같은 문장은 넣지 않는다** — 넣으면 STT→Action 평가가 부풀려진다.
- **고르게 뽑는다**: 한 Action 안에서 정답의 (장치, 세기) 칸을 돌아가며 뽑고, 칸 안에서는 템플릿을 돌아가며 뽑는다. 부르는 말이 많은 장치(화구 6개 표현)나 한 장치만 다루는 템플릿이 많은 장치(음악)가 몇 배씩 많아지지 않게 한다.
- **분할은 가족 단위**: 부모와 그 Paraphrase는 같은 split → 비슷한 문장이 train·test에 같이 안 들어간다. 묶음별로 목표 비율(70/15/15%)에 맞춰 배정하고, 비는 split은 가장 작은 가족을 옮겨 채운다. 묶음은 Action이고, **되묻기는 종류별**(무엇을 하려다 무엇이 빠졌나), **간접 발화는 Action별로 따로**, Hard Negative는 범주 + 기대 판정별이다.
- **Test는 고정**이고 비교할 때만 쓴다. 오류 분석·규칙 조정은 val로 한다. 데이터 버전을 올릴 때 **앞 버전에 있던 가족은 같은 split에 그대로 두고** 새 가족만 배정한다 (`split_dataset.py --base`) — 규칙 파서를 v1 val로 고쳤으므로 v1의 train·val 가족이 v2 test로 넘어가면 안 된다.
- 캘리브레이션(양자화용)은 **train에서만** Action 비율대로 약 500건 (특강 권장 300~1,000, 입력 형식은 LLM-08에서).
- **템플릿 id는 뜻을 바꾸지 않는다.** 정답이 바뀐 템플릿은 지우고 새 id로 만든다.
- 시트를 바꾸면 세 명령을 다시 실행해 커밋한다 — 테스트가 커밋된 데이터와 시트가 같은지 검사한다.

## 검수 (사람)

```bash
python -m training.llm.build_seed --review-csv seed_review.csv       # Seed + Hard Negative
python -m training.llm.build_dataset --review-csv para_review.csv    # Paraphrase
```

Excel에서 열어 `검수(OK/수정)`·`메모` 칸에 표시한다. **문장을 직접 고치지 말고**, 해당 `template_id`의 템플릿이나 슬롯 표현을 시트에서 고친 뒤 다시 생성한다.

### Hard Negative v2 검수 (LLM-03, #98)

기록: [`review/hard_negative_v2_review.csv`](./review/hard_negative_v2_review.csv) — 위 CSV와 같은 열에 `규칙 파서(참고)` 열을 더했다. `tests/training/test_hard_negative.py`가 기록이 지금 데이터와 같은지 검사한다 (데이터를 다시 만들면 다시 검수한다).

**1차 검수 (2026-10-09, Claude가 최지환 요청으로 수행 — 사람 확인 대기)**: 165건 모두 정답이 맞다고 봤다 (`OK(1차)`). 스키마·대명사의 직전 장치·위험 상황의 Guard 기대 판정을 자동 검사로도 확인했다.

| 제안 | 내용 | 영향 |
|---|---|---|
| P1 | 결제 2건(`hn_pay_01`·`hn_pay_02`)에 `expect_guard: ASK` — Safety Guard는 결제 요청을 항상 확인한다 (#96) | Hard Negative 분할 묶음(범주 + 기대 판정)이 바뀜 |
| P2 | 위험 상황에 없는 경우 추가: `SAFE_STOP` 상태, 위험 중 가열 장치가 아닌 장치(조명·음악) 켜기 = ALLOW, 위험 중 긴급 정지·위험 확인 | 새 가족 추가 |
| P3 | 슬롯 표현 "이번 화구"(= 2번 화구)는 "이번(this) 화구"로도 들린다 — 빼거나 "2번 화구"로 | Seed·Paraphrase 전체의 `burner_2` 표현이 바뀜 |

- **세 제안 모두 데이터를 다시 만들고 다시 분할해야 한다.** test에도 Hard Negative 29건이 있어 기준선·LoRA 수치(#86·#88)와 비교가 끊길 수 있다. 진행 중인 LoRA v2(#92)와 시점을 맞춰 이현종과 정한 뒤 반영한다.
- 규칙 파서가 정답과 다르게 내는 68건(대명사 23 · 부정 16 · 범위 밖 12 · 모호 8 · 비슷한 지원 외 8 · 결제 1)은 데이터 오류가 아니라 파서의 한계다 (대명사는 문맥이 없어 되묻는다, "끄지 마"를 끄기로 읽는다, "오천 원 계산해줘"를 결제로 못 읽는다 등). 파서 개선 여부는 ②가 정한다.

## v2 현황 (2026-10-06, 사람 검수 전)

| 구분 | 수 |
|---|---|
| 데이터 | **3,015** (Seed 844 · Paraphrase 2,171) — 가족 246 · 템플릿 462 · 간접 발화 155 |
| Action | TURN_ON 420 · TURN_OFF 420 · SET_LEVEL 480 · SET_TIMER 340 · CANCEL_TIMER 120 · CHECK_STATUS 240 · CHECK_RISK 105 · EMERGENCY_STOP 139 · ASK_CLARIFY 300 · UNSUPPORTED 180 · CHECK_AMOUNT 90 · REQUEST_PAYMENT 81 · CONFIRM 50 · DENY 50 |
| 장치 | 켜기 52~53 · 끄기 46~48(전체 포함 9칸) · 세기 59~61 — 장치 8종이 거의 같은 수. 세기는 (장치, 세기) 24칸이 19~21 |
| 되묻기 300 | 장치 빠짐 146 · 세기 빠짐 73 · 의도 모름 43 · 시간 빠짐 38 |
| 타이머 시간 | 26종 (10초~60분) |
| 어투 | 명령 1,425 · 요청 980 · 평서 610 |
| Hard Negative | 165 — 위험 상황 34 · 대명사 25 · 긴급 아님 21 · 범위 밖 16 · 비슷한 지원 외 16 · 부정 16 · 군말 16 · 모호 14 · 결제 4 · STT 오인식 3 |

| split | 전체 | 일반 | Hard Negative | 가족 |
|---|---|---|---|---|
| train | 2,198 | 2,106 | 92 | 144 |
| val | 508 | 464 | 44 | 77 |
| test | 474 | 445 | 29 (Guard REJECT 8) | 75 |
| calib (train에서) | 502 | | | |

- 목표보다 모자람: CHECK_RISK −5, EMERGENCY_STOP −1, REQUEST_PAYMENT −9 (고정 문장 가족이라 표현이 적음).
- 일부러 넣은 경계 사례: "타이머 정지"=타이머 취소, "음악 멈춰"=음악 끄기(긴급 정지 아님), "만 이천 원 결제해줘"=결제 요청(금액은 단말의 값), "결제 취소"=아니요, "오늘 매출 얼마야"·"에어프라이어 켜줘"·"다음 곡 틀어줘"=지원 외, "응 후드 꺼줘"=후드 끄기(네 아님).

### v1에서 바뀐 것

| 항목 | v1 | v2 |
|---|---|---|
| 범위 | 장치 3종 · 함수 10개 | 장치 8종 · 함수 14개 (튀김기·조명·에어컨·선풍기·음악, 금액 확인·결제 요청·네·아니요) |
| 정답이 바뀐 가족 | 조명·에어컨·음악·볼륨 문장이 "지원 외" | 지우고 장치 명령으로 새로 만듦 (지운 id: `un_02` `un_31` `un_35` `hn_nm_01` `hn_nm_03` `hn_nm_05`) |
| 장치별 수 | 부르는 말이 많은 장치가 더 많이 뽑힘 | 장치·세기 칸을 돌아가며 뽑아 거의 같음 |
| 되묻기 | 230건 중 172건이 "세기 빠짐" | 종류마다 가족을 여럿 두어 한 종류가 35%를 넘지 않음 |
| 분할 | Action으로만 묶음 → **train에 "장치 빠짐" 되묻기 3건 · 시간 1건 · 의도 모름 1건, 간접 발화 8건뿐** (나머지는 val·test) | 되묻기 종류·간접 발화를 따로 묶어 모든 split에 들어감 (train: 장치 빠짐 91 · 세기 52 · 시간 31 · 의도 모름 23, 간접 발화 106) |
| 타이머 시간 | 13종 | 26종 |

v1의 가족 181개 중 175개가 v2에 남았고 모두 v1과 같은 split에 있다. 새 가족 121개만 새로 배정했다.

### 남은 약점

- 사람 검수 전이다. 문장은 템플릿 조합이라 "노래 몇 단인지 알려 줘"처럼 어색한 것이 섞여 있다.
- 간접 발화가 5%(155건)로 적다. v1의 간접 가족이 val에 몰려 있던 것(고정)은 그대로다.
- Hard Negative test가 29건이고 Unsafe Rate 표본은 여전히 8건이다.
- 결제·네·아니요는 문장이 짧고 고정돼 있어 가족당 문장 수가 적다. "네"가 무엇에 대한 대답인지는 데이터에 없다 (Safety Guard가 판단 — FUS-03).
- 실제 음성을 받아쓴 문장(`source: real`)은 아직 없다.

## 평가

기본 모델·규칙 파서 평가는 [`bench/llm_eval.py`](../../bench/README.md). HF 모델 평가는 서비스 환경과 분리된 가상환경을 쓴다 (`requirements-eval.txt` — torch가 크다):

```bash
python3.11 -m venv .venv-llm && .venv-llm/bin/pip install -r training/llm/requirements-eval.txt
```

## 학습 (LLM-07)

LoRA로 학습해 베이스에 병합하고 fp16 HF 모델로 저장한다. 같은 가상환경(`.venv-llm`)을 쓴다.

```bash
.venv-llm/bin/python -m training.llm.train_lora --limit 32 --epochs 1        # 먼저 끝까지 도는지 (1분 안쪽)
.venv-llm/bin/python -m training.llm.train_lora                              # Qwen3-0.6B, 데이터 v2 → runs/llm/llm_qwen3-0.6b_jarvis_v1/
.venv-llm/bin/python -m bench.llm_eval --engine hf --finetuned --model runs/llm/llm_qwen3-0.6b_jarvis_v1 --split val
```

- **입력 형식**: 짧은 지시문 + 사용자 메시지, 예시 없음. 정답은 함수 토큰 + 모델의 끝 토큰이고 loss는 정답에만 건다 ([decision](../../docs/decisions/2026-10-06-llm-input-format.md), 문장은 [`services/llm_svc/prompt.py`](../../services/llm_svc/prompt.py)). 평가할 때는 `--finetuned`로 같은 입력을 준다.
- **설정**: LoRA r=16 · alpha=32 · dropout 0.05, attention·MLP의 선형층 7종, lr 2e-4 (warmup 5% → cosine), 배치 16(4×4), 3 epoch, seed 0. 2026-10-05 Mac 시험 학습과 같은 값이다.
- **저장물** `runs/llm/<이름>/`: 병합된 fp16 모델, 토크나이저, `train_log.json`(설정·epoch별 loss·실제 입력 예시·끝 토큰). git에 넣지 않고 [등록부](../../docs/artifacts.md)에 한 줄 남긴다.
- **어디서**: Mac(16GB, MPS)에서는 Qwen3-0.6B까지 확인했다 (fp32 학습). 더 큰 베이스는 [`train_lora.ipynb`](../colab/train_lora.ipynb) (Colab GPU, 미검증).

### LoRA v1 결과 (2026-10-06, Mac 참고값)

| 데이터 v2 | Action Acc | Entity Acc | Valid Rate |
|---|---|---|---|
| test (n=474) | 72.6% | 71.1% | 96.0% |
| val (n=508) | 83.9% | 83.1% | 97.6% |

- 같은 test에서 기본 모델(지시문 + 예시)은 25.7%, 규칙 파서는 82.5%다. 학습으로 크게 올랐지만 규칙 파서보다는 낮다.
- loss: train 0.42 → 0.010 → 0.002, val 0.071 → 0.060 → 0.068 (3 epoch째 val이 다시 오름 — 외우기 시작).
### val 오류 유형 (LLM-10, Mac fp16)

`bench/llm_errors.py`로 분류했다 (유형 정의는 파일 머리말). 한 오류는 한 유형으로만 세고, 아래 세 줄은 겹쳐 센다. **val로만 분석한다.**

| 유형 | 규칙 파서 | LoRA v1 | LoRA v1 예시 |
|---|---|---|---|
| **틀린 수 / 508** | **108** | **86** | |
| 형식 깨짐 | 0 | 0 | |
| 규칙 위반 | 0 | 12 | "알람 꺼 주세요" → `target=alarm` (없는 장치), "후드 가동해줘" → 세기 함수인데 세기 없음 |
| 빠진 값 채움 | 9 | 2 | "음악 더 작게 해 줘" → 세기 1 (되물어야 함) |
| 불필요한 되묻기 | 34 | 10 | "지금 뭐 켜져 있어" → 장치를 되물음 (전체 상태 확인이어야 함) |
| 지원 외를 실행 | 9 | 19 | "고마워" → 네, "주문 받아 줘" → 결제 요청, "환기팬 끄지 마" → 끄기 |
| 지원 외로 거절 | 33 | 11 | "환풍기 좀 돌려 주세요", "알람 꺼" → 지원 외 |
| 다른 함수 | 21 | 29 | "타이머 멈춰" → 긴급 정지, "냉방 멈춰" → 긴급 정지, "안전 점검해 주세요" → 긴급 정지 |
| 장치 틀림 | 2 | 0 | |
| 값 틀림 | 0 | 3 | "더 세게 해 줘" → 세기를 되물음 (장치를 되물어야 함) |
| (겹쳐 셈) 대명사 실패 | 0 | 1 | |
| (겹쳐 셈) 긴급 정지 오판 | 6 | 18 | 긴급 정지가 아닌데 긴급 정지, 또는 그 반대 |
| (겹쳐 셈) 틀린 실행 | 34 | 42 | 장치·결제를 움직이는 함수를 냈는데 틀림 — 안전과 관련된 오류 |

- LoRA v1이 많이 틀린 가족: `hn_nu_01`("냉방 멈춰"류) 8, `ct_07`("타이머 멈춰"류) 7, `st_04`("지금 뭐 켜져 있어"류) 7, `ask_30`("어 그러니까"류) 7, `hn_ng_01`("끄지 마"류) 7, `ct_04` 6, `un_38` 5, `un_22` 4.
- 규칙 파서와 LoRA v1은 틀리는 곳이 다르다. 규칙 파서는 키워드가 없는 말(돌려 말하기, 처음 보는 동사)을 지원 외로 거절하거나 되묻고, LoRA v1은 비슷한 함수끼리 헷갈린다 (멈춰·정지가 들어가면 긴급 정지).
- **틀린 실행이 42건으로 규칙 파서(34건)보다 많다.** 장치를 잘못 움직이는 오류라 Safety Guard가 막아야 할 몫이 커진다.

**다음 보강 (LLM-11)** — val에서 본 유형으로 train에만 새 문장을 더한다 (val·test는 그대로):

1. 타이머 취소의 다른 말투와 "알람" (멈춰·정지·필요 없어 + 타이머/알람) — 긴급 정지·위험 확인과 헷갈림
2. 매장 장치를 "멈춰·정지·그만"으로 끄는 말 — 긴급 정지와 헷갈림
3. 하지 말라는 말("끄지 마", "켜지 마", "틀지 마") — 끄기·켜기로 실행함
4. 인사·칭찬·가게 일("고마워", "주문 받아 줘") — 네·결제 요청으로 실행함
5. 장치 없이 전체 상태를 묻는 말 — 장치를 되물음
6. 처음 보는 동사("돌려", "가동", "작동")
7. 군말·머뭇거림 — 네로 답함

보드의 양자화 모델은 LLM-08 뒤에 같은 도구로 다시 분류한다.

## 보강과 LoRA v2 (LLM-11)

val 오류 유형(위 표)마다 새 템플릿을 [`augment_sheet.yaml`](./augment_sheet.yaml)에 쓰고 train에만 더한다. **데이터 v2 시트는 고치지 않는다** — 고치면 val·test가 바뀌어 같은 test로 비교할 수 없다.

```bash
python -m training.llm.build_augment                                                  # → data/llm/augment_v1.jsonl
.venv-llm/bin/python -m training.llm.train_lora --extra data/llm/augment_v1.jsonl --name llm_qwen3-0.6b_jarvis_v2
```

- **누수 방지**: val·test·STT 대본과 띄어쓰기를 지운 문장이 같거나, 글자 두 개 조각이 60% 이상 겹치는 문장은 뺀다 (테스트로 확인). train과 같은 문장도 뺀다.
- 템플릿 하나에서 최대 12문장 (장치·값을 돌아가며) — 슬롯이 많은 템플릿이 보강을 다 차지하지 않게.
- 보강 v1: **208문장** (템플릿 21개, 비슷해서 뺀 문장 18개). 겨냥한 유형: 지원 외를 실행 74 · 다른 함수 62 · 규칙 위반 24 · 지원 외로 거절 24 · 불필요한 되묻기 12 · 값 틀림 12.

### 결과 (2026-10-06, Mac 참고값)

바꾼 것은 학습 데이터 하나다 (베이스·설정·지시문·평가 모두 v1과 같음).

| 데이터 v2 test (n=474) | Action Acc | Entity Acc | Valid Rate | 틀린 수 | 틀린 실행 |
|---|---|---|---|---|---|
| 규칙 파서 | 82.5% | 82.1% | 100% | | |
| LoRA v1 | 72.6% | 71.1% | 96.0% | 137 | 20 |
| **LoRA v2** (+ 보강 208) | **78.5%** | **77.6%** | **96.6%** | **106** | **11** |

- test에서 6%p 올랐고, 장치·결제를 잘못 움직이는 오류(틀린 실행)가 20건에서 11건으로 줄었다. 아직 규칙 파서보다 낮다.
- test의 "불필요한 되묻기"는 42건 그대로다 (오류 유형 수만 셌고, test 문장은 보지 않았다).
- val은 83.9% → 94.9%, 틀린 수 86 → 29건. **보강 방향을 val 오류로 정했으므로 v2의 val 수치는 낙관적이다.** 비교는 test로 한다.
- loss: val 0.038 → 0.024 → 0.021 (v1과 달리 3 epoch째에도 내려갔다).

## 데이터 양·다양성 실험 (LLM-15)

다른 팀(기능 5개)은 기능 하나에 학습 문장이 약 1,500개, 우리는 약 170개다. 문장을 늘리는 방법 두 가지를 **같은 수(875문장)**로 비교했다. 둘 다 train에만 더하고 val·test는 그대로다.

```bash
python -m training.llm.build_augment --sheet training/llm/variety_sheet.yaml \
    --out data/llm/variety_v1.jsonl --exclude data/llm/augment_v1.jsonl     # B: 새 말투
python -m training.llm.build_more                                           # A: 같은 말투 (B와 같은 수)
.venv-llm/bin/python -m training.llm.train_lora --extra data/llm/augment_v1.jsonl \
    --extra data/llm/variety_v1.jsonl --name llm_qwen3-0.6b_jarvis_v3b
```

- **A — 같은 말투 더** ([`build_more.py`](./build_more.py)): 가족이 train인 템플릿에서 아직 안 쓴 장치·세기·시간 조합을 뽑는다. 문장이 고정된 템플릿(긴급 정지·결제)은 더 뽑을 게 없어 켜기·타이머·되묻기에 몰린다.
- **B — 새 말투** ([`variety_sheet.yaml`](./variety_sheet.yaml)): 새 템플릿 131개, Action 14개에 고르게. val·test 오류를 보고 정하지 않았다 (생성: Claude, 사람 검수 전). 비슷해서 뺀 문장 934개.

### 결과 (2026-10-13, Mac 참고값)

바꾼 것은 더한 문장 묶음 하나다 (베이스·설정·지시문·평가 모두 LoRA v2와 같음. 문장이 늘어 갱신 횟수는 453 → 618).

| 데이터 v2 test (n=474) | Action Acc | Entity Acc | Valid Rate | 틀린 수 | 틀린 실행 |
|---|---|---|---|---|---|
| 규칙 파서 | 82.5% | **82.1%** | 100% | 85 | 13 |
| LoRA v2 (기준, 2,406문장) | 78.5% | 77.6% | 96.6% | 106 | 11 |
| v3a: A 같은 말투 +875 | 79.3% | 75.3% | 97.0% | 117 | **33** |
| **v3b: B 새 말투 +875** | **83.5%** | 80.6% | **99.8%** | **92** | 12 |

- **양보다 말투 다양성이다.** 같은 수를 더했는데 A는 틀린 수가 늘고(106 → 117) B는 줄었다(106 → 92).
- A는 "지원 외로 거절"이 26 → 6건으로 줄었지만 "다른 함수"가 11 → 33건으로 늘어, **틀린 실행이 3배**가 됐다. 같은 템플릿을 더 보면 처음 보는 말에도 실행하는 쪽으로 기운다.
- B는 Action이 처음으로 규칙 파서를 넘었지만 Entity(80.6%)는 아직 낮다. "값 틀림"이 3 → 12건 — 주로 되묻기에서 빠진 항목(`missing`)을 틀린다.
- test는 오류 유형 수만 셌고 문장은 보지 않았다. val: v3a 94.5% · v3b 95.9% (v2 94.9%).

### v3b의 val 오류 (22건) — 다음 보강의 방향

| 묶음 | 건수 | 예 |
|---|---|---|
| 긴급 정지를 다른 함수로 | 4 | "스탑" → 네, "그만해" → 아니요, "사고 났어 다 꺼" → 끄기(all) |
| 머뭇거림을 "네"·지원 외로 | 4 | "음 그러니까", "아 그러니까" → 네 |
| 되물어야 하는데 실행·거절 | 7 | "타이머 90분" → 90분(범위 밖), "에어컨 18도로" → 지원 외, "음악 더 작게" → 세기 1 |
| 가게 일을 결제 함수로 | 4 | "주문 받아 줘" → 네, "오늘 매출 얼마야" → 금액 확인 |
| 그 밖 | 3 | "요리 다 끝났어 불 다 꺼도 돼" → 장치 되묻기 |

## 새 말투 v2와 LoRA v4 (LLM-16)

v3b의 val 오류(위 표)와 페르소나 말버릇으로 새 템플릿 63개를 [`variety_sheet_v2.yaml`](./variety_sheet_v2.yaml)에 쓰고 train에만 526문장을 더했다 (비슷해서 뺀 문장 608개). val·test는 그대로다.

```bash
python -m training.llm.build_augment --sheet training/llm/variety_sheet_v2.yaml --out data/llm/variety_v2.jsonl \
    --exclude data/llm/augment_v1.jsonl --exclude data/llm/variety_v1.jsonl
.venv-llm/bin/python -m training.llm.train_lora --extra data/llm/augment_v1.jsonl --extra data/llm/variety_v1.jsonl \
    --extra data/llm/variety_v2.jsonl --name llm_qwen3-0.6b_jarvis_v4
```

- 긴급 빠른 경로(`services/safety_guard/emergency.py`)가 긴급 정지로 처리하는 말은 정답도 긴급 정지인지 테스트로 확인한다 (`tests/training/test_variety_sheets.py`).

### 결과 (2026-10-13, Mac 참고값)

바꾼 것은 더한 문장 묶음 하나다 (v3b 학습 데이터 + `variety_v2.jsonl`, 3,807문장. 갱신 횟수 618 → 714, 49분).

| 데이터 v2 test (n=474) | Action Acc | Entity Acc | Valid Rate | 틀린 수 | 틀린 실행 |
|---|---|---|---|---|---|
| 규칙 파서 | 82.5% | 82.1% | 100% | 85 | 13 |
| v3b (새 말투 v1) | 83.5% | 80.6% | 99.8% | 92 | 12 |
| **v4 (+ 새 말투 v2)** | **86.9%** | **86.5%** | 97.5% | **64** | **11** |

- **Entity도 처음으로 규칙 파서를 넘었다** (82.1% → 86.5%). 틀린 실행은 늘지 않았다 (12 → 11).
- 줄어든 것: 불필요한 되묻기 37 → 20, 다른 함수 14 → 6, 값 틀림 12 → 2, 지원 외로 거절 24 → 20. 되묻기(ASK_CLARIFY) Entity 50.0% → 88.6%.
- 늘어난 것: **규칙 위반 1 → 12** (모양은 맞는데 없는 이름·인자 — Guard가 막지만 Valid가 99.8% → 97.5%로 내려갔다).
- 그대로인 것: 긴급 정지 오판 7 → 7 (EMERGENCY_STOP Action 71.4%), SET_LEVEL 66.0%. 실제 흐름에서는 긴급 단어를 빠른 경로가 LLM보다 먼저 처리한다.
- val은 98.8% / 98.8% / 100% (v3b 95.9%)이지만 **v2 시트를 v3b val 오류로 만들었으니 낙관적이다.** 비교는 test로 한다.
- test는 v2부터 다섯 번 비교에 썼다. 비교에만 쓰고 보강 방향은 정하지 않았지만, 같은 test로 고르기를 거듭할수록 test도 조금씩 낙관적이 된다.
- 기록: 이 실험의 오류 집계 중 `bench/llm_errors.py`가 test 오답 예시 문장 16개를 한 번 출력했다. 그 문장은 보강에 쓰지 않는다. 그 뒤로 test는 `--counts-only`(건수 표만)로 센다.

### v4의 val 오류 (6건)

| 묶음 | 건수 | 예 |
|---|---|---|
| 머뭇거림을 네·아니요로 | 3 | "어/음/아 그러니까" → 네·아니요 (되물어야 함) |
| 결제 요청으로 실행 | 2 | "주문 확인해 줘"(지원 외), "결제하지 마"(아니요) → 결제 요청 — "결제할까요?" 확인 단계가 막는다 |
| 끄기를 되물음 | 1 | "요리 다 끝났어 불 다 꺼도 돼" → 장치 되묻기 (v3b부터 그대로) |

- 틀린 실행은 val에서 12 → 4건이다. 남은 넷 중 둘이 결제 요청이라 다음 보강은 "결제하지 마"류 부정과 주문·매출 같은 가게 일이다.

## 새 말투 v3와 LoRA v5 (LLM-17) — 같은 test로 마지막 비교

v4의 val 오류 6건만 보고 새 템플릿 18개를 [`variety_sheet_v3.yaml`](./variety_sheet_v3.yaml)에 쓰고 train에만 162문장을 더했다: 결제를 하지 말라는 말(→ 아니요, 기존 보강에 하나도 없었다), 주문·결제 내역(→ 지원 외), 머뭇거림만(→ 되묻기)과 머뭇거린 뒤 네·아니요, "불 다 꺼"(→ 전체 끄기)와 "불 꺼"(→ 장치 되묻기)의 대비. test에서만 늘어난 규칙 위반은 겨냥하지 않았다.

```bash
python -m training.llm.build_augment --sheet training/llm/variety_sheet_v3.yaml --out data/llm/variety_v3.jsonl \
    --exclude data/llm/augment_v1.jsonl --exclude data/llm/variety_v1.jsonl --exclude data/llm/variety_v2.jsonl
.venv-llm/bin/python -m training.llm.train_lora --extra data/llm/augment_v1.jsonl --extra data/llm/variety_v1.jsonl \
    --extra data/llm/variety_v2.jsonl --extra data/llm/variety_v3.jsonl --name llm_qwen3-0.6b_jarvis_v5
```

### 결과 (2026-10-13, Mac 참고값)

바꾼 것은 더한 문장 묶음 하나다 (v4 학습 데이터 + `variety_v3.jsonl`, 3,969문장. 갱신 횟수 714 → 747, 52분).

| 데이터 v2 test (n=474) | Action Acc | Entity Acc | Valid Rate | 틀린 수 | 틀린 실행 | 긴급 정지 오판 |
|---|---|---|---|---|---|---|
| 규칙 파서 | 82.5% | 82.1% | 100% | 85 | 13 | 8 |
| v4 | 86.9% | 86.5% | 97.5% | 64 | 11 | 7 |
| v5 (+ 새 말투 v3) | 87.3% | 86.3% | 98.3% | 65 | 10 | 8 |

- **v4와 v5는 같다고 본다.** 차이가 문장 한두 개(0.2~0.4%p)라 학습 한 번의 흔들림보다 작다고 말할 수 없다.
- val도 6 → 6건이다. v4가 틀린 6건 중 5건은 고쳤지만 다른 5건이 새로 틀렸다 ("스탑" → 네, "타이머 90분" → 90분, "타이머" → 타이머 취소, "계란 반숙으로 7분만 알려줘" → 타이머에 장치 자리만 넣음(규칙 위반), "주문 들어왔어" → 결제 요청). 고친 곳 옆이 다시 틀리는 모양이라, **val 오류를 보고 문장을 더하는 방법은 이 모델(0.6B LoRA)에서 한계에 왔다.**
- 그래서 대표 모델은 **v4로 둔다** (더 적은 데이터로 같은 결과). v5는 기록만 남긴다.
- 같은 test로 고르는 일은 여기서 멈춘다. 다음 비교는 보드 변환(LLM-08) 뒤, 또는 새 test에서 한다.
- 남은 방향 (데이터를 더 넣는 것 말고): 출력 검증 실패(규칙 위반·범위 밖 값)를 규칙 파서나 되묻기로 넘기는 처리, 더 큰 모델(1B급), 여러 seed로 학습해 흔들림 재기.
