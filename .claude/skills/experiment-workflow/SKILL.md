---
name: experiment-workflow
description: 모델 성능·지연·정확도를 측정하거나 Baseline/개선 실험을 할 때 사용합니다. 측정 조건 고정, 결과 기록, 수치 날조 방지 규칙을 적용합니다.
---

# 실험·측정 워크플로

## 읽기 전략

- `docs/workflows/experiment.md` (원칙과 절차의 source of truth)
- `docs/METRICS.md` (지표 정의, 결과표, 측정 로그)
- `templates/experiment.spec.md`
- 관련 recipe: `recipes/stt-eval.md`, `recipes/yolo-to-rknn.md`, `recipes/llm-to-rkllm.md`

## 절차

1. 실험 spec을 채운다: 가설, 바꾸는 변수 1개, 고정 조건, 데이터셋 버전, 지표, 측정 스크립트.
2. 데이터 분할이 그룹 단위인지 확인한다 (speaker / session / template / scenario). Test Set을 학습·튜닝에 쓰지 않는다.
3. Baseline을 같은 조건으로 먼저 측정한다.
4. 변경을 적용하고 같은 스크립트·같은 Test Set으로 재측정한다.
5. 결과를 METRICS 측정 로그에 한 줄씩 추가하고, 결과표의 해당 칸을 갱신한다.
6. Validation 오류를 유형별로 분류하고, 다음 개선 작업을 이슈로 만든다.

## 기록 규칙

- 실측값만 기록한다. 측정하지 않은 칸은 `측정 예정`으로 둔다.
- 측정 조건(보드 모델·RAM, 툴 버전, 모델 파일, 데이터셋, 커밋, 실행 명령)을 함께 남긴다.
- 보드가 아닌 곳(Mac, Colab)에서 잰 값은 비고에 측정 위치를 적고 최종 수치와 구분한다.
- 수업 자료·논문·공식 문서의 수치는 "참고"로 표시하고 우리 측정과 섞지 않는다.
- 결과가 기대보다 나빠도 그대로 기록한다. 원인 분석이 발표 산출물이다.
