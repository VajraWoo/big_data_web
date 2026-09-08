from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb


GOLD_DIR = Path(
    r"D:\CS_Projects\big_data_web\data\gold\t010-aggregation-20260908-v1-duckdb"
)


class GoldInsightsRepository:
    def __init__(self, gold_dir: Path | None = None):
        self.gold_dir = gold_dir or GOLD_DIR

        self.products_path = self.gold_dir / "products.parquet"
        self.facets_path = self.gold_dir / "product_facets.parquet"
        self.themes_path = self.gold_dir / "themes.parquet"
        self.timeseries_path = self.gold_dir / "theme_timeseries.parquet"
        self.reviews_path = self.gold_dir / "theme_reviews.parquet"
        self.batch_path = self.gold_dir / "batch.json"
        self.validation_path = self.gold_dir / "validation.json"

        required = [
            self.products_path,
            self.facets_path,
            self.themes_path,
            self.timeseries_path,
            self.reviews_path,
            self.batch_path,
            self.validation_path,
        ]

        missing = [str(p) for p in required if not p.exists()]
        if missing:
            raise RuntimeError(
                "Missing T010 Gold files:\n" + "\n".join(missing)
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

    def _connect(self) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect()
        con.execute("PRAGMA threads=4")
        return con

    def _read_parquet_sql(self, path: Path) -> str:
        value = path.as_posix().replace("'", "''")
        return f"read_parquet('{value}')"

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "repository": "gold",
            "data_source": "t010_gold",
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

            facets = [
                dict(zip(facet_columns, r))
                for r in facet_cursor.fetchall()
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
                    name,
                    sentiment,
                    review_count,
                    ratio_value,
                    ratio_status,
                    ratio_definition_id
                FROM {self._read_parquet_sql(self.themes_path)}
                WHERE parent_asin = ?
                  AND sentiment = ?
                ORDER BY review_count DESC, name
                """,
                [parent_asin, sentiment],
            )

            theme_columns = [
                x[0] for x in theme_cursor.description
            ]

            items = []

            for row in theme_cursor.fetchall():
                raw = dict(zip(theme_columns, row))

                items.append(
                    {
                        "theme_id": raw["theme_id"],
                        "name": raw["name"],
                        "sentiment": raw["sentiment"],
                        "review_count": raw["review_count"],
                        "ratio": {
                            "value": raw["ratio_value"],
                            "status": raw["ratio_status"],
                            "definition_id": raw["ratio_definition_id"],
                        },
                    }
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
                  AND facet = 'improvement'
                """,
                [parent_asin],
            )

            row = facet_cursor.fetchone()

            facet = None

            if row is not None:
                columns = [
                    x[0] for x in facet_cursor.description
                ]
                facet = dict(zip(columns, row))

            return {
                "facet": facet,
                "items": [],
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
                "name": raw["name"],
                "theme_type": "evaluation",
                "sentiment": raw["sentiment"],
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
        return dict(self._batch)