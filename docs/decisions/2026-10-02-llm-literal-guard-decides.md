# Decision: LLM은 명령을 말 그대로 해석하고, 위험 판단은 Safety Guard가 한다

## Status
- Accepted

## Date
- 2026-10-02

## Context
- LLM 학습 데이터(LLM-02·03)를 만들면서, 위험 상황(DANGER·UNATTENDED)에 들어온 위험 명령("2번 화구 세게")의 **정답**을 정해야 했다 (#55).
- [안전 3계층](./2026-10-01-safety-layers.md): LLM은 Function Call을 **제안**만 하고, 위험 판단은 결정론적 Safety Guard(L1)와 ESP32(L0)가 한다.
- 학습 대상은 1B급 소형 모델이다. 맥락에 따라 같은 문장의 정답이 바뀌면 배우기 어렵고, 평소 명령까지 거부하는 오류가 생길 수 있다.

## Options
- Option A: LLM은 말 그대로 해석 (정답 = `SET_LEVEL burner_2 3`), Guard가 REJECT
- Option B: LLM도 맥락을 보고 거부·되묻기 (정답 = `ASK_CLARIFY` 등)

## Decision
- 선택한 안: **A** (결정: 이현종)
- 선택 이유: 안전 판단을 한 곳(결정론적 Guard)에 모아 테스트·설명이 쉽다. 정답이 맥락과 무관해 데이터가 일관된다. 소형 모델이 평소 명령을 거부하는 오류를 피한다.

## Consequences
- Hard Negative의 위험 상황 데이터에 `expect_guard`(REJECT/ALLOW)를 달아, 같은 데이터를 Guard 테스트(FUS-03)에도 쓴다.
- **Unsafe Action Rate (Guard 적용 전)은 설계상 높게 나온다.** 목표(≤ 2%)는 Guard 적용 후에 적용한다. 전/후 차이가 "LLM만으로는 위험하고 Guard가 필요하다"는 근거가 된다.
- 영향: [METRICS](../METRICS.md) Unsafe Action Rate, [training/llm](../../training/llm/README.md), FUS-03(Guard 규칙: 위험 상태의 점화·세기 올림 REJECT, 끄기·후드·타이머 ALLOW — `expect_guard` 제안값은 ③ 담당이 확정)

## Verification
- LLM Baseline(LLM-06)·v1(LLM-08)에서 Hard Negative의 Guard 전/후 Unsafe Rate를 측정한다 — 미측정.

## Revisit
- Guard가 막지 못하는 위험 유형이 측정으로 나오면, 그 유형만 LLM 쪽 보조 규칙을 검토한다.
