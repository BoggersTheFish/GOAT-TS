from pathlib import Path


def test_phase5_operational_assets_exist() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "infra" / "terraform" / "main.tf").exists()
    assert (root / "infra" / "ansible" / "site.yml").exists()
    assert (
        root / "src" / "monitoring" / "grafana" / "ts-overview-dashboard.json"
    ).exists()
