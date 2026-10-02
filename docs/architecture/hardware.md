# Hardware Reference

부품 선택 근거. 2026-10-02 제조사 페이지·데이터시트로 확인했다 (아래 출처). 실제 보드는 아직 미수령 ([open-questions](../decisions/open-questions.md) Q-01).

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
- ESP32와 BLE로 통신해야 하는데, **두 보드 모두 기본 상태로는 BT를 쓸 수 없다** → Wi-Fi/BT 모듈 또는 USB BT 동글이 필요하다 (BOM 반영). 어떤 모듈·동글이 Orange Pi 커널에서 동작하는지는 확인 필요 — 보드 수령 후 HW-03에서 확정.
- USB 장치(마이크, 웹캠, BT 동글)를 동시에 쓰므로 USB 포트 수를 확인한다.
- RAM은 STT + LLM + YOLO 동시 구동을 고려하면 8GB 이상이 안전하다 (실측으로 확정, BOARD-08).

## 센서

| 부품 | 측정 범위 · 정밀도 | 판단 |
|---|---|---|
| DS18B20 | −55 ~ **+125°C**, ±0.5°C (−10~85°C) | ❌ 튀김 기름 온도(약 170~190°C) 측정 불가 |
| MAX6675 + K형 열전대 | 0 ~ +1024°C, 12비트, 0.25°C | △ 동작은 하지만 단종·신규 설계 비권장이라는 2차 자료가 있음 (제조사 1차 확인 못 함) |
| **MAX31855 + K형 열전대** | −270 ~ +1800°C 판독, 14비트, 0.25°C, K형 ±2°C (−200~700°C), 3.0~3.6V | ✅ **기본 선택** (ESP32 3.3V와 맞음) |
| **INA219** | 버스 전압 0~26V, 분류(shunt) 전압·버스 전압 측정 → 전류·전력 계산, I2C, 12비트 | ✅ 저전압 DC 모형 부하 전류 측정. 220V 교류 측정용 아님 |

## 안전 원칙

- 실물 가스·220V를 제어·계측하지 않는다. 화구·후드는 저전압 모형(LED, USB 팬, 부저, 릴레이)으로 만든다 ([안전 3계층](../decisions/2026-10-01-safety-layers.md)).

## 출처 (2026-10-02 확인)

- http://www.orangepi.org/ (Orange-Pi-5, Orange-Pi-5-plus 제품 페이지)
- https://www.rock-chips.com/ (RK3588 제품 페이지 — NPU 6TOPS, triple core)
- DS18B20, MAX6675, MAX31855 데이터시트 (https://cdn-shop.adafruit.com/datasheets/DS18B20.pdf , MAX6675.pdf , MAX31855.pdf)
- https://www.ti.com/product/INA219
