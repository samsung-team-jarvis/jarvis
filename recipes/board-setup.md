# Recipe: Orange Pi 보드 초기 세팅

> ⚠️ **검증 전 초안.** 실제로 세팅하면서(BOARD-02, BOARD-03) 명령과 결과를 확인하고 "(확인 필요)"를 지운다.

## 준비물

- Orange Pi 5 또는 5 Plus (**모델에 맞는 이미지**를 받아야 한다 — 5와 5 Plus 이미지는 다르다)
- microSD 32GB 이상 (또는 eMMC/NVMe), 전원 어댑터, 방열판·팬, 랜선
- Mac: balenaEtcher (이미지 굽기)

## 1. OS 설치

1. Orange Pi 공식 사이트 다운로드 페이지에서 해당 보드의 **Ubuntu 이미지**를 받는다 (Rockchip 커널 포함 이미지인지 확인 — NPU 드라이버가 들어 있어야 한다).
2. balenaEtcher로 microSD에 굽는다.
3. 보드에 꽂고 랜선 연결 후 전원.
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
sudo cat /sys/kernel/debug/rknpu/version        # NPU 드라이버 버전 (경로 확인 필요)
free -h                                         # RAM
cat /sys/class/thermal/thermal_zone*/temp       # SoC 온도 (1/1000 °C)
```

결과를 [versions.md](../docs/conventions/versions.md)에 기록한다.

## 4. 런타임 설치

- RKNN: airockchip/rknn-toolkit2 저장소의 `rknn-toolkit-lite2` 휠과 `librknnrt.so`를 **변환 툴과 같은 릴리스**로 설치 (확인 필요: 휠 경로·Python 버전 태그)
- RKLLM: airockchip/rknn-llm 저장소 README의 보드 런타임 설치 절차와 **최소 NPU 드라이버 버전 요구사항** 확인

## 5. 동작 확인

- BOARD-04: `rknn_model_zoo`의 YOLOv8 예제로 이미지 1장 추론
- BOARD-05: RKLLM 공식 데모로 지원 모델 1개 실행

## 자주 막히는 곳

- 변환 툴 버전 ≠ 보드 런타임 버전 → 로드 실패 또는 결과 이상
- 방열 없이 장시간 구동 → 스로틀링으로 속도 저하
- 전원 어댑터 출력 부족 → 랜덤 재부팅
