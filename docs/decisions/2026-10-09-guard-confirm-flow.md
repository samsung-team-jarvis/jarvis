# Decision: Safety Guard의 확인 흐름 (결제 요청 → 네·아니요)

## Status
- Accepted

## Date
- 2026-10-09

## Context
- 스키마 v0.2에서 결제 요청(`REQUEST_PAYMENT`)은 Safety Guard가 항상 확인(`ASK`)을 받은 뒤 실행하기로 했다 ([decision](./2026-10-06-function-call-schema-v02.md)). "네"·"아니요"는 `CONFIRM`·`DENY` Action으로 오고, 기다리는 질문이 있는지는 Guard가 판단한다.
- 대답을 기다리는 시간과, 그동안 호출어 없이 대답을 받는 방법은 FUS-03에서 정하기로 남겨 두었다 (interfaces §5).
- 호출어가 없는 문장(`stt/text`의 `wake=false`)은 명령 해석(`llm_svc`)이 무시한다. 손님과 대화하던 중에 "네"라고 말할 때마다 결제가 실행되면 안 된다.

## Options
- 기다리는 시간: (A) 10초 / (B) 무제한 (다른 명령이 올 때까지)
- 호출어 없는 대답: (A) 기다리는 동안에만 Guard가 `stt/text`를 직접 읽어 "네"·"아니요"인지 본다 / (B) 호출어가 있어야만 받는다 ("자비스 네") / (C) audio_svc·llm_svc가 기다리는 상태를 알고 호출어 없이 넘긴다
- 기다리는 중 다른 명령: (A) 질문을 버린다 / (B) 질문을 유지한다

## Decision
- 선택한 안: 시간 A (10초), 호출어 없는 대답 A, 다른 명령 A (결정: 최지환)
- 세부:
  - `REQUEST_PAYMENT` → `guard/decision`의 `ASK`. 상태와 무관하게 항상 묻는다.
  - 10초 안에 `CONFIRM`이 오면 물었던 결제 요청을 `ALLOW`로 다시 발행한다. `DENY`가 오면 `DENY`를 `ALLOW`로 발행한다(응답: "취소했습니다").
  - 기다리는 동안 호출어 없는 문장을 규칙 파서(`services/llm_svc/rule_parser.py`)로 읽어 **`CONFIRM`·`DENY`일 때만** 대답으로 받는다. 그 밖의 말은 무시하고 계속 기다린다.
  - 다른 명령이 오거나, 긴급 정지가 일어나거나, 10초가 지나면 질문을 버린다. 그 뒤의 "네"·"아니요"는 `REJECT`("확인할 질문이 없어요.").
- 선택 이유:
  - 시간을 짧게 두면 나중에 대화 속 "네"가 결제를 실행하는 일을 줄인다. 다른 명령이 오면 질문을 버리는 것도 같은 이유다.
  - 기다리는 상태는 Guard 하나만 알면 된다. audio_svc·llm_svc를 바꾸지 않고, LLM도 거치지 않는다 (결정론적 규칙).
  - "네"·"아니요" 판정은 규칙 파서와 같은 규칙을 써서 호출어가 있을 때와 없을 때 결과가 같다.

## Consequences
- 장점: 결제가 확인 없이 실행되는 경로가 없다. 대답할 때 "자비스"를 다시 부르지 않아도 된다.
- 단점: 10초 안에 대화 속 "네"가 들어오면 결제가 허용된다 (확인을 물은 직후라 실제로 대답일 가능성이 높다고 본다). 결제 실행(가상 결제 단말 연결)은 아직 없다 (HW-23).
- 영향: [interfaces](../architecture/interfaces.md) §3.1·§5, [`services/safety_guard`](../../services/safety_guard/README.md), PLAN FUS-03

## Verification
- `tests/safety_guard/test_service.py`: 확인 → 허용, 아니요 → 취소, 시간 초과·다른 명령·긴급 정지 뒤의 대답 거부, 호출어 없는 대답, llm_svc와 이은 "자비스 결제해 줘" → "자비스 네"

## Revisit
- 시연에서 10초가 짧거나 길 때
- 결제 말고도 확인이 필요한 명령이 생길 때
- 대화 속 "네"로 잘못 확인되는 일이 실제로 생길 때
