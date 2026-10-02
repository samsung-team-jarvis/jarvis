# recorder — 메시지 녹화기

버스에 오가는 모든 메시지를 세션별 JSONL 파일로 남긴다. 녹화 파일은 데이터셋(FUS-10), 지연 측정(INFRA-06), 재생 회귀 테스트(FUS-11)에 같이 쓴다. (PLAN INFRA-05)

## 실행

```bash
python -m services.recorder                                   # 모든 토픽 → data/sessions/<session_id>.jsonl
python -m services.recorder --topic 'stt/#' --out /tmp/rec    # 일부 토픽만, 다른 폴더로
python -m services.recorder summary data/sessions/<세션>.jsonl # 토픽별 개수·길이 요약
```

종료는 Ctrl+C 또는 SIGTERM. 종료할 때 세션·토픽별 녹화 개수를 출력한다.

## Spec

| 항목 | 내용 |
|---|---|
| 역할 | `--topic`(기본 `#`) 구독 → 메시지를 `session_id`별 파일에 한 줄씩 기록 |
| 하지 않는 일 | 메시지 수정·필터링·재발행 (재생은 FUS-11에서 `read_session`으로 구현) |
| 입력 | 버스의 모든 토픽 |
| 출력 | `data/sessions/<session_id>.jsonl` (git 제외). 한 줄 = 봉투 JSON |
| 설정 | `--out`, `--bus`(기본 `JARVIS_BUS`), `--topic` |
| 실패 시 | 줄마다 즉시 flush → 갑자기 죽어도 그 직전까지 남음. 규격에 맞지 않는 메시지는 버스 단계에서 무시됨 |
| 파일 이름 | `session_id`에서 `/`·공백 등을 `_`로 바꿔 경로 밖으로 나가지 않게 함 |

## 녹화 파일을 코드에서 읽기

```python
from services.recorder.store import read_session, summarize

for msg in read_session("data/sessions/sim_overheat_20261002_124005.jsonl"):
    print(msg.mono, msg.type, msg.payload)     # Envelope 객체 (common.messages)

print(summarize("data/sessions/....jsonl"))   # {"messages", "by_topic", "duration_s", ...}
```

- `read_session(path, strict=False)`: 쓰다 끊긴 마지막 줄 같은 깨진 줄은 건너뛴다. `strict=True`면 몇 번째 줄인지 알려 주며 오류를 낸다.
- 녹화 파일은 크기가 커질 수 있어 git에 넣지 않는다. 데이터로 쓸 녹화는 [산출물 등록부](../../docs/artifacts.md)에 기록하고 직접 전달한다.
