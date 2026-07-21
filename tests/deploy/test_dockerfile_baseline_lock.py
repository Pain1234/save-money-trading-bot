"""AUD-P1-014 / #377: production Dockerfile must install the pinned baseline."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "deploy" / "Dockerfile.paper-python"


def test_paper_python_dockerfile_installs_requirements_baseline() -> None:
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "requirements-baseline.txt" in text
    assert "pip install -r requirements-baseline.txt" in text
    assert 'pip install -e ".[api]" --no-deps' in text
    # Must not resolve lower-bound deps as the sole install path.
    assert 'pip install -e ".[api]"\n' not in text.replace(
        'pip install -e ".[api]" --no-deps', ""
    )
