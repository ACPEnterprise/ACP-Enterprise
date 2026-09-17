from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_static_document_title_matches_platform_brand_before_javascript_loads() -> None:
    index = (REPOSITORY_ROOT / "frontend/index.html").read_text(encoding="utf-8")
    brand = (REPOSITORY_ROOT / "frontend/src/branding/brandConfig.ts").read_text(
        encoding="utf-8"
    )

    assert "<title>ACP Enterprise Command Center</title>" in index
    assert 'applicationTitle: "ACP Enterprise Command Center"' in brand
    assert "<title>frontend</title>" not in index
