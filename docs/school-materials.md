# 학교 제공 자료 (마음AI)

> ⚠️ 원본은 저작권(ⓒ MAUM.AI)이 있어 **이 public 저장소에 올리지 않는다.** 각자 학교에서 받은 파일을 보관하고, 문서에는 자료명·쪽 번호만 적는다. `.gitignore`가 `*.pdf`, `*.xlsx`를 막는다.

| 자료 | 내용 | 주로 쓰는 작업 |
|---|---|---|
| 특강2 「Orange Pi 5+ 기반 On-device AI — LLM 학습·평가 → 양자화·포팅·서빙 → 음성 연동」 (39쪽) | 모델 선정, A100 서버·보드 환경, chat template·eos, 대화 데이터, 파인튜닝, 평가, RKLLM 변환 도커(`run.sh`), 보드 검증, C API·서빙(FastAPI), 성능 측정, 음성 파이프라인(VAD·STT·TTS) | LLM-*, BOARD-*, STT-* |
| SUDA 데이터 시트 「2025 AI Expo HomeIoT」 | 가전 제어 함수 정의(docstring), 함수 토큰 출력 형식, 싱글턴·멀티턴(슬롯 필링), 간접 발화, STT 오인식 변형 데이터, train/eval 분리 | LLM-01~05 |
| SUDA 데이터 시트 「Jeju bus」 | 기획 시트(기능 분류·키워드·어투·데이터 비율·생성 프롬프트), 차수별 train/eval(1차 → 2-1차), 숫자 읽기 데이터, 잡담(chitchat) 클래스 | LLM-02~05, LLM-10·11 |

## 우리 계획에 반영한 내용

### 학교 제공 환경 (특강 p.8, 18, 23, 28, 34~35)
- 보드: Orange Pi 5 Plus · RK3588 · RAM 16GB · Ubuntu 22.04 배포 이미지, RKNPU 드라이버 v0.9.8 사전 설치, `~/voice/models`에 VAD·STT·TTS 모델 사전 배치
- 학습·변환: x86_64 클라우드 GPU 서버(A100 80GB) + 제공 도커. 변환은 `./run.sh check → calib → convert → build-demo`
- 서빙: 보드에서 제공 FastAPI 서버(OpenAI 호환 `/v1/chat/completions`, ctypes로 librkllmrt 로드)
- → [결정 사항](./decisions/open-questions.md) Q-01·03, [llm-to-rkllm](../recipes/llm-to-rkllm.md), [board-setup](../recipes/board-setup.md)

### 지켜야 할 규칙 (특강)
- RKLLM 변환 입력은 **병합된 fp16/fp32 HF 모델** (어댑터 파일만으로는 변환 불가, p.12)
- chat template·system 지시·종료 토큰을 학습·평가·캘리브레이션·보드 추론에서 **동일하게** (p.9, 24). 종료 토큰은 `config.json`·`generation_config.json`의 `eos_token_id`에도 (빠지면 캘리브레이션 target이 설명문으로 길어짐, p.25)
- RK3588은 w8a8 계열만 (w4a16은 RK3576용, p.21). `target_platform: RK3588`, `num_npu_core: 3`은 전 팀 고정 (p.26)
- 캘리브레이션 300~1,000건, 실제 발화를 학습과 같은 형식으로, 유형·말투를 고르게 (p.22, 25)
- 같은 문항으로 ① 기본 모델 ② 학습 모델 ③ 양자화 모델(보드) 비교 (p.14, 32)
- 측정 전 **클럭 고정** `sudo bash fix_freq_rk3588.sh`, `RKLLM_LOG_LEVEL=1`로 TTFT·tok/s 로그 (p.28~29)
- `llm_demo`·런타임의 `max_context_len`은 변환 시 `max_context` 이하 (p.29~30)
- 음성 파이프라인 기본 배치: STT 4스레드·TTS 2스레드는 CPU, NPU는 LLM (p.34)

### SUDA 방식에서 가져온 것 (데이터 시트)
- **LLM 출력 형식**: JSON 대신 함수 토큰 형식 `<fn_id>(arg=값, ...)<end>` — 출력 토큰이 짧아 생성 시간이 줄고, 종료 토큰으로 생성을 끊기 쉽다 → [Q-10](./decisions/open-questions.md)
- **함수 정의를 docstring으로**: 함수·인자·값 목록을 명확히 적은 Function Description을 데이터 설계의 기준으로 둔다
- **대상이 불명확하면 `-1`** (멀티턴에서 되묻기) → 우리 `ASK_CLARIFY`
- **간접 발화**: "음식이 식었어" → 오븐 켜기처럼 의도만 말하는 문장을 Seed에 포함
- **STT 오인식 변형**: "오븐" → "5븐"·"오분"처럼 STT가 틀리게 적는 형태를 학습 데이터에 섞음 → STT-10
- **숫자 표기 변형**: "793-2" ↔ "칠백구십삼다시이"처럼 숫자를 글자로 읽은 형태 → 화구 번호·타이머 분 데이터
- **생성 프롬프트 + 키워드 목록 + 어투(명령문·공손한 요청·평서문)**로 Paraphrase를 만들고 기능별 데이터 비율을 정함 → LLM-04
- **차수별 개선**: 1차 → 1-1차 → 2차 → 2-1차로 train/eval을 고쳐 가며 재학습 → Phase 5
- **지원 외 요청은 별도 클래스** (`<General_Conversation>()`) → 우리 `UNSUPPORTED`

## 참고 수치 (우리 측정 아님)

특강 p.32의 RK3588 공식 벤치마크 (w8a8, 64 tokens). [METRICS](./METRICS.md)에 "참고"로만 둔다.

| 모델 | 크기 | TTFT | tok/s | 메모리 |
|---|---|---|---|---|
| Qwen3 | 0.6B | 214 ms | 32.2 | 774 MB |
| TinyLLAMA (≈ Llama 3.2 1B) | 1.1B | 239 ms | 24.5 | 1,085 MB |
| Qwen2.5 | 1.5B | 412 ms | 16.3 | 1,659 MB |
