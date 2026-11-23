# Decision: 가상 주방에 아바타를 두지 않고, 인식 화면은 메인 카메라, 사람 감지는 웹캠으로

## Status
- Accepted

## Date
- 2026-11-23

## Context
- HW-25(장면 2차, #158)는 `Avatar`(가상 요리사)·`CookingZone`(아바타가 들어왔는지 보는 보이지 않는 영역)·`VisionCamera`(AI 전용 고정 카메라 → `VisionRT` 640×360)를 만들기로 했다 ([kitchen README](../../kitchen/README.md)).
- 화면이 보드에 꼭 알려 줘야 하는 것은 **조리 구역에 사람이 있는가**다. 방치 = 가열 장치 켜짐 + 사람 없음 ([vision decision](./2026-10-29-vision-pretrained-person.md), [State 규칙](./2026-11-09-state-rules.md)).
- 노트북 시연 설정은 이미 웹캠 입력이다 (`scripts/launch_demo.yaml`의 `vision_svc --input camera`). 카메라 앞의 사람이 조리 구역의 사람 역할을 한다.

## Options
- Option A: 아바타·조리 구역·인식용 카메라를 Unity에 만든다. Unity 화면(`kitchen/frame`)으로 사람을 감지한다.
- Option B: **아바타·조리 구역·인식용 카메라를 만들지 않는다.** 사람 감지는 웹캠으로 하고, `kitchen/frame`은 메인 카메라 화면을 640×360으로 보낸다.

## Decision
- 선택한 안: **B** (결정: 최석진, #180)
- `Avatar`·`CookingZone`·`VisionCamera`는 만들지 않는다. 아바타가 없으면 조리 구역은 감지할 대상이 없다.
- HW-20의 `kitchen/frame`은 메인 카메라 화면이다. 보낼 때 코드에서 640×360 Render Texture에 한 번 더 그리므로 사용자가 보는 화면은 바뀌지 않는다. 화면 고정 UI(Screen Space - Overlay)는 이 그림에 들어가지 않고, 장치 위의 이름표(월드 공간 글자)는 들어간다.
- 웹캠 사람 감지는 나중에 붙이는 선택 항목이다. 필수로 두지 않는다.

## Consequences
- 장면 작업이 줄어든다. HW-25는 장치 이름·`Devices`·Build Profiles 장면만 남는다.
- **웹캠(또는 `vision_svc`)이 없으면 보드는 사람이 없는 것으로 본다.** 가열 장치를 켜면 30초 뒤 방치(`UNATTENDED`), 그 뒤 30초 유예 후 자동 차단된다 ([auto-stop](./2026-11-11-auto-stop.md)). 온도 경고·265°C 자체 차단은 사람 감지와 상관없다.
- Unity 화면 속 사람을 인식할 일이 없어 `kitchen/frame`의 쓰임이 줄어든다: 시연 화면의 "AI가 본 화면", 나중의 맞춤 학습용 캡처(VIS-03).
- 메인 카메라를 움직이면 `kitchen/frame` 구도도 바뀐다.
- 영향: [PLAN](../PLAN.md) HW-25·HW-20·VIS-03, [kitchen README](../../kitchen/README.md), [Unity 연결 안내](../../recipes/unity-kitchen-link.md) §4

## Revisit When
- Unity 화면으로 사람(방치)을 시연해야 할 때 (웹캠을 쓸 수 없는 시연장)
- 맞춤 클래스 학습(VIS-03·04)을 시작해서 고정 구도의 캡처가 필요할 때
