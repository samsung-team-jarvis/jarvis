# kitchen — 가상 주방 (Unity)

시연용 가상 주방이다. 장치(화구·튀김기·후드 등)와 가상 온도, 인식용 카메라 화면을 만들고, 보드와 `kitchen/*` 토픽으로 주고받는다.

- 왜 Unity인가: [decision](../docs/decisions/2026-10-05-unity-virtual-kitchen.md)
- 왜 이 폴더인가, 무엇을 커밋하는가: [decision](../docs/decisions/2026-10-08-unity-project-in-repo.md)
- 보드와 주고받는 규격: [연결 안내](../recipes/unity-kitchen-link.md) (기준 문서는 [interfaces](../docs/architecture/interfaces.md) §4)
- 화면 시안: 6주차 UI/UX 발표자료 (화면 1 "평소"의 배치를 따른다)

## 현재 상태

> 2026-10-08 기준. 작업이 끝날 때마다 이 절을 고친다.

- Unity 6000.3.25f1 URP 프로젝트만 만들었다 (#95). 템플릿 안내문과 `com.unity.collab-proxy`는 지웠고, Unity Cloud에는 연결하지 않았다.
- 장면은 템플릿 기본 장면(`Assets/Scenes/SampleScene`)뿐이다. 장치·카메라는 아직 없다.
- 보드와 주고받는 코드는 없다.

## 작업 순서

작업 목록과 완료 기준의 source of truth는 [PLAN](../docs/PLAN.md)이다. 아래는 이 폴더에서 할 일의 순서만 적었다.

| 순서 | PLAN | 할 일 | 상태 |
|---|---|---|---|
| 1 | HW-15 | 장면 1차: 화구 2개·후드·튀김기, 조리 구역, 인식용 카메라 ([아래](#장면-1차-hw-15)) | 진행 중 (#95) |
| 2 | HW-16 | `kitchen/cmd`로 후드 켜고 끄기, `kitchen/ack`로 답하기 (MQTTnet 4.3.7) | |
| 3 | HW-18 | 생존 신호가 3초 끊기면 가열 장치 OFF, `kitchen/state` 보고 | |
| 4 | HW-19 | 가열 장치의 가상 온도 계산, `kitchen/temp` 1초에 한 번, 265°C에서 스스로 OFF | |
| 5 | HW-20 | 인식용 카메라 화면을 `kitchen/frame`으로 전송 (JPEG 640×360, 1초에 4장) | |
| 6 | HW-21·22 | 제어 성공률·왕복 지연 측정과 개선 | |
| 7 | HW-23 | 장치 8종(조명·에어컨·선풍기·음악·결제)과 장치 상태 표시 — 발표 시연용 완성 | |

함께 쓰는 사람: 신지호(VIS-03)가 이 장면의 화면을 캡처해 YOLO 데이터를 만들고, 최지환(UI-01·02)이 화면에 겹쳐 띄우는 정보(장치 이름표·경고·판단 근거)를 붙인다.

## 장면 1차 (HW-15)

완료 기준은 **장치가 제자리에 있고, 인식용 카메라 화면을 캡처할 수 있는 상태**다. 1차는 Unity 기본 도형(Cube·Cylinder·Capsule)만 쓰고 Asset Store 에셋은 쓰지 않는다.

### 1. 장면과 폴더

1. `Assets/Scenes/SampleScene`을 Project 창에서 `Kitchen`으로 이름을 바꾼다.
2. `Assets/` 아래에 `Materials`, `RenderTextures`, `Prefabs` 폴더를 만든다 (`Scripts`는 HW-16에서).
3. File → Build Profiles의 장면 목록에 `Kitchen`이 있는지 확인한다 (메뉴 이름 확인 필요).

### 2. 물체 배치

GameObject → 3D Object로 만든다. 단위는 1 = 1m. 크기는 출발점용 예시다.

| 이름 | 도형 | 크기 예시 (Scale) | 위치 |
|---|---|---|---|
| `Floor` | Plane | 1, 1, 1 (10m×10m) | 바닥 |
| `Wall` | Cube | 6, 3, 0.1 | 조리대 뒤 |
| `Counter` | Cube | 3, 0.9, 0.7 | 벽 앞 |
| `burner_1`, `burner_2` | Cylinder | 0.3, 0.02, 0.3 | 조리대 윗면 왼쪽에 나란히 |
| `fryer` | Cube | 0.4, 0.3, 0.5 | 조리대 윗면 오른쪽 |
| `hood` | Cube | 1.2, 0.4, 0.6 | 화구 위 약 1m |
| `CookingZone` | Cube (얇게) | 3, 0.01, 1.2 | 조리대 앞 바닥 |
| `Avatar` | Capsule | 기본 (키 약 2m) | 조리 구역 안 |

- **장치 이름은 `burner_1`·`burner_2`·`fryer`·`hood` 그대로 짓는다.** `kitchen/cmd`의 `target` 값과 같아서 HW-16에서 이름으로 장치를 찾는다.
- 장치 4개는 빈 오브젝트 `Devices` 아래에 모은다 (GameObject → Create Empty).
- `CookingZone`은 Mesh Renderer를 끄고 Box Collider의 Is Trigger를 켠다. 보이지 않는 "사람 있음" 감지 영역이다 (감지 코드는 나중).
- 색은 Material(Create → Material, Base Map 색)로 구분한다. YOLO가 이 화면으로 학습하므로 장치끼리 생김새가 구분돼야 한다.

### 3. 카메라

- `Main Camera`: 시연 때 사람이 보는 화면. 정면에서 조리대 전체가 보이게 둔다.
- `VisionCamera`: AI가 보는 인식용 고정 카메라.
  1. GameObject → Camera로 만들고, 같이 생긴 Audio Listener는 지운다 (장면에 하나만).
  2. 조리대와 조리 구역이 모두 보이게 위쪽 앞에서 비스듬히 내려다보게 둔다.
  3. Create → Render Texture로 `Assets/RenderTextures/VisionRT`를 만들고 크기를 **640×360**으로 한다 (`common/kitchen_link.py`의 캡처 크기).
  4. `VisionCamera`의 Output → Target Texture에 `VisionRT`를 넣는다.

Render Texture는 카메라 화면을 메모리 속 그림으로 담아 둔다. HW-20에서 이것을 JPEG로 바꿔 보낸다.

### 4. 확인

1. ▶ Play → Project 창에서 `VisionRT`를 고르면 Inspector 미리보기에 인식용 카메라 화면이 보인다.
2. Game 화면 스크린샷을 남긴다 (PR 첨부, VIS-01에 전달).
3. Play를 끄고 Ctrl+S. Play 중에 바꾼 값은 끄면 사라진다.

## 지킬 것

- 파일 이동·이름 변경·삭제는 **Unity 안에서** 한다. 탐색기·Finder로 하면 `.meta`가 따라가지 않아 연결이 끊긴다.
- `.meta` 파일은 항상 원본과 함께 커밋한다.
- 같은 장면(`.unity`)을 두 사람이 동시에 고치지 않는다.
- Asset Store 에셋은 재배포가 허용된 것만 커밋한다 (저장소가 PUBLIC).
- Unity Cloud·Unity Version Control에 연결하지 않는다.
- 브랜치를 바꾸기 전에 Unity를 닫는다.

## 여는 방법

1. Unity Hub에서 [versions](../docs/conventions/versions.md)에 고정된 에디터 버전을 설치한다 (다른 버전으로 열면 프로젝트 파일이 바뀐다).
2. Unity Hub → **Add** → 이 `kitchen/` 폴더를 고른다.
3. 처음 열 때 `Library/`를 새로 만드느라 몇 분 걸린다.
