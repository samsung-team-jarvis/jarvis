# Decision: 가상 주방 플랫폼은 Unity

## Status
- Accepted ([open-questions](./open-questions.md) Q-11 답. [가상 주방 결정](./2026-10-05-virtual-kitchen-demo.md)의 "플랫폼 미정"을 채운다)

## Date
- 2026-10-05

## Context
- 시연은 가상 주방에서 하기로 했고 플랫폼은 미정이었다 ([decision](./2026-10-05-virtual-kitchen-demo.md), PLAN HW-13).
- Q-11 선택 기준: ① 보드와 메시지를 주고받을 수 있는가 ② 인식용 카메라 화면을 캡처해 내보낼 수 있는가 ③ 장치 상태를 스크립트로 바꿀 수 있는가 ④ 비용.
- 제약: 보드와 가상 주방 PC는 랜선으로 잇고 인터넷 없이 돈다. 보드 쪽 서비스는 로컬 MQTT로 통신한다 ([decision](./2026-10-02-message-bus-mqtt.md)). 팀 개발 PC는 Mac(M1)과 Windows가 섞여 있다. 담당(최석진)은 게임 엔진·메타버스 도구 경험이 없다.
- "메타버스"는 문서에서 "가상 주방(메타버스)"로만 쓰였고, 소셜 플랫폼(온라인 접속형)이어야 한다는 요구는 저장소에 없다. 수업·멘토 쪽 요구가 있는지는 확인하지 않았다 (확인 필요).

## Options
- Option A: **Unity** — PC에서 오프라인으로 도는 3D 엔진, C# 스크립트
- Option B: Unreal / Godot — 다른 게임 엔진
- Option C: 소셜 메타버스 플랫폼 (ZEPETO, Roblox 등) — 온라인 서버에서 돈다. 랜선으로 보드와 직접 메시지를 주고받을 수 있는지는 확인하지 않았다
- Option D: 직접 만든 간단한 2D 화면 + [simulator](../../services/simulator/README.md) — PLAN 위험 표의 대체안

## Decision
- 선택한 안: **A (Unity)** (결정: 최석진)

| 기준 | Unity에서 하는 방법 | 근거 (2026-10-05 공식 문서 확인) |
|---|---|---|
| ① 보드와 메시지 | Unity 안에서 MQTT 클라이언트로 보드의 브로커에 접속해 버스 토픽을 그대로 주고받는다. 라이브러리 후보: MQTTnet **4.3.7** (MIT, .NET Standard 2.1 지원). 5.x는 .NET 8 이상 전용이라 Unity에서 바로 쓸 수 없다 | Unity 6 기본 API 호환 수준이 .NET Standard 2.1, .NET Standard용 DLL 사용 가능 ([Unity manual](https://docs.unity3d.com/6000.0/Documentation/Manual/dotnet-profile-support.html)), [MQTTnet 4.3.7](https://www.nuget.org/packages/MQTTnet/4.3.7.1207), [MQTTnet 최신](https://www.nuget.org/packages/MQTTnet) |
| ② 카메라 화면 캡처 | 인식용 카메라를 RenderTexture에 그리고 `AsyncGPUReadback` 또는 `ReadPixels`로 읽어 `EncodeToJPG`로 압축해 보낸다 | [ReadPixels](https://docs.unity3d.com/ScriptReference/Texture2D.ReadPixels.html), [EncodeToJPG](https://docs.unity3d.com/ScriptReference/ImageConversion.EncodeToJPG.html) |
| ③ 장치 상태 스크립트 | 장치마다 C# 스크립트(켜기·끄기·세기)를 붙이고, 받은 명령으로 호출한다 | Unity 기본 기능 |
| ④ 비용 | Unity Personal 무료 (최근 12개월 매출·투자 20만 달러 미만). 학생 프로젝트라 해당 | [Plans & Pricing](https://unity.com/products) |
| 실행 PC | Unity 6.3 에디터는 Windows 10 21H1 이상, macOS 13 이상(Apple Silicon 지원) | [System requirements](https://docs.unity3d.com/6000.3/Documentation/Manual/system-requirements.html) |

- 버전: **Unity 6.3 LTS** (2027-12까지 지원). 6.0 LTS는 2026-10에 지원이 끝난다 ([Unity 6 support](https://unity.com/releases/unity-6/support)). 패치 버전은 설치 후 [versions](../conventions/versions.md)에 고정한다.
- 선택 이유: 네 기준을 모두 공식 문서로 확인했고, 인터넷 없이 PC에서 돌아 보드와 랜선으로 잇기 쉽다. Windows·Mac 둘 다 에디터가 돈다. 무료다. B는 따로 확인하지 않았다 — 담당이 Unity로 시작하기로 했다. C는 ①을 확인할 수 없어 제외했다. D는 Unity가 막히면 쓰는 대체안으로 남긴다.

## Consequences
- 장점: 가상 주방 쪽 코드가 모두 C# 한 곳에 모인다. 보드 쪽은 기존 MQTT 버스를 그대로 쓴다.
- 단점:
  - 담당이 Unity·C#을 처음 배운다. 장면 1차(HW-15)와 제어 hello(HW-16)에 학습 시간이 든다.
  - MQTT 수신은 Unity 메인 스레드가 아닌 곳에서 일어난다. 장치를 움직이는 코드는 메인 스레드에서 실행하도록 넘겨야 한다.
  - 보드의 mosquitto 기본 설정은 같은 기기(localhost)에서만 접속을 받는다. 가상 주방 PC가 접속하려면 보드 쪽 설정이 필요하다 → HW-14(연결 규격)에서 정한다.
- 영향을 받는 문서·작업: [open-questions](./open-questions.md) Q-11, [versions](../conventions/versions.md), [budget](../budget.md), [overview](../architecture/overview.md), PLAN HW-13(완료)·HW-14(전달 방식)·HW-15·16·19·20, [README](../../README.md)

## Verification
- 이 결정은 공식 문서 확인만 근거로 한다. Unity를 설치해 실제로 MQTT 메시지를 주고받고 화면을 캡처한 것은 **아직 아니다 (미검증)**.
- 실제 확인: HW-16 (메시지 하나로 가상 주방의 후드 켜고 끄기), HW-20 (캡처 화면 3~5fps 전달).

## Revisit
- HW-16에서 Unity와 보드가 MQTT로 메시지를 주고받지 못할 때
- HW-20에서 캡처 화면을 3~5fps로 보낼 수 없을 때
- 수업·멘토가 소셜 메타버스 플랫폼을 요구할 때
