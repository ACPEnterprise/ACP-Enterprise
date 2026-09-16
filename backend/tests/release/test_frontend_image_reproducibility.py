from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def image_references(dockerfile: Path) -> list[str]:
    return [
        line.split()[1]
        for line in dockerfile.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ")
    ]


def test_all_frontend_artifacts_use_the_same_digest_pinned_base_images() -> None:
    tenant = image_references(REPOSITORY_ROOT / "frontend" / "Dockerfile")
    mission_control = image_references(
        REPOSITORY_ROOT / "frontend" / "Dockerfile.mission-control"
    )

    assert mission_control == tenant
    assert len(tenant) == 2
    assert all("@sha256:" in image for image in tenant)
