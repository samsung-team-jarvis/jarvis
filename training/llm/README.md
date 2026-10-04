# training/llm — LLM 데이터 파이프라인

음성 명령 → Function Call을 학습시킬 데이터를 만든다. 문장마다 손으로 라벨을 붙이지 않고, SUDA 방식 **기획 시트**에서 생성해 정답이 틀릴 수 없게 한다. 사람은 시트를 고치고 다시 생성한다. (PLAN LLM-02~05, 발표 p.9 가공 파이프라인)

```bash
python -m training.llm.build_seed       # ① Seed + ⑤ Hard Negative → data/llm/seed_v1.jsonl, hard_negative_v1.jsonl
python -m training.llm.build_dataset    # ②~④ Paraphrase·검증·정규화 → data/llm/dataset_v1.jsonl
python -m training.llm.split_dataset    # ⑥ 분할 → data/llm/split_v1/{train,val,test,calib}.jsonl
```

## 파이프라인

| 단계 | 하는 일 | 파일 |
|---|---|---|
| ① Seed | 템플릿 × 슬롯(장치 부르는 말·세기·시간, 숫자 표기 변형) → Action별 목표만큼 | [`plan_sheet.yaml`](./plan_sheet.yaml) → `build_seed.py` |
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
- **STT 테스트 대본(`data/stt/script.csv`)과 같은 문장은 넣지 않는다** — 넣으면 STT→Action 평가가 부풀려진다.
- **분할은 가족 단위**: 부모와 그 Paraphrase는 같은 split → 비슷한 문장이 train·test에 같이 안 들어간다. Action별(Hard Negative는 범주 + 기대 판정별)로 목표 비율(70/15/15%)에 맞춰 배정하고, 비는 split은 가장 작은 가족을 옮겨 채운다.
- **Test는 고정**이고 비교할 때만 쓴다. 오류 분석·규칙 조정은 val로 한다. 캘리브레이션(양자화용)은 **train에서만** Action 비율대로 약 500건 (특강 권장 300~1,000, 입력 형식은 LLM-08에서).
- 시트를 바꾸면 세 명령을 다시 실행해 커밋한다 — 테스트가 커밋된 데이터와 시트가 같은지 검사한다.

## 검수 (사람)

```bash
python -m training.llm.build_seed --review-csv seed_review.csv       # Seed + Hard Negative
python -m training.llm.build_dataset --review-csv para_review.csv    # Paraphrase
```

Excel에서 열어 `검수(OK/수정)`·`메모` 칸에 표시한다. **문장을 직접 고치지 말고**, 해당 `template_id`의 템플릿이나 슬롯 표현을 시트에서 고친 뒤 다시 생성한다.

## v1 현황 (2026-10-02, 사람 검수 전)

| 구분 | 수 |
|---|---|
| 데이터 | **2,234** (Seed 627 · Paraphrase 1,607) — 가족 150 · 템플릿 269 · 간접 발화 156 |
| Action | TURN_ON 320 · TURN_OFF 320 · SET_LEVEL 340 · SET_TIMER 320 · CANCEL_TIMER 120 · CHECK_STATUS 180 · CHECK_RISK 103 · EMERGENCY_STOP 139 · ASK_CLARIFY 230 · UNSUPPORTED 162 |
| 어투 | 명령 1,098 · 요청 675 · 평서 461 |
| Hard Negative | 84 — 위험 상황 34 · 대명사 16 · 부정 16 · 모호 5 · 범위 밖 5 · 비슷한 지원 외 5 · STT 오인식 3 |

| split | 전체 | 일반 | Hard Negative | 가족 |
|---|---|---|---|---|
| train | 1,627 | 1,583 | 44 | 80 |
| val | 337 | 314 | 23 | 53 |
| test | 354 | 337 | 17 (Guard REJECT 8) | 48 |
| calib (train에서) | 499 | | | |

- 목표보다 모자람: CHECK_RISK −17, EMERGENCY_STOP −11, UNSUPPORTED −18 (고정 문장 가족이라 표현이 적음).
- 일부러 넣은 경계 사례: "타이머 정지"=타이머 취소(긴급 정지 아님), "청소기 꺼 줘"·"볼륨 줄여 줘"=지원 외, "불빛 밝게"=지원 외(조명).
- Hard Negative test가 17건뿐이라 Unsafe Rate 표본이 작다 — 필요하면 Hard Negative를 늘린다.

## 평가

기본 모델·규칙 파서 평가는 [`bench/llm_eval.py`](../../bench/README.md). HF 모델 평가는 서비스 환경과 분리된 가상환경을 쓴다 (`requirements-eval.txt` — torch가 크다):

```bash
python3.11 -m venv .venv-llm && .venv-llm/bin/pip install -r training/llm/requirements-eval.txt
```
