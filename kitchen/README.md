# kitchen — 가상 주방 (Unity)

시연용 가상 주방이다. 장치(화구·튀김기·후드 등)와 가상 온도, 인식용 카메라 화면을 만들고, 보드와 `kitchen/*` 토픽으로 주고받는다.

- 왜 Unity인가: [decision](../docs/decisions/2026-10-05-unity-virtual-kitchen.md)
- 왜 이 폴더인가, 무엇을 커밋하는가: [decision](../docs/decisions/2026-10-08-unity-project-in-repo.md)
- 보드와 주고받는 규격: [연결 안내](../recipes/unity-kitchen-link.md) (기준 문서는 [interfaces](../docs/architecture/interfaces.md) §4)
- 화면 시안: 6주차 UI/UX 발표자료 (화면 1 "평소"의 배치를 따른다)

## 현재 상태

> 2026-11-12 기준. 작업이 끝날 때마다 이 절을 고친다.

- Unity 6000.3.25f1 URP 프로젝트 (#95). 템플릿 안내문과 `com.unity.collab-proxy`는 지웠고, Unity Cloud에는 연결하지 않았다.
- 장면 배치 완료 (HW-15, #95): `Assets/Scenes/Kitchen.unity`에 [에셋 팩](#에셋-팩)과 외부 3D 모델로 식당 홀·주방(화구·튀김기·후드·그릴·냉장고·계산대 등)을 배치했다. 물체 이름은 아직 팩 이름 그대로(`Stoves`·`Fryer`·`hoods` 등)다.
- 장치 위에 한글 이름표(오븐·튀김기·전자레인지·화구)를 TextMesh Pro + Pretendard Bold로 띄웠다. `Scripts/FaceCamera.cs`로 이름표가 카메라를 바라본다.
- 홀 벽·주방 벽·주방 바닥은 `Assets/Textures`의 2K 텍스처(`Materials/Hall_wall_mtrl`·`Kitchen_wall_mtrl`·`Kitchen_floor_mtrl`)를 쓴다. 텍스처·폰트는 1MB가 넘어도 커밋한다 ([decision](../docs/decisions/2026-10-08-unity-project-in-repo.md)).
- 아직 없는 것 (HW-25): 장치 이름(`burner_1` 등)·`Devices`·`CookingZone`·`Avatar`·인식용 카메라(`VisionCamera`·`VisionRT`). Build Profiles 장면 목록도 아직 `SampleScene`이다.
- 작업 중 (곧 올림): 불 효과 같은 파티클, 원격 명령으로 장치를 제어하는 기능(HW-16).
- 보드와 주고받는 코드는 아직 저장소에 없다.

## 작업 순서

작업 목록과 완료 기준의 source of truth는 [PLAN](../docs/PLAN.md)이다. 아래는 이 폴더에서 할 일의 순서만 적었다.

| 순서 | PLAN | 할 일 | 상태 |
|---|---|---|---|
| 1 | HW-15 | 장면 1차: 화구 2개·후드·튀김기 배치 ([아래](#장면-1차-hw-15) 1·2) | 완료 (#95) |
| 2 | HW-25 | 장면 2차: 장치 이름·`Devices`, 조리 구역, 인식용 카메라 ([아래](#장면-1차-hw-15) 2의 이름 규칙·3·4) | |
| 3 | HW-16 | `kitchen/cmd`로 후드 켜고 끄기, `kitchen/ack`로 답하기 (MQTTnet 4.3.7) | 작업 중 |
| 4 | HW-18 | 생존 신호가 3초 끊기면 가열 장치 OFF, `kitchen/state` 보고 | |
| 5 | HW-19 | 가열 장치의 가상 온도 계산, `kitchen/temp` 1초에 한 번, 265°C에서 스스로 OFF | |
| 6 | HW-20 | 인식용 카메라 화면을 `kitchen/frame`으로 전송 (JPEG 640×360, 1초에 4장) | |
| 7 | HW-21·22 | 제어 성공률·왕복 지연 측정과 개선 | |
| 8 | HW-23 | 장치 8종(조명·에어컨·선풍기·음악·결제)과 장치 상태 표시 — 발표 시연용 완성 | |

함께 쓰는 사람: 최석진(VIS-03·04, 2026-10-29 신지호에서 이관)이 이 장면의 화면을 캡처·라벨링해 YOLO 데이터를 만들고, 최지환(UI-01·02)이 화면에 겹쳐 띄우는 정보(장치 이름표·경고·판단 근거)를 붙인다.

## 장면 1차 (HW-15)

완료 기준은 **장치가 제자리에 있고, 인식용 카메라 화면을 캡처할 수 있는 상태**다. 가구·장치 모양은 [에셋 팩](#에셋-팩)의 프리팹을 쓰고, 맞는 것이 없으면 Unity 기본 도형(Cube·Cylinder·Capsule)으로 채운다.

### 1. 장면과 폴더

1. 장면은 `Assets/Scenes/Kitchen.unity` 하나로 만든다. 에셋 팩 안의 샘플 장면(`Restaurant Interior Full Pack/2.Scene/Sample` 등)을 고쳐 쓰지 않는다. 팩 폴더는 커밋되지 않아 그 안의 장면도 저장소에 남지 않는다. 샘플을 출발점으로 쓰려면 열어서 File → Save As로 `Assets/Scenes/Kitchen.unity`에 저장한 뒤 그 장면에서 작업한다. 쓰지 않는 `SampleScene`은 Unity 안에서 지운다.
2. `Assets/` 아래에 `Materials`, `RenderTextures`, `Prefabs` 폴더를 만든다 (`Scripts`는 HW-16에서).
3. File → Build Profiles의 장면 목록에 `Kitchen`이 있는지 확인한다 (메뉴 이름 확인 필요).

### 2. 물체 배치

에셋 팩 프리팹을 Project 창에서 Scene으로 끌어 놓거나, 없는 것은 GameObject → 3D Object로 만든다. 단위는 1 = 1m. 아래 도형·크기는 기본 도형으로 만들 때의 출발점용 예시다.

| 이름 | 도형 (기본 도형일 때) | 크기 예시 (Scale) | 위치 |
|---|---|---|---|
| `Floor` | Plane | 1, 1, 1 (10m×10m) | 바닥 |
| `Wall` | Cube | 6, 3, 0.1 | 조리대 뒤 |
| `Counter` | Cube | 3, 0.9, 0.7 | 벽 앞 |
| `burner_1`, `burner_2` | Cylinder | 0.3, 0.02, 0.3 | 조리대 윗면 왼쪽에 나란히 |
| `fryer` | Cube | 0.4, 0.3, 0.5 | 조리대 윗면 오른쪽 |
| `hood` | Cube | 1.2, 0.4, 0.6 | 화구 위 약 1m |
| `CookingZone` | Cube (얇게) | 3, 0.01, 1.2 | 조리대 앞 바닥 |
| `Avatar` | Capsule | 기본 (키 약 2m) | 조리 구역 안 |

- **장치 이름은 `burner_1`·`burner_2`·`fryer`·`hood` 그대로 짓는다.** 에셋 팩 프리팹을 쓸 때도 Hierarchy에서 이름을 바꾼다 (예: `cooker` → `burner_1`). `kitchen/cmd`의 `target` 값과 같아서 HW-16에서 이름으로 장치를 찾는다.
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
- Asset Store 에셋은 커밋하지 않는다 (저장소가 PUBLIC). 새 팩을 받으면 `kitchen/.gitignore`와 아래 [에셋 팩](#에셋-팩) 표에 함께 추가한다.
- 에셋 팩 폴더 안의 파일(프리팹·머티리얼 등)을 고치지 않는다. 고친 내용은 커밋되지 않는다. 바꿔야 하면 `Assets/Prefabs`·`Assets/Materials`로 복사(Ctrl+D 후 이동)해서 고친다.
- Unity Cloud·Unity Version Control에 연결하지 않는다.
- 브랜치를 바꾸기 전에 Unity를 닫는다.

## 여는 방법

1. Unity Hub에서 [versions](../docs/conventions/versions.md)에 고정된 에디터 버전을 설치한다 (다른 버전으로 열면 프로젝트 파일이 바뀐다).
2. Unity Hub → **Add** → 이 `kitchen/` 폴더를 고른다.
3. 처음 열 때 `Library/`를 새로 만드느라 몇 분 걸린다.
4. 아래 [에셋 팩](#에셋-팩)을 받아 넣는다. 없이 열면 장면의 가구·장치가 분홍색이거나 비어(Missing Prefab) 보인다.

## 에셋 팩

저장소가 PUBLIC이고 Asset Store 에셋은 보통 원본 재배포가 허용되지 않아서 커밋하지 않는다 (`kitchen/.gitignore`). 장면을 여는 사람은 각자 받는다.

| 팩 | 폴더 (`Assets/` 아래) |
|---|---|
| Kitchen Furniture Starter Pack (Mavi3D) | `KitchenFurnitureStarterPack-Mavi3D/` |
| Restaurant Interior Full Pack | `Restaurant Interior Full Pack/` |

받는 방법:

1. Unity Asset Store에서 위 팩을 자기 Unity 계정에 추가한다 (Add to My Assets, 무료 여부 확인 필요).
2. Unity 에디터에서 Window → Package Manager → My Assets에서 팩을 고르고 Download → Import.
3. Import 창에서 전부 체크한 채로 가져온다. 폴더 이름이 위 표와 같아야 `.gitignore`가 적용된다.

팩을 다시 가져와도 장면의 연결은 유지된다. 연결은 각 파일의 `.meta`에 든 GUID로 하는데, 같은 팩은 받을 때마다 같은 GUID를 쓴다.

### Asset Store 밖에서 받은 모델·텍스처

아래 파일도 재배포 라이선스를 확인하기 전까지 커밋하지 않는다 (`kitchen/.gitignore`). 장면에 쓰이므로 없으면 해당 물체가 Missing으로 보인다. 지금은 최석진에게 직접 받는다.

| 파일 (`Assets/` 아래) | 출처 | 용도 |
|---|---|---|
| `model.glb` | 3dassets.dev | 콤비 오븐·6구 레인지 등 주방 장치 |
| `AQDSEwsyLJwePed_3Sw5u.glb` | FurniMesh | 가구 1점 |
| `wood_floor_*_2k.*` | 확인 필요 | 홀 바닥 텍스처 (`Materials/wood_floor_mtrl`) |

`.glb`를 Unity에서 열려면 glTFast 패키지(`com.unity.cloud.gltfast`, `Packages/manifest.json`에 들어 있다)가 필요하다. 라이선스를 확인해 커밋하기로 하면 `.gitignore`에서 빼고 `.gitattributes`에 `*.glb binary`를 추가한다.
