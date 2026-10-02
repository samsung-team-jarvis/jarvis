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
