from pathlib import Path

from app.repositories.gold import resolve_default_gold_paths


def test_default_gold_paths_follow_the_repository_location(tmp_path: Path):
    module_path = (
        tmp_path
        / "moved-project"
        / "backend_generated"
        / "backend"
        / "app"
        / "repositories"
        / "gold.py"
    )

    gold_dir, t011_path, overrides_path = resolve_default_gold_paths(
        module_path
    )
    gold_root = tmp_path / "moved-project" / "data" / "gold"

    assert gold_dir == (
        gold_root / "t010-aggregation-20260908-v1-duckdb"
    )
    assert t011_path == (
        gold_root / "t011-final-corrected-20260909-v1.ndjson"
    )
    assert overrides_path == (
        gold_root / "t010-polarity-overrides-20260909-v1.json"
    )
