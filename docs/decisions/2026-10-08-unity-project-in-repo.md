# Decision: Unity 프로젝트는 같은 저장소의 `kitchen/`에 둔다

## Status
- Accepted ([Unity 결정](./2026-10-05-unity-virtual-kitchen.md)에 없던 "프로젝트를 어디에 두는가"를 채운다)

## Date
- 2026-10-08

## Context
- 가상 주방은 Unity 6.3 LTS로 만든다 ([decision](./2026-10-05-unity-virtual-kitchen.md)). HW-15(#95)에서 첫 프로젝트를 만들면서 git에 어떻게 올릴지 정해야 했다.
- Unity가 지켜야 할 연결 규격은 이 저장소에 있다 ([interfaces](../architecture/interfaces.md) §4, [recipe](../../recipes/unity-kitchen-link.md), `common/kitchen_link.py`).
- [Git Convention](../conventions/git.md)의 scope 표에 `kitchen`이 이미 "`kitchen_gw` + 가상 주방 스크립트"로 정의돼 있다.
- 저장소는 PUBLIC이다.

## Options
- Option A: 같은 저장소의 `kitchen/` 폴더
- Option B: 별도 저장소 (예: `jarvis-kitchen`)
- Option C: Unity Version Control (Unity 자체 버전 관리, 클라우드)

## Decision
- 선택한 안: **A** (결정: 최석진)

| 항목 | 결정 |
|---|---|
| 위치 | `kitchen/` (Unity 프로젝트 루트) |
| 커밋하는 것 | `Assets/` · `Packages/`(`manifest.json`, `packages-lock.json`) · `ProjectSettings/`, 모든 `.meta` 파일 |
| 커밋하지 않는 것 | `Library/` · `Temp/` · `Logs/` · `UserSettings/` · `*.csproj` · `*.sln` 등 Unity·IDE가 다시 만드는 파일 (`kitchen/.gitignore`) |
| 에디터 설정 | Version Control Mode = Visible Meta Files, Asset Serialization = Force Text |
| 줄바꿈 | 텍스트 에셋(장면·프리팹·`.meta`)은 저장소 규칙대로 LF. 이미지·3D 모델·소리는 `.gitattributes`에서 `binary` |
| Unity Cloud | 연결하지 않는다 (`ProjectSettings.asset`의 `cloudProjectId`·`organizationId` 비움). `com.unity.collab-proxy` 패키지 제거 |
| Git LFS | 쓰지 않는다 (아래 Revisit) |

- 선택 이유:
  - 이슈 → 브랜치 → PR → PLAN 체크 흐름과 훅·CI·라벨을 그대로 쓴다. B는 이것을 다시 세팅해야 한다.
  - 연결 규격(`kitchen/*` 토픽)과 Unity 쪽 코드를 같은 PR에서 함께 바꿀 수 있다.
  - C는 git과 두 벌의 버전 관리가 되고, 팀원 모두 Unity 계정·조직 설정이 필요하다.

## Consequences
- 장점: 작업 흐름이 하나다. 규격과 구현이 한곳에 있다.
- 단점:
  - Python 개발자가 저장소를 받을 때 Unity 에셋도 함께 받는다. 지금은 수백 KB라 문제없다.
  - 장면 파일(`.unity`)은 텍스트여도 충돌을 손으로 풀기 어렵다 → 한 장면은 한 번에 한 사람만 편집하고, 장치는 프리팹으로 나눈다.
  - 저장소가 PUBLIC이라 Asset Store 에셋은 재배포가 허용된 것만 커밋할 수 있다 (에셋마다 라이선스 확인 필요). 1차 장면은 Unity 기본 도형으로 만든다.
- 영향: `kitchen/`, `.gitattributes`, [versions](../conventions/versions.md)(Unity 패치 버전), README 폴더 구조, PLAN HW-15~23

## Verification
- 6000.3.25f1에서 만든 URP 프로젝트를 `kitchen/`에 두고 `git status`로 추적 대상이 `Assets/`·`Packages/`·`ProjectSettings/`·`.gitignore`·`.vsconfig`뿐인지 확인 (Windows, #95)
- **미검증**: 다른 PC(특히 Mac)에서 clone해 같은 장면이 열리는지

## Revisit
- 3D 모델·텍스처·소리가 늘어 저장소가 수십 MB를 넘을 때 → Git LFS 또는 에셋 별도 보관
- 장면 충돌이 자주 날 때 → 장면 분리, UnityYAMLMerge 설정
