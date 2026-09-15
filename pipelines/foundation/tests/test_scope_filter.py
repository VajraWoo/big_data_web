import unittest

from pipelines.foundation.scope_filter import (
    classify_product_category,
    product_passes_scope,
    review_is_in_analysis_period,
)


class ScopeFilterCategoryRules(unittest.TestCase):
    def test_accepts_specific_whole_appliance_categories(self):
        self.assertEqual(
            classify_product_category(
                ["Appliances", "Refrigerators, Freezers & Ice Makers", "Ice Makers"]
            ),
            ("included", "Ice Makers"),
        )
        self.assertEqual(
            classify_product_category(
                ["Appliances", "Laundry Appliances", "Washers & Dryers", "Portable Washers"]
            ),
            ("included", "Portable Washers"),
        )

    def test_excludes_parts_accessories_and_consumables(self):
        self.assertEqual(
            classify_product_category(
                ["Appliances", "Parts & Accessories", "Refrigerator Parts & Accessories", "Water Filters"]
            )[0],
            "excluded",
        )
        self.assertEqual(
            classify_product_category(
                ["Small Appliance Parts & Accessories", "Coffee Filters", "Reusable Filters"]
            )[0],
            "excluded",
        )

    def test_does_not_accept_generic_or_unknown_paths(self):
        self.assertEqual(classify_product_category(["Appliances"])[0], "review")
        self.assertEqual(
            classify_product_category(["Appliances", "Gerhards Appliances"])[0],
            "review",
        )

    def test_product_scope_does_not_require_positive_or_negative_counts(self):
        self.assertTrue(
            product_passes_scope(
                review_count=300,
                active_months=12,
                last_review_month="2023-09",
                active_since_month="2022-10",
                positive_count=0,
                negative_count=0,
            )
        )

    def test_analysis_period_accepts_all_dated_historical_reviews(self):
        self.assertTrue(review_is_in_analysis_period("2005-01", "2023-09"))
        self.assertTrue(review_is_in_analysis_period("2023-09", "2023-09"))
        self.assertFalse(review_is_in_analysis_period(None, "2023-09"))
        self.assertFalse(review_is_in_analysis_period("2023-10", "2023-09"))


if __name__ == "__main__":
    unittest.main()
