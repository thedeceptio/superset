# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Runtime validation for chart configurations.

Layer 3 of the validation pipeline. Checks for performance and usability
issues that are non-blocking — results surface as informational warnings,
never as errors that prevent chart generation.

Internal structure mirrors the test contract:
- _validate_format_compatibility  → axis/format mismatch warnings (XY only)
- _validate_cardinality           → high-cardinality warnings (XY only)
- _validate_chart_type            → chart-type appropriateness (all types)
"""

import logging

from superset.mcp_service.chart.schemas import (
    TableChartConfig,
    XYChartConfig,
)

logger = logging.getLogger(__name__)

# Readability thresholds
_MAX_Y_COLUMNS = 5
_MAX_TABLE_COLUMNS = 15

# SQL types that tend to have high cardinality
_HIGH_CARDINALITY_TYPES = {"VARCHAR", "TEXT", "STRING", "CHAR", "NVARCHAR", "CLOB"}


class RuntimeValidator:
    """
    Layer 3 validator: non-blocking performance and usability checks.

    All public methods return ``(True, metadata | None)`` so that runtime
    issues are surfaced to LLM clients as suggestions, never as hard errors.
    """

    @staticmethod
    def validate_runtime_issues(
        config: XYChartConfig | TableChartConfig,
        dataset_id: int | str,
    ) -> tuple[bool, dict[str, list[str]] | None]:
        """
        Check for performance and usability issues in the chart configuration.

        For **XY charts** all three sub-validators are called:
        ``_validate_format_compatibility``, ``_validate_cardinality``, and
        ``_validate_chart_type``.

        For **table charts** only ``_validate_chart_type`` is called because
        format and cardinality checks are XY-specific concepts.

        Args:
            config: Resolved chart configuration.
            dataset_id: Dataset identifier used for context-aware checks.

        Returns:
            ``(True, metadata)`` where *metadata* is ``None`` when nothing is
            found, or a dict with optional keys ``"warnings"`` and
            ``"suggestions"``.
        """
        warnings: list[str] = []
        suggestions: list[str] = []

        if isinstance(config, XYChartConfig):
            # Format/axis compatibility (XY-specific)
            format_warnings = RuntimeValidator._validate_format_compatibility(config)
            warnings.extend(format_warnings)

            # Cardinality / data-volume (XY-specific)
            card_warnings, card_suggestions = RuntimeValidator._validate_cardinality(
                config, dataset_id
            )
            warnings.extend(card_warnings)
            suggestions.extend(card_suggestions)

            # Chart-type appropriateness (shared, but called for XY too)
            type_warnings, type_suggestions = RuntimeValidator._validate_chart_type(
                config
            )
            warnings.extend(type_warnings)
            suggestions.extend(type_suggestions)

        elif isinstance(config, TableChartConfig):
            # Only chart-type checks for tables; format/cardinality are XY-only
            type_warnings, type_suggestions = RuntimeValidator._validate_chart_type(
                config
            )
            warnings.extend(type_warnings)
            suggestions.extend(type_suggestions)

        if not warnings and not suggestions:
            return True, None

        logger.info(
            "Runtime validation produced %d warning(s) and %d suggestion(s)",
            len(warnings),
            len(suggestions),
        )

        metadata: dict[str, list[str]] = {}
        if warnings:
            metadata["warnings"] = warnings
        if suggestions:
            metadata["suggestions"] = suggestions

        return True, metadata

    # ------------------------------------------------------------------
    # Sub-validators (mocked independently in tests)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_format_compatibility(
        config: XYChartConfig,
    ) -> list[str]:
        """
        Check for axis format / scale configuration issues.

        Returns:
            List of warning strings (may be empty).
        """
        warnings: list[str] = []

        # Log scale requires strictly positive values
        if config.y_axis and config.y_axis.scale == "log":
            warnings.append(
                "Log scale is applied to the Y-axis. Make sure all Y-axis values "
                "are strictly positive — log scale fails for zero or negative values."
            )

        # x_axis format mismatch: date-like format strings on a non-obvious axis
        if config.x_axis and config.x_axis.format:
            fmt = config.x_axis.format
            # Currency/numeric formats applied to the X-axis are often a mistake
            # when the X column is a date or categorical field.
            if any(c in fmt for c in ("$", "%", ",.")) and "date" not in fmt.lower():
                warnings.append(
                    f"X-axis format '{fmt}' looks like a numeric/currency format. "
                    "Verify that the X-axis column contains numeric data; this "
                    "format may not display dates or text values correctly."
                )

        return warnings

    @staticmethod
    def _validate_cardinality(
        config: XYChartConfig,
        dataset_id: int | str,
    ) -> tuple[list[str], list[str]]:
        """
        Check for high-cardinality patterns that can make a chart unreadable.

        Returns:
            ``(warnings, suggestions)`` — both may be empty lists.
        """
        warnings: list[str] = []
        suggestions: list[str] = []

        dataset_info = RuntimeValidator._get_dataset_info(dataset_id)

        # Warn when group_by targets a string column (likely high-cardinality)
        if config.group_by and dataset_info:
            col_name = config.group_by.name.lower()
            col_info = dataset_info.get("columns", {}).get(col_name)
            if col_info:
                col_type = col_info.get("type", "")
                if any(t in col_type for t in _HIGH_CARDINALITY_TYPES):
                    warnings.append(
                        f"group_by column '{config.group_by.name}' has SQL type "
                        f"'{col_type}', which often has many distinct values. "
                        "A chart with dozens of series becomes unreadable."
                    )
                    suggestions.append(
                        "Consider adding a filter to limit the number of groups, "
                        "or choose a lower-cardinality column for group_by."
                    )

        # Suggest time_grain when X is a datetime column without one set
        if not config.time_grain and dataset_info:
            col_info = dataset_info.get("columns", {}).get(config.x.name.lower())
            if col_info and (
                col_info.get("is_temporal") or col_info.get("is_dttm")
            ):
                suggestions.append(
                    f"X-axis column '{config.x.name}' is a datetime column but no "
                    "time_grain is set. Adding time_grain (e.g. 'P1D' for daily, "
                    "'P1M' for monthly) groups timestamps into meaningful intervals."
                )

        return warnings, suggestions

    @staticmethod
    def _validate_chart_type(
        config: XYChartConfig | TableChartConfig,
    ) -> tuple[list[str], list[str]]:
        """
        Check whether the chart type is well-suited to the column configuration.

        Returns:
            ``(warnings, suggestions)`` — both may be empty lists.
        """
        warnings: list[str] = []
        suggestions: list[str] = []

        if isinstance(config, XYChartConfig):
            # Too many Y-axis series crowd the chart
            if len(config.y) > _MAX_Y_COLUMNS:
                warnings.append(
                    f"Chart has {len(config.y)} Y-axis columns. Charts with more "
                    f"than {_MAX_Y_COLUMNS} series are hard to read."
                )
                suggestions.append(
                    "Consider splitting into multiple charts or using group_by "
                    "to create series dynamically."
                )

            # Scatter with aggregated Y columns hides individual points
            if config.kind == "scatter":
                aggregated = [col.name for col in config.y if col.aggregate]
                if aggregated:
                    warnings.append(
                        f"Scatter plot uses aggregated Y columns "
                        f"({', '.join(aggregated)}). Aggregation hides the "
                        "point distribution that scatter plots are designed to show."
                    )
                    suggestions.append(
                        "Use a bar chart for aggregated comparisons, or remove "
                        "aggregation to show raw scatter points."
                    )

            # Stacked chart with group_by may produce too many layers
            if config.stacked and config.group_by:
                warnings.append(
                    f"Stacked chart uses group_by='{config.group_by.name}'. "
                    "If this column has many distinct values the chart will have "
                    "too many stacked segments to be readable."
                )

        elif isinstance(config, TableChartConfig):
            # Too many columns make the table hard to scan
            if len(config.columns) > _MAX_TABLE_COLUMNS:
                warnings.append(
                    f"Table has {len(config.columns)} columns. Tables with more "
                    f"than {_MAX_TABLE_COLUMNS} columns are difficult to scan."
                )
                suggestions.append(
                    "Select only the most relevant columns for a cleaner table."
                )

            # Mix of aggregated and raw columns causes implicit GROUP BY
            has_aggregated = any(col.aggregate for col in config.columns)
            has_raw = any(not col.aggregate for col in config.columns)
            if has_aggregated and has_raw:
                warnings.append(
                    "Table mixes aggregated columns (SUM/COUNT/etc.) with raw "
                    "columns. Superset will implicitly GROUP BY all raw columns "
                    "to compute aggregates, which may produce unexpected results."
                )
                suggestions.append(
                    "Use only aggregated columns or only raw columns in the same "
                    "table to avoid implicit grouping surprises."
                )

        return warnings, suggestions

    # ------------------------------------------------------------------
    # Internal dataset helper
    # ------------------------------------------------------------------

    @staticmethod
    def _get_dataset_info(dataset_id: int | str) -> dict | None:
        """
        Return lightweight column metadata for the dataset, or ``None``.

        Failures are silently swallowed so that the runtime validator never
        blocks chart generation.
        """
        try:
            from superset.daos.dataset import DatasetDAO

            if isinstance(dataset_id, int) or (
                isinstance(dataset_id, str) and dataset_id.isdigit()
            ):
                dataset = DatasetDAO.find_by_id(int(dataset_id))
            else:
                dataset = DatasetDAO.find_by_id(dataset_id, id_column="uuid")

            if not dataset:
                return None

            columns: dict[str, dict] = {}
            for col in dataset.columns:
                columns[col.column_name.lower()] = {
                    "type": str(col.type).upper() if col.type else "UNKNOWN",
                    "is_temporal": getattr(col, "is_temporal", False),
                    "is_dttm": getattr(col, "is_dttm", False),
                    "is_numeric": getattr(col, "is_numeric", False),
                }

            return {
                "table_name": dataset.table_name,
                "columns": columns,
                "is_virtual": getattr(dataset, "is_virtual", False),
            }
        except Exception as exc:
            logger.debug(
                "Could not fetch dataset info for runtime checks: %s", exc
            )
            return None
