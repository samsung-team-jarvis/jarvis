# Pull Request Writing

PR 본문은 [PR 템플릿](../../.github/pull_request_template.md)의 섹션 구조를 유지한다. 리뷰어가 "무엇을 왜 바꿨고, 무엇으로 확인했는가"를 PR만 보고 판단할 수 있어야 한다. 이 PR들이 그대로 주간보고·최종 보고서의 근거가 된다.

## 섹션별 작성 기준

| 섹션 | 쓸 것 | 쓰지 말 것 |
|---|---|---|
| Related Issues | `Closes #N`, 관련 PLAN ID | |
| Background | 기존 상태, 바꾸는 이유 (문단형) | 파일 나열 |
| Tasks | 구현 흐름과 의도 | 커밋 메시지 복붙 |
| Implementation Notes | 선택한 접근, 제외한 대안, trade-off, 임시 정책 | |
| Verification | **실제 실행한** 명령과 실행 장소 (Mac / Colab / 보드 / ESP32) | 실행하지 않은 검증 |
| Measurement | 측정했다면 수치 + 측정 조건 (보드, 툴 버전, 데이터셋, 커밋). METRICS 갱신 여부 | 추정치, 측정 안 한 수치 |
| Evidence | 로그, 스크린샷, 시연 영상 링크, 출력 예시 | |
| PR Point | 리뷰어가 중점적으로 볼 곳 | |
| Risk / Follow-up | 남은 리스크와 후속 이슈 | |

## 머지 전 체크리스트

- [ ] 제목이 `[PREFIX](scope): #N work summary` 형식
- [ ] 본문에 `Closes #N`
- [ ] `docs/PLAN.md` 해당 항목 체크 (완료된 경우)
- [ ] 수치가 있으면 `docs/METRICS.md` 측정 로그에 기록
- [ ] 인터페이스를 바꿨으면 `docs/architecture/interfaces.md` 변경 이력 갱신
- [ ] 결정이 있었으면 `docs/decisions/` 기록
- [ ] 모델 가중치·원본 데이터·비밀값이 diff에 없음
- [ ] 안전 규칙을 바꿨으면 PR Point에 명시하고 테스트 추가
