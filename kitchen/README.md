# kitchen — 가상 주방 (Unity)

시연용 가상 주방이다. 장치(화구·튀김기·후드 등)와 가상 온도, 인식용 카메라 화면을 만들고, 보드와 `kitchen/*` 토픽으로 주고받는다.

- 왜 Unity인가: [decision](../docs/decisions/2026-10-05-unity-virtual-kitchen.md)
- 왜 이 폴더인가, 무엇을 커밋하는가: [decision](../docs/decisions/2026-10-08-unity-project-in-repo.md)
- 보드와 주고받는 규격: [연결 안내](../recipes/unity-kitchen-link.md)

## 여는 방법

1. Unity Hub에서 [versions](../docs/conventions/versions.md)에 고정된 에디터 버전을 설치한다 (다른 버전으로 열면 프로젝트 파일이 바뀐다).
2. Unity Hub → **Add** → 이 `kitchen/` 폴더를 고른다.
3. 처음 열 때 `Library/`를 새로 만드느라 몇 분 걸린다.

## 지킬 것

- 파일 이동·이름 변경·삭제는 **Unity 안에서** 한다. 탐색기·Finder로 하면 `.meta`가 따라가지 않아 연결이 끊긴다.
- `.meta` 파일은 항상 원본과 함께 커밋한다.
- 같은 장면(`.unity`)을 두 사람이 동시에 고치지 않는다.
- Asset Store 에셋은 재배포가 허용된 것만 커밋한다 (저장소가 PUBLIC).
- Unity Cloud·Unity Version Control에 연결하지 않는다.
