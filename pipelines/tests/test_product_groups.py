import unittest

from pipelines.product_groups import canonical_product_group, evaluate_candidate, select_candidates


class ProductGroupRules(unittest.TestCase):
    def test_uses_deepest_specific_category_and_stable_slug(self):
        group = canonical_product_group(
            ["Appliances", "Refrigerators", "Ice Makers"],
            main_category="Appliances",
        )

        self.assertEqual(
            group,
            {
                "group_id": "ice-makers",
                "name": "Ice Makers",
                "category_depth": 3,
                "category_path": ["Appliances", "Refrigerators", "Ice Makers"],
            },
        )

    def test_rejects_empty_and_only_generic_category_paths(self):
        self.assertIsNone(canonical_product_group([], "Appliances"))
        self.assertIsNone(canonical_product_group(["Appliances", "Home & Kitchen"], None))
        self.assertIsNone(canonical_product_group(["Appliances", "Replacement Parts"], None))

    def test_candidate_gate_reports_every_failed_dimension(self):
        decision = evaluate_candidate(
            {
                "review_count": 4000,
                "product_count": 8,
                "eligible_text_rate": 0.69,
                "active_months": 11,
                "metadata_identifiability": 0.79,
                "category_depth": 1,
            }
        )

        self.assertEqual(decision["selection_state"], "rejected")
        self.assertEqual(
            decision["rejection_reasons"],
            [
                "reviews_below_5000",
                "products_below_10",
                "eligible_text_rate_below_0.70",
                "active_months_below_12",
                "metadata_identifiability_below_0.80",
                "category_depth_below_2",
            ],
        )

    def test_selects_two_highest_predeclared_scores_with_stable_tie_break(self):
        rows = [
            {"group_id": "washers", "name": "Washers", "review_count": 20000, "product_count": 40,
             "eligible_text_rate": .90, "active_months": 80, "metadata_identifiability": .98, "category_depth": 3},
            {"group_id": "ice-makers", "name": "Ice Makers", "review_count": 30000, "product_count": 60,
             "eligible_text_rate": .91, "active_months": 90, "metadata_identifiability": .99, "category_depth": 3},
            {"group_id": "ranges", "name": "Ranges", "review_count": 10000, "product_count": 20,
             "eligible_text_rate": .85, "active_months": 60, "metadata_identifiability": .95, "category_depth": 3},
        ]

        selected = select_candidates(rows, minimum_selected=2)

        self.assertEqual(
            [row["group_id"] for row in selected if row["selection_state"] == "selected"],
            ["ice-makers", "washers"],
        )
        self.assertTrue(all("selection_score" in row for row in selected))
        self.assertEqual(selected[-1]["selection_state"], "candidate")

    def test_selected_groups_must_come_from_different_semantic_families(self):
        rows = [
            {"group_id": "water-filters", "name": "Water Filters", "review_count": 30000, "product_count": 50,
             "eligible_text_rate": .9, "active_months": 80, "metadata_identifiability": .98, "category_depth": 3},
            {"group_id": "reusable-filters", "name": "Reusable Filters", "review_count": 25000, "product_count": 45,
             "eligible_text_rate": .9, "active_months": 80, "metadata_identifiability": .98, "category_depth": 3},
            {"group_id": "ice-makers", "name": "Ice Makers", "review_count": 20000, "product_count": 40,
             "eligible_text_rate": .9, "active_months": 80, "metadata_identifiability": .98, "category_depth": 3},
        ]

        selected = select_candidates(rows, minimum_selected=2)

        self.assertEqual(
            [row["group_id"] for row in selected if row["selection_state"] == "selected"],
            ["water-filters", "ice-makers"],
        )


if __name__ == "__main__":
    unittest.main()
