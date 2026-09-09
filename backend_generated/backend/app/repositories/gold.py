from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import duckdb


GOLD_DIR = Path(
    r"D:\CS_Projects\big_data_web\data\gold\t010-aggregation-20260908-v1-duckdb"
)

T011_PATH = GOLD_DIR.parent / "t011-final-corrected-20260909-v1.ndjson"
POLARITY_OVERRIDES_PATH = GOLD_DIR.parent / "t010-polarity-overrides-20260909-v1.json"


class GoldInsightsRepository:
    def __init__(
        self,
        gold_dir: Path | None = None,
        t011_path: Path | None = None,
        polarity_overrides_path: Path | None = None,
    ):
        self.gold_dir = gold_dir or GOLD_DIR

        self.products_path = self.gold_dir / "products.parquet"
        self.facets_path = self.gold_dir / "product_facets.parquet"
        self.themes_path = self.gold_dir / "themes.parquet"
        self.timeseries_path = self.gold_dir / "theme_timeseries.parquet"
        self.reviews_path = self.gold_dir / "theme_reviews.parquet"
        self.batch_path = self.gold_dir / "batch.json"
        self.validation_path = self.gold_dir / "validation.json"

        self.t011_path = t011_path or T011_PATH
        self.polarity_overrides_path = (
            polarity_overrides_path or POLARITY_OVERRIDES_PATH
        )

        required = [
            self.products_path,
            self.facets_path,
            self.themes_path,
            self.timeseries_path,
            self.reviews_path,
            self.batch_path,
            self.validation_path,
            self.t011_path,
            self.polarity_overrides_path,
        ]

        missing = [str(p) for p in required if not p.exists()]
        if missing:
            raise RuntimeError(
                "Missing Gold files:\n" + "\n".join(missing)
            )

        validation = json.loads(
            self.validation_path.read_text(encoding="utf-8")
        )

        if validation.get("status") != "ready":
            raise RuntimeError(
                f"T010 Gold is not ready: {validation}"
            )

        self._batch = json.loads(
            self.batch_path.read_text(encoding="utf-8")
        )

        self._improvements_by_product: dict[str, list[dict[str, Any]]] = (
            defaultdict(list)
        )
        with self.t011_path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Invalid T011 JSONL at line {line_number}"
                    ) from exc

                if row.get("generation_status") != "success":
                    continue

                parent_asin = row.get("parent_asin")
                taxonomy_id = row.get("taxonomy_id")
                suggestion = row.get("improvement_suggestion")

                if not (
                    isinstance(parent_asin, str)
                    and parent_asin
                    and isinstance(taxonomy_id, str)
                    and taxonomy_id
                    and isinstance(suggestion, str)
                    and suggestion.strip()
                ):
                    continue

                self._improvements_by_product[parent_asin].append(row)

        override_payload = json.loads(
            self.polarity_overrides_path.read_text(encoding="utf-8")
        )

        self._polarity_overrides: dict[tuple[str, str], str] = {}
        for correction in override_payload.get("corrections", []):
            parent_asin = correction.get("parent_asin")
            taxonomy_id = correction.get("taxonomy_id")
            to_sentiment = correction.get("to_sentiment")

            if (
                isinstance(parent_asin, str)
                and isinstance(taxonomy_id, str)
                and to_sentiment in {"positive", "negative"}
            ):
                self._polarity_overrides[
                    (parent_asin, taxonomy_id)
                ] = to_sentiment

    def _connect(self) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect()
        con.execute("PRAGMA threads=4")
        return con

    def _read_parquet_sql(self, path: Path) -> str:
        value = path.as_posix().replace("'", "''")
        return f"read_parquet('{value}')"

    def _effective_sentiment(
        self,
        parent_asin: str,
        taxonomy_id: str,
        raw_sentiment: str,
    ) -> str:
        if raw_sentiment == "negative":
            return self._polarity_overrides.get(
                (parent_asin, taxonomy_id),
                raw_sentiment,
            )
        return raw_sentiment

    def _apply_facet_count(
        self,
        facet: dict[str, Any] | None,
        facet_name: str,
        item_count: int,
    ) -> dict[str, Any]:
        value = dict(facet or {})
        value["facet"] = facet_name
        value["theme_count"] = item_count
        value["status"] = "ready" if item_count else "empty"
        value["empty_reason"] = None if item_count else "no_items"
        value["error_summary"] = None
        return value

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "repository": "gold",
            "data_source": "t010_gold+t011_gold",
            "t011_group_count": sum(
                len(items)
                for items in self._improvements_by_product.values()
            ),
            "polarity_override_count": len(self._polarity_overrides),
        }

    async def categories(self) -> list[str]:
        con = self._connect()
        try:
            rows = con.execute(
                f"""
                SELECT DISTINCT category
                FROM {self._read_parquet_sql(self.products_path)}
                WHERE category IS NOT NULL
                ORDER BY category
                """
            ).fetchall()

            return [row[0] for row in rows]
        finally:
            con.close()

    async def products(
        self,
        q: str | None,
        category: str | None,
        analysis_status: str | None,
    ) -> list[dict[str, Any]]:
        con = self._connect()

        try:
            sql = f"""
                SELECT
                    parent_asin,
                    title,
                    category,
                    review_count,
                    active_month_count,
                    last_review_month,
                    analysis_status
                FROM {self._read_parquet_sql(self.products_path)}
                WHERE 1 = 1
            """

            params: list[Any] = []

            if q:
                sql += """
                    AND (
                        LOWER(title) LIKE ?
                        OR LOWER(parent_asin) LIKE ?
                    )
                """
                needle = f"%{q.strip().lower()}%"
                params.extend([needle, needle])

            if category:
                sql += " AND category = ?"
                params.append(category)

            if analysis_status:
                sql += " AND analysis_status = ?"
                params.append(analysis_status)

            sql += " ORDER BY review_count DESC, parent_asin"

            cursor = con.execute(sql, params)

            columns = [x[0] for x in cursor.description]

            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        finally:
            con.close()

    async def product_overview(
        self,
        parent_asin: str,
    ) -> dict[str, Any] | None:
        con = self._connect()

        try:
            product_cursor = con.execute(
                f"""
                SELECT
                    parent_asin,
                    title,
                    category,
                    review_count,
                    active_month_count,
                    last_review_month,
                    analysis_status
                FROM {self._read_parquet_sql(self.products_path)}
                WHERE parent_asin = ?
                """,
                [parent_asin],
            )

            row = product_cursor.fetchone()

            if row is None:
                return None

            product_columns = [
                x[0] for x in product_cursor.description
            ]

            product = dict(zip(product_columns, row))

            facet_cursor = con.execute(
                f"""
                SELECT
                    facet,
                    status,
                    theme_count,
                    empty_reason,
                    error_summary
                FROM {self._read_parquet_sql(self.facets_path)}
                WHERE parent_asin = ?
                ORDER BY
                    CASE facet
                        WHEN 'positive_evaluation' THEN 1
                        WHEN 'negative_evaluation' THEN 2
                        WHEN 'improvement' THEN 3
                        ELSE 99
                    END
                """,
                [parent_asin],
            )

            facet_columns = [
                x[0] for x in facet_cursor.description
            ]

            raw_facets = {
                r[0]: dict(zip(facet_columns, r))
                for r in facet_cursor.fetchall()
            }

            positive = await self.product_themes(
                parent_asin,
                "positive",
            )
            negative = await self.product_themes(
                parent_asin,
                "negative",
            )

            positive_count = len(positive["items"]) if positive else 0
            negative_count = len(negative["items"]) if negative else 0
            improvement_count = len(
                self._improvements_by_product.get(parent_asin, [])
            )

            facets = [
                self._apply_facet_count(
                    raw_facets.get("positive_evaluation"),
                    "positive_evaluation",
                    positive_count,
                ),
                self._apply_facet_count(
                    raw_facets.get("negative_evaluation"),
                    "negative_evaluation",
                    negative_count,
                ),
                self._apply_facet_count(
                    raw_facets.get("improvement"),
                    "improvement",
                    improvement_count,
                ),
            ]

            return {
                "product": product,
                "facets": facets,
            }

        finally:
            con.close()

    async def product_themes(
        self,
        parent_asin: str,
        sentiment: str,
    ) -> dict[str, Any] | None:
        con = self._connect()

        try:
            product_exists = con.execute(
                f"""
                SELECT COUNT(*)
                FROM {self._read_parquet_sql(self.products_path)}
                WHERE parent_asin = ?
                """,
                [parent_asin],
            ).fetchone()[0]

            if not product_exists:
                return None

            facet_name = f"{sentiment}_evaluation"

            facet_cursor = con.execute(
                f"""
                SELECT
                    facet,
                    status,
                    theme_count,
                    empty_reason,
                    error_summary
                FROM {self._read_parquet_sql(self.facets_path)}
                WHERE parent_asin = ?
                  AND facet = ?
                """,
                [parent_asin, facet_name],
            )

            facet_row = facet_cursor.fetchone()

            facet = None
            if facet_row is not None:
                facet_columns = [
                    x[0] for x in facet_cursor.description
                ]
                facet = dict(zip(facet_columns, facet_row))

            theme_cursor = con.execute(
                f"""
                SELECT
                    theme_id,
                    taxonomy_id,
                    name,
                    sentiment,
                    review_count,
                    ratio_value,
                    ratio_status,
                    ratio_definition_id
                FROM {self._read_parquet_sql(self.themes_path)}
                WHERE parent_asin = ?
                  AND sentiment IN ('positive', 'negative')
                """,
                [parent_asin],
            )

            theme_columns = [
                x[0] for x in theme_cursor.description
            ]

            raw_rows = [
                dict(zip(theme_columns, row))
                for row in theme_cursor.fetchall()
            ]

            # Apply the 13 verified polarity corrections at presentation time.
            # If the corrected taxonomy already has a positive theme, keep that
            # canonical positive row and suppress the old negative duplicate.
            existing_positive_taxonomies = {
                raw["taxonomy_id"]
                for raw in raw_rows
                if raw["sentiment"] == "positive"
            }

            items = []

            for raw in raw_rows:
                effective_sentiment = self._effective_sentiment(
                    parent_asin,
                    raw["taxonomy_id"],
                    raw["sentiment"],
                )

                if effective_sentiment != sentiment:
                    continue

                is_corrected_negative = (
                    raw["sentiment"] == "negative"
                    and effective_sentiment == "positive"
                )

                if (
                    is_corrected_negative
                    and raw["taxonomy_id"] in existing_positive_taxonomies
                ):
                    continue

                items.append(
                    {
                        "theme_id": raw["theme_id"],
                        "taxonomy_id": raw["taxonomy_id"],
                        "name": raw["name"],
                        "sentiment": effective_sentiment,
                        "review_count": raw["review_count"],
                        "ratio": {
                            "value": raw["ratio_value"],
                            "status": raw["ratio_status"],
                            "definition_id": raw["ratio_definition_id"],
                        },
                    }
                )

            items.sort(
                key=lambda item: (
                    -(item.get("review_count") or 0),
                    item.get("name") or "",
                )
            )

            facet = self._apply_facet_count(
                facet,
                facet_name,
                len(items),
            )

            return {
                "facet": facet,
                "items": items,
            }

        finally:
            con.close()

    async def product_improvements(
        self,
        parent_asin: str,
    ) -> dict[str, Any] | None:
        con = self._connect()

        try:
            product_exists = con.execute(
                f"""
                SELECT COUNT(*)
                FROM {self._read_parquet_sql(self.products_path)}
                WHERE parent_asin = ?
                """,
                [parent_asin],
            ).fetchone()[0]

            if not product_exists:
                return None

            rows = list(
                self._improvements_by_product.get(parent_asin, [])
            )

            if not rows:
                return {
                    "facet": self._apply_facet_count(
                        None,
                        "improvement",
                        0,
                    ),
                    "items": [],
                }

            taxonomy_ids = [
                row["taxonomy_id"]
                for row in rows
            ]

            placeholders = ",".join("?" for _ in taxonomy_ids)

            theme_cursor = con.execute(
                f"""
                SELECT
                    theme_id,
                    taxonomy_id,
                    name,
                    review_count,
                    ratio_value,
                    ratio_status,
                    ratio_definition_id
                FROM {self._read_parquet_sql(self.themes_path)}
                WHERE parent_asin = ?
                  AND sentiment = 'negative'
                  AND taxonomy_id IN ({placeholders})
                """,
                [parent_asin, *taxonomy_ids],
            )

            theme_columns = [
                x[0] for x in theme_cursor.description
            ]

            themes_by_taxonomy = {
                raw["taxonomy_id"]: raw
                for raw in (
                    dict(zip(theme_columns, value))
                    for value in theme_cursor.fetchall()
                )
                if (
                    parent_asin,
                    raw["taxonomy_id"],
                ) not in self._polarity_overrides
            }

            items = []

            for row in rows:
                taxonomy_id = row["taxonomy_id"]

                # T011 final already excludes the 13 false-negative groups.
                # This check keeps the backend consistent even if a stale T011
                # file is accidentally supplied.
                if (
                    parent_asin,
                    taxonomy_id,
                ) in self._polarity_overrides:
                    continue

                theme = themes_by_taxonomy.get(taxonomy_id)

                items.append(
                    {
                        "input_id": row["input_id"],
                        "taxonomy_id": taxonomy_id,
                        "theme_id": (
                            theme["theme_id"]
                            if theme is not None
                            else None
                        ),
                        "name": row["canonical_theme_name"],
                        "improvement_suggestion": row[
                            "improvement_suggestion"
                        ],
                        "support_insight_count": row.get(
                            "support_insight_count",
                            0,
                        ),
                        "support_review_count": row.get(
                            "support_review_count",
                            0,
                        ),
                        "negative_insight_count": row.get(
                            "negative_insight_count",
                            0,
                        ),
                        "mixed_insight_count": row.get(
                            "mixed_insight_count",
                            0,
                        ),
                        "generation_mode": row.get(
                            "generation_mode",
                            "direct",
                        ),
                        "review_count": (
                            theme["review_count"]
                            if theme is not None
                            else row.get("support_review_count", 0)
                        ),
                        "ratio": (
                            {
                                "value": theme["ratio_value"],
                                "status": theme["ratio_status"],
                                "definition_id": theme[
                                    "ratio_definition_id"
                                ],
                            }
                            if theme is not None
                            else None
                        ),
                    }
                )

            items.sort(
                key=lambda item: (
                    -(item.get("review_count") or 0),
                    item.get("name") or "",
                )
            )

            return {
                "facet": self._apply_facet_count(
                    None,
                    "improvement",
                    len(items),
                ),
                "items": items,
            }

        finally:
            con.close()

    async def theme_detail(
        self,
        theme_id: str,
    ) -> dict[str, Any] | None:
        con = self._connect()

        try:
            theme_cursor = con.execute(
                f"""
                SELECT
                    theme_id,
                    parent_asin,
                    taxonomy_id,
                    name,
                    sentiment,
                    review_count,
                    ratio_value,
                    ratio_status,
                    ratio_definition_id
                FROM {self._read_parquet_sql(self.themes_path)}
                WHERE theme_id = ?
                """,
                [theme_id],
            )

            row = theme_cursor.fetchone()

            if row is None:
                return None

            columns = [
                x[0] for x in theme_cursor.description
            ]

            raw = dict(zip(columns, row))

            effective_sentiment = self._effective_sentiment(
                raw["parent_asin"],
                raw["taxonomy_id"],
                raw["sentiment"],
            )

            trend_cursor = con.execute(
                f"""
                SELECT
                    month,
                    review_count,
                    ratio_value,
                    ratio_status,
                    ratio_definition_id
                FROM {self._read_parquet_sql(self.timeseries_path)}
                WHERE theme_id = ?
                ORDER BY month
                """,
                [theme_id],
            )

            trend_columns = [
                x[0] for x in trend_cursor.description
            ]

            trend = []

            for trend_row in trend_cursor.fetchall():
                point = dict(
                    zip(trend_columns, trend_row)
                )

                trend.append(
                    {
                        "month": point["month"],
                        "review_count": point["review_count"],
                        "ratio": {
                            "value": point["ratio_value"],
                            "status": point["ratio_status"],
                            "definition_id": point["ratio_definition_id"],
                        },
                    }
                )

            return {
                "theme_id": raw["theme_id"],
                "parent_asin": raw["parent_asin"],
                "taxonomy_id": raw["taxonomy_id"],
                "name": raw["name"],
                "theme_type": "evaluation",
                "sentiment": effective_sentiment,
                "review_count": raw["review_count"],
                "ratio": {
                    "value": raw["ratio_value"],
                    "status": raw["ratio_status"],
                    "definition_id": raw["ratio_definition_id"],
                },
                "trend": trend,
            }

        finally:
            con.close()

    async def theme_reviews(
        self,
        theme_id: str,
    ) -> list[dict[str, Any]] | None:
        con = self._connect()

        try:
            theme_exists = con.execute(
                f"""
                SELECT COUNT(*)
                FROM {self._read_parquet_sql(self.themes_path)}
                WHERE theme_id = ?
                """,
                [theme_id],
            ).fetchone()[0]

            if not theme_exists:
                return None

            cursor = con.execute(
                f"""
                SELECT
                    review_id,
                    text,
                    evidence_text,
                    rating,
                    review_date,
                    review_month
                FROM {self._read_parquet_sql(self.reviews_path)}
                WHERE theme_id = ?
                ORDER BY review_date DESC NULLS LAST
                """,
                [theme_id],
            )

            columns = [
                x[0] for x in cursor.description
            ]

            return [
                dict(zip(columns, row))
                for row in cursor.fetchall()
            ]

        finally:
            con.close()

    async def batch(self) -> dict[str, Any]:
        value = dict(self._batch)
        value["t011_file"] = self.t011_path.name
        value["t011_group_count"] = sum(
            len(items)
            for items in self._improvements_by_product.values()
        )
        value["polarity_override_file"] = (
            self.polarity_overrides_path.name
        )
        value["polarity_override_count"] = len(
            self._polarity_overrides
        )
        return value
