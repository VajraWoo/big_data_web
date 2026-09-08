import json
import tempfile
import unittest
from pathlib import Path

from pipelines.insight_taxonomy_mapping_job import build_mappings


def write_ndjson(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class InsightTaxonomyMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.candidates = root / "candidates"
        self.clusters = root / "clusters"
        self.taxonomy = root / "taxonomy"
        self.output = root / "output"

        common = {
            "review_id": "r1",
            "parent_asin": "p1",
            "product_category": "Ice Makers",
            "polarity": "positive",
            "target_scope": "current_product",
            "topic_raw": "ice production",
            "evidence": "Makes ice quickly.",
        }
        write_ndjson(
            self.candidates / "candidates-ice-makers.ndjson",
            [
                {"candidate_id": "a", **common},
                {"candidate_id": "b", **{**common, "review_id": "r2"}},
            ],
        )
        write_ndjson(
            self.clusters / "members-ice-makers.ndjson",
            [{"candidate_id": "a", "cluster_id": "c1", **common, "center_similarity": 0.9}],
        )
        write_ndjson(
            self.taxonomy / "taxonomy.ndjson",
            [{"taxonomy_id": "t1", "product_category": "Ice Makers", "canonical_theme_name": "Ice production"}],
        )
        write_ndjson(
            self.taxonomy / "cluster-to-taxonomy.ndjson",
            [{"first_level_cluster_id": "c1", "taxonomy_id": "t1", "product_category": "Ice Makers", "canonical_theme_name": "Ice production"}],
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_maps_clustered_and_preserves_unclustered_candidate(self) -> None:
        report = build_mappings(self.candidates, self.clusters, self.taxonomy, self.output)
        rows = [json.loads(line) for line in (self.output / "insight-taxonomy-mappings.ndjson").read_text(encoding="utf-8").splitlines()]

        self.assertEqual(2, len(rows))
        self.assertEqual("mapped_by_cluster", rows[0]["mapping_status"])
        self.assertEqual("c1", rows[0]["cluster_id"])
        self.assertEqual("t1", rows[0]["taxonomy_id"])
        self.assertEqual("unmapped_no_cluster", rows[1]["mapping_status"])
        self.assertIsNone(rows[1]["cluster_id"])
        self.assertIsNone(rows[1]["taxonomy_id"])
        self.assertEqual({"mapped_by_cluster": 1, "unmapped_no_cluster": 1}, report["mapping_status_counts"])

    def test_duplicate_candidate_id_fails(self) -> None:
        row = json.loads((self.candidates / "candidates-ice-makers.ndjson").read_text(encoding="utf-8").splitlines()[0])
        write_ndjson(self.candidates / "candidates-extra.ndjson", [row])
        with self.assertRaisesRegex(ValueError, "duplicate candidate_id"):
            build_mappings(self.candidates, self.clusters, self.taxonomy, self.output)

    def test_member_category_mismatch_fails(self) -> None:
        member = json.loads((self.clusters / "members-ice-makers.ndjson").read_text(encoding="utf-8"))
        member["product_category"] = "Washers"
        write_ndjson(self.clusters / "members-ice-makers.ndjson", [member])
        with self.assertRaisesRegex(ValueError, "category mismatch"):
            build_mappings(self.candidates, self.clusters, self.taxonomy, self.output)

    def test_orphan_cluster_mapping_fails(self) -> None:
        write_ndjson(
            self.taxonomy / "cluster-to-taxonomy.ndjson",
            [{"first_level_cluster_id": "c1", "taxonomy_id": "missing", "product_category": "Ice Makers", "canonical_theme_name": "Missing"}],
        )
        with self.assertRaisesRegex(ValueError, "unknown taxonomy_id"):
            build_mappings(self.candidates, self.clusters, self.taxonomy, self.output)


if __name__ == "__main__":
    unittest.main()
