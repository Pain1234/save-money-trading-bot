# Railway dashboard bundle must not expose private API URL
from pathlib import Path


def test_dashboard_client_uses_server_side_env_only() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "src/lib/paper-api/client.ts"
    ).read_text(encoding="utf-8")
    assert "process.env.PRIVATE_PAPER_API_URL" in source
    assert "NEXT_PUBLIC_" not in source
