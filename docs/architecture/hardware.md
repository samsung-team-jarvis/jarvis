# Hardware Reference

보드와 주변 장치. 2026-10-02 제조사 페이지로 확인했다 (아래 출처). 실제 보드는 아직 미수령이며, 학교 특강 기준 **Orange Pi 5 Plus · 16GB · 배포 이미지**가 기준이다 ([open-questions](../decisions/open-questions.md) Q-01, [school-materials](../school-materials.md)).

## 메인 보드: Orange Pi 5 vs 5 Plus

| | Orange Pi 5 | Orange Pi 5 Plus |
|---|---|---|
| SoC | RK3588S | RK3588 |
| NPU | 6 TOPS, 3코어 (같음) | 6 TOPS, 3코어 (같음) |
| RAM | 4 / 8 / 16GB LPDDR4/4X | 4 / 8 / 16GB LPDDR4/4X |
| 이더넷 | 1× Gigabit | 2× 2.5GbE |
| 저장장치 | M.2 M-key (PCIe 2.0, NVMe), eMMC 소켓 없음 | M.2 2280 NVMe (PCIe 3.0 x4) + eMMC 소켓 |
| Wi-Fi / BT | **보드 내장 무선 없음** (별도 모듈) | M.2 E-key 슬롯 (Wi-Fi6/BT 모듈을 꽂아야 함) |
| USB | USB 3.0 ×1, USB 2.0 ×2, Type-C ×1 | USB 3.0 ×2, USB 2.0 ×2, Type-C ×1 |
| 영상 | HDMI 2.1 ×1 | HDMI 출력 ×2, HDMI 입력 ×1, MIPI CSI ×1 |

**이 프로젝트에서의 의미**
- NPU 사양(6 TOPS, 3코어)이 같다. 보드 선택은 I/O(무선, USB, 저장장치) 차이로 판단한다.
- 가상 주방(PC)과 메시지·화면을 주고받으므로 **네트워크 연결**이 필요하다. 이더넷은 두 보드 모두 있다. Wi-Fi는 두 보드 모두 별도 모듈이 필요하다 → 유선 연결을 기본으로 한다.
- USB 장치는 마이크와 스피커뿐이다.
- RAM은 STT + LLM + YOLO 동시 구동을 고려하면 8GB 이상이 안전하다 (실측으로 확정, BOARD-08).

## 주변 장치

| 장치 | 용도 | 비고 |
|---|---|---|
| USB 핀마이크 | 음성 입력 (실제 음성) | 노트북 내장 마이크와 비교 측정 예정 (STT-09) |
| 소형 스피커 | TTS 음성 응답·경고 | 보드의 오디오 출력 단자는 수령 후 확인 |
| PC (팀원 노트북) | 가상 주방 실행 | 플랫폼이 요구하는 사양은 플랫폼 선정(HW-13) 때 확인 |

## 쓰지 않는 것 (2026-10-05 결정)

시연 환경을 가상 주방으로 바꾸면서 아래는 쓰지 않는다 ([decision](../decisions/2026-10-05-virtual-kitchen-demo.md)). 카메라 화면과 온도는 가상 주방에서 받는다.

- ESP32, BLE 모듈·동글, 저전압 모형(LED·USB 팬·릴레이·부저)
- USB 웹캠
- 온도 센서(K형 열전대 + MAX31855), 전류 센서(INA219)

## 안전 원칙

- 실물 가스·220V·가열 장치를 다루지 않는다. 화구·튀김기·후드는 가상 주방 안의 장치다 ([안전 3계층](../decisions/2026-10-01-safety-layers.md)).

## 출처 (2026-10-02 확인)

- http://www.orangepi.org/ (Orange-Pi-5, Orange-Pi-5-plus 제품 페이지)
- https://www.rock-chips.com/ (RK3588 제품 페이지 — NPU 6TOPS, triple core)
