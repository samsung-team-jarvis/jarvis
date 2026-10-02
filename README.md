# JARVIS — 온디바이스 스마트 주방 어시스턴트

1인 주방에서 손을 쓰기 어려운 작업자를 위해, 음성·비전·온도/전류 센서를 Orange Pi(RK3588 NPU)에서 **오프라인으로** 융합 추론하고, Safety Guard를 거쳐 ESP32(BLE)로 주방 장비(모형)를 제어한다.

2026-2 모바일시스템응용프로젝트 · 삼성팀 (신지호 · 이현종 · 최지환 · 최석진) · 산업체 멘토 마음AI

## 빠른 시작

```bash
git clone https://github.com/samsung-team-jarvis/jarvis.git
cd jarvis
python3 -m venv .venv && source .venv/bin/activate
pip install pre-commit ruff && pre-commit install
```

자세한 환경 구성: [Local Development](docs/workflows/local-development.md)

## 작업 방식

모든 작업은 **이슈 → 브랜치 → PR → 머지**로 진행한다. → [Git Convention](docs/conventions/git.md)

## 문서

- [문서 인덱스](docs/index.md)
- [작업 계획 (PLAN)](docs/PLAN.md)
- [아키텍처](docs/architecture/overview.md) · [인터페이스 규격](docs/architecture/interfaces.md)
- [평가 지표 (METRICS)](docs/METRICS.md)
- [결정 기록](docs/decisions/index.md)
- [Agent Guide](AGENTS.md)
