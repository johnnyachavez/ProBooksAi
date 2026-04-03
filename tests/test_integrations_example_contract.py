"""integrations/work-context.example.json shape for scripts/sync-workspace.ps1 consumers."""

from __future__ import annotations

import json

from tests.repo_paths import INTEGRATIONS_WORK_CONTEXT_EXAMPLE as _EXAMPLE, REPO_ROOT


def test_work_context_example_is_valid_json_with_expected_keys() -> None:
    data = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    for key in (
        "generatedAt",
        "repository",
        "repositoryUrl",
        "localWorkFiles",
        "pullRequests",
        "issues",
        "warnings",
    ):
        assert key in data, f"missing work-context.example.json key: {key!r}"
    assert isinstance(data["generatedAt"], str) and data["generatedAt"].strip()
    assert isinstance(data["repository"], str) and data["repository"].strip()
    assert isinstance(data["repositoryUrl"], str) and data["repositoryUrl"].startswith("https://")
    assert isinstance(data["localWorkFiles"], list)
    assert isinstance(data["pullRequests"], list)
    assert isinstance(data["issues"], list)
    assert isinstance(data["warnings"], list)

    paths: set[str] = set()
    for i, row in enumerate(data["localWorkFiles"]):
        assert isinstance(row, dict), f"localWorkFiles[{i}] must be an object"
        assert "path" in row and "lastWriteUtc" in row, row
        assert isinstance(row["path"], str) and row["path"].strip(), row
        assert isinstance(row["lastWriteUtc"], str) and row["lastWriteUtc"].strip(), row
        paths.add(row["path"])
    expected_paths = {
        "index.html",
        "invoice.html",
        "review.html",
        "docs/ROADMAP.md",
    }
    assert paths == expected_paths, (
        f"localWorkFiles paths should be the minimal sample set {expected_paths!r}, got {paths!r}"
    )
    assert len(data["localWorkFiles"]) == len(expected_paths), (
        "localWorkFiles should list each sample path once (no duplicate path rows)"
    )

    assert data["pullRequests"], "expected at least one sample pullRequests[] row"
    pr0 = data["pullRequests"][0]
    for key in ("number", "title", "url", "state", "headRefName", "baseRefName"):
        assert key in pr0, f"sample PR missing {key!r}"
    assert isinstance(pr0["number"], int)

    assert data["issues"], "expected at least one sample issues[] row"
    iss0 = data["issues"][0]
    for key in ("number", "title", "url", "state"):
        assert key in iss0, f"sample issue missing {key!r}"
    assert isinstance(iss0["number"], int)

    for w in data["warnings"]:
        assert isinstance(w, str), w


def test_work_context_example_warnings_literals_exist_in_sync_workspace_ps1() -> None:
    """Sample warnings[] entries must match strings sync-workspace.ps1 actually emits."""
    data = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    script = (REPO_ROOT / "scripts" / "sync-workspace.ps1").read_text(encoding="utf-8")
    for w in data["warnings"]:
        assert isinstance(w, str) and w.strip(), w
        assert w in script, (
            f"work-context.example.json warnings[] must echo a literal from sync-workspace.ps1; "
            f"missing {w!r}"
        )
