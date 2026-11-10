"""서비스별 CPU·메모리 측정 (#126): ps 출력 해석과 CPU 시간 차이 계산."""

import pytest

from bench import resources as r

PS = """\
  101  204800  0:02.50 /x/.venv/bin/python -u -m services.llm_svc --model m.gguf
  102  102400  1:00.00 /x/.venv/bin/python -u -m services.kitchen_gw.fake_kitchen --frames f
  103    4096  0:00.10 /x/.venv/bin/python scripts/launch.py --config scripts/launch_demo.yaml
  104   51200  00:00:03 python3 -m services.vision_svc --input kitchen
"""


def test_cputime_formats_of_mac_and_linux() -> None:
    assert r.parse_cputime("0:02.50") == pytest.approx(2.5)
    assert r.parse_cputime("1:02.34") == pytest.approx(62.34)
    assert r.parse_cputime("01:02:03") == 3723
    assert r.parse_cputime("1-00:00:01") == 86401


def test_only_service_processes_are_kept() -> None:
    procs = r.parse_ps(PS)
    assert [(p.pid, p.service) for p in procs] == [
        (101, "llm_svc"),
        (102, "fake_kitchen"),
        (104, "vision_svc"),
    ]
    assert procs[0].rss_mb == 200 and procs[1].cpu_s == 60


def test_cpu_percent_is_cpu_time_delta_over_wall_time() -> None:
    s = r.Sampler()
    s.update([r.Proc(1, "llm_svc", 300, 10.0), r.Proc(2, "vision_svc", 100, 5.0)], t=0.0)
    s.update([r.Proc(1, "llm_svc", 320, 11.5), r.Proc(2, "vision_svc", 110, 5.2)], t=1.0)
    s.update([r.Proc(1, "llm_svc", 310, 11.6), r.Proc(3, "audio_svc", 50, 1.0)], t=2.0)
    assert s.by_service["llm_svc"].cpu == pytest.approx([150.0, 10.0])
    assert s.by_service["vision_svc"].cpu == pytest.approx([20.0])
    assert "audio_svc" not in s.by_service  # 처음 본 프로세스는 다음 차례부터
    assert s.total_cpu == pytest.approx([170.0, 10.0])
    assert s.total_rss == pytest.approx([430.0, 310.0])
    table = s.report()
    assert "| llm_svc | 80.0 | 150.0 | 320 |" in table
    assert "**합계** (2초)" in table
