# 비용 목록

돈이 드는 항목과 무료 대안. **💰 표시 항목은 구매·결제 전에 팀에서 확인한다.** 가격은 구매할 때 아래 "구매 기록"에 실제 금액으로 적는다 (추정 가격은 쓰지 않는다).

## 💰 구매가 필요한 하드웨어

2026-10-05 시연 환경을 가상 주방으로 바꿔 **실물 제어 하드웨어(ESP32·센서·모형·웹캠·BT 동글)는 사지 않는다** ([decision](./decisions/2026-10-05-virtual-kitchen-demo.md)). 학교·멘토사에서 지급되는 것이 있으면 먼저 확인하고, 없는 것만 산다. 근거: [hardware](./architecture/hardware.md), [PLAN BOM](./PLAN.md)

| 품목 | 수량 | 필수 | 비고 |
|---|---|---|---|
| Orange Pi 5 계열 보드 + 전원 어댑터 | 1 | 필수 | 학교 특강 기준 **Orange Pi 5 Plus 16GB가 배포 이미지와 함께 지급**되는 것으로 보임 → 지급이면 구매 불필요 |
| 방열판 + 팬 (보드용) | 1 | 필수 | 장시간 구동 시 스로틀링 방지 |
| microSD 64GB 이상 (또는 NVMe) | 1 | 필수 | OS·모델 저장 |
| USB 핀마이크 (또는 USB 사운드카드 + 핀마이크) | 1 | 필수 | |
| 소형 스피커 (USB 또는 3.5mm) | 1 | 필수 | TTS 음성 응답·경고용 (STT-12). 보드의 오디오 출력 단자는 수령 후 확인 |
| 랜선 | 1 | 필수 | 보드 ↔ 가상 주방 PC |

## 무료로 쓰는 것 (결제 불필요)

| 항목 | 용도 | 조건·주의 |
|---|---|---|
| GitHub (org, public 저장소, Actions) | 코드·CI | public 저장소라 브랜치 보호·Actions 무료 |
| Google Colab 무료 | 학습·모델 변환 | GPU 사용 시간 한도가 있다. 부족하면 💰 유료 플랜을 상의 |
| RKNN-Toolkit2, RKLLM, sherpa-onnx, ultralytics, mosquitto, paho-mqtt | 변환·추론·통신 | 오픈소스 |
| Hugging Face | LLM 다운로드 | 계정 무료 |
| Roboflow 무료 플랜 | 비전 라벨링 | 무료 플랜 조건(데이터셋 공개 여부·한도)을 가입 시 확인 ([Q-09](./decisions/open-questions.md)). 대안: Label Studio·CVAT(무료) |
| Claude Code / Codex 등 AI 도구 | 개발 보조 | 각자 계정·요금제 (팀 비용 아님) |

## 💰 유료 가능성이 있는 서비스 (쓰기 전에 확인)

| 서비스 | 언제 필요해지나 | 기본 결정 |
|---|---|---|
| Unity 유료 플랜·에셋 스토어 유료 에셋 (가상 주방) | Personal로 안 되는 기능이 필요하거나 유료 3D 모델을 쓰고 싶을 때 | **Unity Personal(무료)로 진행** — 최근 12개월 매출·투자 20만 달러 미만이면 무료 (2026-10-05 [공식 페이지](https://unity.com/products) 확인, [decision](./decisions/2026-10-05-unity-virtual-kitchen.md)). 에셋은 무료 에셋을 먼저 쓰고, 유료가 필요하면 결제 전에 상의 |
| 클라우드 GPU 서버 (A100, 학교 특강의 "대여 클라우드 GPU") | LLM 학습·RKLLM 변환 | 학교·멘토사 제공으로 보이지만 **팀이 비용을 내는 대여인지 확인 필요**. 유료라면 Colab 무료로 대체 가능 (`convert_rkllm.ipynb`, 단 학습 시간·메모리 한계) |
| Colab 유료 플랜 | 무료 GPU 한도로 학습이 반복적으로 끊길 때 | 무료로 진행, 필요 시 상의 |
| CodeRabbit (AI 코드 리뷰) | `.coderabbit.yaml`은 있으나 앱 미설치 | **요금 조건을 확인한 뒤** 설치 여부 결정 (설치 안 해도 CI·리뷰 규칙은 동작) |
| Roboflow 유료 플랜 | 데이터셋을 비공개로 해야 하는데 무료 조건이 안 맞을 때 | Label Studio·CVAT(무료)로 대체 |

## 구매 기록

| 날짜 | 품목 | 수량 | 금액 | 구매자 | 비고 |
|---|---|---|---|---|---|
