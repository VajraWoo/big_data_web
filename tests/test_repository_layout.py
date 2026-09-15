from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RepositoryLayout(unittest.TestCase):
    def test_formal_pipeline_stages_have_discoverable_directories_and_readmes(self):
        expected = {
            "foundation": ("silver_job.py", "scope_filter_job.py"),
            "t007": ("runner.py", "contract.py", "prompt.py"),
            "t008": ("clustering", "taxonomy", "large_categories", "audit", "finalization", "review_decisions"),
            "t009": ("insight_taxonomy_mapping_job.py",),
            "t010": ("theme_aggregation_duckdb_job.py",),
            "t011": ("prepare_t011_inputs.py", "run_t011_qwen.py"),
        }

        for stage, entries in expected.items():
            stage_dir = ROOT / "pipelines" / stage
            self.assertTrue(stage_dir.is_dir(), stage)
            self.assertTrue((stage_dir / "README.md").is_file(), stage)
            for entry in entries:
                self.assertTrue((stage_dir / entry).exists(), f"{stage}/{entry}")

    def test_t008_workspaces_are_not_repository_root_directories(self):
        obsolete = (
            "t008-large-work",
            "t008_category_taxonomy_rewrite",
            "t008_cluster_audit_export",
            "t008_finish_bundle",
            "t008_large_taxonomy_pipeline",
            "t008_taxonomy_consolidation",
        )
        for name in obsolete:
            self.assertFalse((ROOT / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
