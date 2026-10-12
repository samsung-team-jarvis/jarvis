# 산출물 (데이터 · 모델 파일) 규칙과 등록부

팀은 공용 클라우드 저장소를 쓰지 않는다. 대용량 파일은 **git에 넣지 않고, 각자 로컬에 보관하고, 메신저·USB·scp로 직접 전달**한다.
대신 이 문서의 등록부에 "어떤 파일이 어떤 버전이고 누가 갖고 있는지"를 남겨, 최신 파일을 찾고 전달 중 깨졌는지 확인한다.

## 대상

| 종류 | 예 | git |
|---|---|---|
| 모델 가중치·변환 결과 | `.pt`, `.onnx`, `.rknn`, `.rkllm` | ❌ (pre-commit·CI가 막음) |
| 원본 데이터 | 사진, 녹음(`.wav`), 영상, Roboflow zip | ❌ |
| 학교·외부 자료 원본 | `.pdf`, `.xlsx`, `.pptx`, `.docx` | ❌ (각자 학교에서 받은 것을 보관, [school-materials](./school-materials.md)) |
| 매니페스트·분할 목록·설정 | `manifest.csv`, `dataset.txt`, `config.yaml`, `metrics.json` | ✅ 커밋 (작으면) |

## 파일 이름 규칙

```text
<작업물>_<이름>_<버전>[_<설정>].<확장자>
```

| 예 | 뜻 |
|---|---|
| `vision_kitchen_v1.pt` | 비전, 주방 데이터 v1로 학습한 가중치 |
| `vision_kitchen_v1_i8.rknn` | 위 모델의 INT8 RKNN |
| `data_vision_kitchen_v1.zip` | 비전 학습 데이터 v1 (Roboflow export) |
| `llm_qwen3-0.6b_jarvis_v2_w8a8.rkllm` | LLM 학습 v2의 W8A8 변환 결과 |
| `data_stt_test_v1.zip` | STT 테스트 세트 v1 (wav + manifest) |

- 버전은 내용이 바뀔 때마다 올린다 (`v1` → `v2`). 같은 이름으로 내용이 다른 파일을 만들지 않는다.
- 변환 도구가 정한 이름(학교 도커의 `.rkllm` 등)은 바꾸지 말고 그대로 등록한다.

## 전달할 때

```bash
# 보내는 사람: 등록부 한 줄 만들기
python3 scripts/artifact_info.py vision_kitchen_v1_i8.rknn

# 받는 사람: 깨지지 않았는지 확인 (등록부의 sha256 앞 12자리)
python3 scripts/artifact_info.py --check vision_kitchen_v1_i8.rknn 029cf51129ee

# 보드로: 같은 네트워크면 scp (메신저보다 빠르고 용량 제한 없음)
scp vision_kitchen_v1_i8.rknn jarvis-board:~/models/
```

- 메신저는 파일 크기 제한이 있을 수 있다. 큰 파일(수백 MB 이상)은 USB 또는 scp.
- 학습 데이터에 팀원 목소리·얼굴이 들어 있으면 팀 밖으로 보내지 않는다.
- Roboflow 다운로드 링크(raw URL)에는 계정 키가 들어 있다. 링크를 문서·이슈·커밋에 붙이지 않는다.

## 등록부

새 파일을 만들면 PR에서 한 줄 추가한다 (`artifact_info.py` 출력 + 나머지 칸). 측정 결과는 [METRICS](./METRICS.md)에, 이 표에는 파일만.

| 파일 | 크기 | sha256(앞 12) | 만든 방법 (커밋 · 노트북/명령) | 보관자 | 날짜 |
|---|---|---|---|---|---|
| `llm_qwen3-0.6b_jarvis_v1/model.safetensors` (폴더째: 토크나이저·`train_log.json` 포함) | 1.2 GB | `865bea892252` | 1079e3c · `python -m training.llm.train_lora` (Mac MPS, 데이터 v2) | 이현종 | 2026-10-06 |
| `llm_qwen3-0.6b_jarvis_v2/model.safetensors` (폴더째) | 1.2 GB | `ca82bf78bc66` | 8d926e1 · `python -m training.llm.train_lora --extra data/llm/augment_v1.jsonl --name llm_qwen3-0.6b_jarvis_v2` (Mac MPS) | 이현종 | 2026-10-06 |
