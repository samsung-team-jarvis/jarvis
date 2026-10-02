# training/llm — LLM 데이터 (LLM-02 Seed · LLM-03 Hard Negative)

[기획 시트](./plan_sheet.yaml)(SUDA 방식: 장치 부르는 말·숫자 표기·어투 3종·Action별 템플릿·목표 수량)로 정답이 보장된 데이터를 만든다. 사람은 문장마다 라벨을 붙이지 않고, **시트를 고치고 다시 생성**한다.

```bash
python -m training.llm.build_seed                            # → data/llm/seed_v1.jsonl, hard_negative_v1.jsonl
python -m training.llm.build_seed --review-csv review.csv    # 검수용 표 (Excel로 열기, git 제외 위치에)
```

## 데이터 형식 (한 줄 = interfaces §3.4)

```json
{"instruction": "두 번째 불을 켜 주세요",
 "context": {"state": "COOKING", "temperature": 175, "detected_objects": ["pan", "burner_on", "hand"], "last_target": null},
 "output": {"action": "TURN_ON", "target": "burner_2"},
 "meta": {"template_id": "on_03", "tone": "요청", "source": "seed", "indirect": false, "split": null}}
```

- `instruction`은 **호출어를 뺀** 명령 문장 (llm_svc가 `split_wake` 결과를 넘긴다).
- 학습 정답 문자열은 `to_tokens(output)` → `<jarvis_1>(target=burner_2)<jarvis_end>`.
- `template_id`가 학습/평가 분할(LLM-05)의 그룹 단위다. `split`은 LLM-05에서 채운다.
- Hard Negative의 `meta`: `category`, `expect_guard`(Guard에 갔을 때 기대 판정 — FUS-03 테스트에도 씀), `note`.

## 규칙

- **위험 상황의 위험 명령도 정답은 말 그대로의 명령**이다 ("DANGER인데 2번 화구 세게" → `SET_LEVEL burner_2 3`). 막는 것은 Safety Guard ([decision](../../docs/decisions/2026-10-02-llm-literal-guard-decides.md)).
- **STT 테스트 대본과 같은 문장은 넣지 않는다** (`data/stt/script.csv`, 띄어쓰기·문장부호 무시 비교). 넣으면 STT→Action 평가가 부풀려진다.
- 같은 문장·같은 맥락에 정답이 둘이면 생성이 실패한다 (시트 모순).
- 기획 시트를 바꾸면 반드시 다시 생성해 커밋한다 — 테스트가 커밋된 데이터와 시트가 같은지 검사한다.

## 검수 (사람)

1. `--review-csv`로 표를 만들어 Excel에서 연다 (`검수(OK/수정)`, `메모` 칸).
2. 어색한 문장·틀린 정답을 표시한다. **문장을 직접 고치지 말고** 해당 `template_id`의 템플릿이나 슬롯 표현을 시트에서 고친다.
3. 다시 생성 → PR.

## v1 현황 (2026-10-02)

| 구분 | 수 | 비고 |
|---|---|---|
| Seed | 627 | 템플릿 143개, 어투 명령 312 · 요청 199 · 평서 116, 간접 발화 33 |
| Hard Negative | 84 | 위험 상황 34 · 대명사 16 · 부정 16 · 모호 5 · 범위 밖 5 · 비슷한 지원 외 5 · STT 오인식 3 |

- 목표보다 모자란 Action: `CANCEL_TIMER` −12, `CHECK_RISK` −7, `EMERGENCY_STOP` −12, `UNSUPPORTED` −2 (고정 문장 템플릿이 적고, "멈춰·그만·긴급 정지" 등은 STT 대본과 겹쳐 제외). **LLM-04 Paraphrase에서 채운다.**
- 사람 검수 전이다.

## Paraphrase → 데이터 v1 (LLM-04, 발표 p.9 ②~④)

```bash
python -m training.llm.build_dataset                           # → data/llm/dataset_v1.jsonl
python -m training.llm.build_dataset --review-csv review.csv   # Paraphrase만 검수용 표
```

| 단계 | 하는 일 | 어디서 |
|---|---|---|
| ① Seed | 기획 시트 템플릿 → 627건 (모두 포함) | `plan_sheet.yaml`, `build_seed.py` |
| ② Paraphrase | 부모 템플릿을 같은 뜻의 다른 말투로 바꿔 쓴 **템플릿** (생성: Claude, 프롬프트는 시트 머리말) | `paraphrase_sheet.yaml` |
| ③ 검증·중복 제거 | 스키마 검증, 띄어쓰기·문장부호만 다른 중복 제거, 같은 문장에 다른 정답이면 실패 | `build_dataset.py` |
| ④ Entity 치환·STT 정규화 | 슬롯 채우기(정답이 자동으로 따라옴) + 서비스와 같은 STT 오인식 사전 적용 (`meta.raw_instruction`에 원문) | `build_dataset.py` |
| ⑤ Hard Negative 분리 | 따로 둔다 | `hard_negative_v1.jsonl` |
| ⑥ 분할 | 가족(`meta.group`) 단위 | LLM-05 |

- 바꿔 쓴 템플릿은 부모의 정답·장치 목록을 물려받고 **같은 가족(`group` = 부모 id)**이다. 분할을 가족 단위로 해야 비슷한 문장이 train·test에 함께 들어가지 않는다.
- `(a|b|c)` 선택지는 모든 조합으로 펼친다. Action별 목표까지 템플릿을 돌아가며 뽑는다.
- 헷갈리기 쉬운 경계를 일부러 넣었다: "타이머 정지"=타이머 취소(긴급 정지 아님), "청소기 꺼 줘"·"볼륨 줄여 줘"=지원 외, "불빛 밝게"=지원 외(조명).

### v1 현황 (2026-10-02)

| 구분 | 수 |
|---|---|
| 합계 | **2,234** (Seed 627 · Paraphrase 1,607) |
| Action | TURN_ON 320 · TURN_OFF 320 · SET_LEVEL 340 · SET_TIMER 320 · CANCEL_TIMER 120 · CHECK_STATUS 180 · CHECK_RISK 103 · EMERGENCY_STOP 139 · ASK_CLARIFY 230 · UNSUPPORTED 162 |
| 어투 | 명령 1,098 · 요청 675 · 평서 461 |
| 가족(분할 단위) | 150 (템플릿 269) |

- 목표보다 모자람: CHECK_RISK −17, EMERGENCY_STOP −11, UNSUPPORTED −18 (고정 문장 가족이라 표현이 적음).
- Paraphrase 1,607건은 사람 검수 전이다 (Seed 검수와 같은 방식: 시트를 고쳐 재생성).

## 분할 (LLM-05, 발표 p.9 ⑥)

```bash
python -m training.llm.split_dataset    # → data/llm/split_v1/{train,val,test,calib}.jsonl, groups.json
```

- **가족(`meta.group`) 단위**: 부모 템플릿과 그 Paraphrase는 같은 split → 비슷한 문장이 train·test에 같이 들어가지 않는다. `groups.json`이 가족 → split 목록이다.
- Action별(Hard Negative는 범주 + Guard 기대 판정별)로 큰 가족부터 목표 비율(70/15/15%)보다 가장 모자란 split에 넣고, 어떤 split에 그 Action이 비면 가장 남는 split의 가장 작은 가족을 옮긴다.
- **Test는 고정**: 순서·seed가 고정이라 다시 나눠도 같다 (테스트가 확인). Test는 비교할 때만 쓰고, 오류 분석·조정은 val로 한다.
- **캘리브레이션(`calib.jsonl`)**: 양자화(RKLLM 변환)용. **train에서만**, Action 비율대로 약 500건 (특강 권장 300~1,000). 변환 입력 형식(chat template 적용)은 LLM-08에서 만든다.

### v1 분할 (2026-10-02)

| split | 전체 | 일반 | Hard Negative | 가족 |
|---|---|---|---|---|
| train | 1,627 | 1,583 | 44 | 80 |
| val | 337 | 314 | 23 | 53 |
| test | 354 | 337 | 17 | 48 |
| calib (train에서) | 499 | | | |

- 모든 Action이 세 split에 다 있다. 가족·문장 누수 0.
- Hard Negative를 범주 + 기대 판정(REJECT/ALLOW)으로 나눠 배정한다 — 그래야 Guard가 거절해야 할 위험 명령이 test에 들어가 Unsafe Rate를 잴 수 있다 (test REJECT 8건). 표본이 작으니 필요하면 Hard Negative를 늘린다.
