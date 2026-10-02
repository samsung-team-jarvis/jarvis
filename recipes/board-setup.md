# Recipe: Orange Pi 보드 초기 세팅

> 보드 미수령 상태(2026-10-02)에서 공식 자료로 확인한 내용이다. 실제 세팅(BOARD-02, BOARD-03)을 하면서 명령 결과를 확인하고, 남은 "(확인 필요)"를 지운다.

## 준비물

- Orange Pi 5 또는 5 Plus — **모델에 맞는 이미지**를 받아야 한다 (두 보드는 SoC가 다르다: 5 = RK3588S, 5 Plus = RK3588). 차이는 [hardware](../docs/architecture/hardware.md)
- 저장장치: microSD 32GB 이상, 또는 NVMe(M.2) / eMMC(5 Plus)
- 전원 어댑터, 방열판·팬, 랜선
- Mac: balenaEtcher (이미지 굽기)

## 1. OS 설치

1. Orange Pi 공식 사이트 다운로드 페이지에서 해당 보드의 **Ubuntu 이미지**를 받는다 (Rockchip 커널 포함 이미지 — NPU 드라이버가 들어 있어야 한다).
2. balenaEtcher로 microSD에 굽는다.
3. 보드에 꽂고 랜선 연결 후 전원. (Orange Pi 5는 기본 Wi-Fi가 없다 — 유선 또는 M.2 모듈)
4. 공유기 관리 페이지 등에서 보드 IP를 찾는다.

## 2. 첫 접속

```bash
ssh <기본계정>@<보드IP>      # 기본 계정·비밀번호는 공식 매뉴얼 참고 (확인 필요)
passwd                        # 비밀번호 변경
sudo apt update && sudo apt upgrade -y
sudo apt install -y git python3-venv python3-pip htop
```

Mac `~/.ssh/config`에 별칭을 등록하면 편하다 (IP·계정은 repo에 커밋하지 않는다).

```text
Host jarvis-board
  HostName <보드IP>
  User <계정>
```

VS Code: Remote-SSH 확장으로 `jarvis-board` 접속.

## 3. NPU·시스템 확인

```bash
uname -a                                        # 커널 버전
sudo cat /sys/kernel/debug/rknpu/version        # NPU 드라이버 버전 (root·debugfs 필요). RKLLM 1.3.1은 v0.9.8 이상 필요
free -h                                         # RAM
cat /sys/class/thermal/thermal_zone*/temp       # SoC 온도 (1/1000 °C)
python3 --version                               # rknn-toolkit-lite2는 Python 3.7~3.12
```

결과를 [versions.md](../docs/conventions/versions.md)에 기록한다. NPU 드라이버가 v0.9.8보다 낮으면 RKLLM이 동작하지 않으므로 이미지(커널)를 바꿔야 한다.

## 4. 런타임 설치

- RKNN: airockchip/rknn-toolkit2의 `rknn-toolkit-lite2/packages/`에서 보드 Python 버전에 맞는 **aarch64 휠**(v2.3.2)을 설치하고, 같은 릴리스의 `librknnrt.so`를 쓴다. 변환에 쓴 RKNN-Toolkit2와 버전을 맞춘다.
- RKLLM: airockchip/rknn-llm 저장소(1.3.1)의 보드 런타임(`librkllmrt.so`)과 `rkllm_api_demo`를 사용한다. 런타임은 C/C++ API다.
- STT를 NPU로 돌리려면 sherpa-onnx의 RKNN 빌드가 필요하다 ([stt-eval](./stt-eval.md)).

## 5. 동작 확인

- BOARD-04: `rknn_model_zoo`의 YOLOv8 예제로 이미지 1장 추론
- BOARD-05: RKLLM `rkllm_api_demo`로 지원 모델 1개 실행

## 자주 막히는 곳

- 변환 툴 버전 ≠ 보드 런타임 버전 → 로드 실패 또는 결과 이상
- NPU 드라이버가 낮음 → RKLLM 실행 불가 (v0.9.8 이상)
- 방열 없이 장시간 구동 → 스로틀링으로 속도 저하
- 전원 어댑터 출력 부족 → 랜덤 재부팅

## 출처 (2026-10-02 확인)

- https://github.com/airockchip/rknn-toolkit2 (`rknn-toolkit-lite2/packages`)
- https://github.com/airockchip/rknn-llm (README, SDK 문서 §2.4)
- http://www.orangepi.org/ (Orange Pi 5 / 5 Plus 제품 페이지)
