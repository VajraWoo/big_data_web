import json
import tempfile
import unittest
from pathlib import Path

from pipelines.t011.prepare_t011_inputs import prepare_inputs


def write_ndjson(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def mapped(
    candidate_id: str,
    review_id: str,
    parent_asin: str,
    taxonomy_id: str,
    polarity: str,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "review_id": review_id,
        "parent_asin": parent_asin,
        "product_title": f"Product {parent_asin}",
        "product_category": "Ice Makers",
        "polarity": polarity,
        "topic_raw": "noise",
        "evidence": f"evidence {candidate_id}",
        "candidate_text": f"noise: evidence {candidate_id}",
        "taxonomy_id": taxonomy_id,
        "canonical_theme_name": "Noise level",
        "mapping_status": "mapped_by_cluster",
    }


class PrepareT011InputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.source = root / "mappings.ndjson"
        self.output = root / "output"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_only_negative_groups_are_emitted_and_mixed_is_auxiliary(self) -> None:
        rows = [
            mapped("n2", "r1", "p1", "t1", "negative"),
            mapped("m1", "r1", "p1", "t1", "mixed"),
            mapped("n1", "r2", "p1", "t1", "negative"),
            mapped("m2", "r3", "p2", "t2", "mixed"),
            mapped("p1", "r4", "p3", "t3", "positive"),
            {**mapped("n3", "r5", "p4", "t4", "negative"), "mapping_status": "unmapped_no_cluster"},
        ]
        write_ndjson(self.source, rows)

        report = prepare_inputs(self.source, self.output)
        output_rows = [
            json.loads(line)
            for line in (self.output / "input.ndjson").read_text(encoding="utf-8").splitlines()
        ]

        self.assertEqual(1, len(output_rows))
        group = output_rows[0]
        self.assertEqual(("p1", "t1"), (group["parent_asin"], group["taxonomy_id"]))
        self.assertEqual(2, group["negative_insight_count"])
        self.assertEqual(1, group["mixed_insight_count"])
        self.assertEqual(3, group["support_insight_count"])
        self.assertEqual(2, group["support_review_count"])
        self.assertEqual(["n1", "n2", "m1"], [row["candidate_id"] for row in group["insights"]])
        self.assertEqual(1, report["trigger_group_count"])
        self.assertEqual(2, report["negative_insight_count"])
        self.assertEqual(1, report["usable_mixed_insight_count"])
        self.assertEqual(2, report["all_mapped_mixed_insight_count"])

    def test_duplicate_candidate_id_is_rejected(self) -> None:
        write_ndjson(
            self.source,
            [
                mapped("duplicate", "r1", "p1", "t1", "negative"),
                mapped("duplicate", "r2", "p1", "t1", "negative"),
            ],
        )

        with self.assertRaisesRegex(ValueError, "duplicate candidate_id"):
            prepare_inputs(self.source, self.output)


if __name__ == "__main__":
    unittest.main()
