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
"""LLM handler for the context-aware chat widget.

Supports multiple LLM providers via LiteLLM.  Configure in superset_config.py:

    LLM_PROVIDER = "openai"        # openai | anthropic | google | azure | ollama
    LLM_MODEL = "gpt-4o"
    LLM_API_KEY = "sk-..."
    LLM_API_BASE = None            # optional override (Azure, Ollama, etc.)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypedDict

from flask import current_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------


class ColumnInfo(TypedDict):
    name: str
    type: str
    is_temporal: bool


class ChatContext(TypedDict, total=False):
    page: str
    dataset_id: int
    dataset_name: str
    columns: list[ColumnInfo]
    current_form_data: dict[str, Any]
    dashboard_title: str


class HistoryItem(TypedDict):
    role: str
    content: str


class ParsedResponse(TypedDict, total=False):
    chart_config: dict[str, Any] | None
    sql: str | None
    text: str


class ChatResponse(TypedDict, total=False):
    role: str
    text: str
    chart_explore_url: str | None
    sql_rows: list[dict[str, Any]] | None
    sql_columns: list[str] | None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class LLMChatHandler:
    """Orchestrates context-aware LLM chat for Superset."""

    def build_system_prompt(self, context: ChatContext) -> str:
        """Build a system prompt that includes dataset schema and chart config."""
        lines: list[str] = [
            "You are a data analyst assistant inside Apache Superset.",
            "Your job is to help the user explore and modify their charts and dashboards.",
            "",
        ]

        page = context.get("page", "other")
        dataset_name = context.get("dataset_name", "")
        columns: list[ColumnInfo] = context.get("columns", [])
        form_data = context.get("current_form_data")
        dashboard_title = context.get("dashboard_title", "")

        # Always show the schema block when we have a dataset, regardless of page.
        if dataset_name and columns:
            lines += [
                "## Available data",
                f'Table name (use this EXACTLY in SQL FROM clauses): "{dataset_name}"',
                "Columns:",
            ]
            for col in columns:
                temporal_tag = " (temporal)" if col.get("is_temporal") else ""
                lines.append(
                    f'  - {col["name"]} ({col.get("type", "UNKNOWN")}{temporal_tag})'
                )
            lines.append("")
        elif dataset_name:
            lines += [
                "## Available data",
                f'Table name (use this EXACTLY in SQL FROM clauses): "{dataset_name}"',
                "",
            ]

        if page == "explore":
            if dataset_name:
                lines.append(
                    f'The user is viewing a chart built on dataset "{dataset_name}".'
                )
            if form_data:
                lines.append("Current chart configuration (form_data):")
                lines.append("```json")
                lines.append(json.dumps(form_data, indent=2, default=str))
                lines.append("```")
            lines.append("")

        elif page == "dashboard" and dashboard_title:
            lines.append(f'The user is viewing the dashboard "{dashboard_title}".')
            lines.append("")

        # Build the SQL example line using the real table name so the LLM has
        # a concrete anchor and cannot hallucinate an alternative name.
        from_clause = f'"{dataset_name}"' if dataset_name else "<table>"
        lines += [
            "## Response format — pick exactly one",
            "1. To modify the chart, output a fenced code block tagged `chart_config`",
            "   containing ONLY the updated form_data JSON (no extra keys):",
            "   ```chart_config",
            "   { ... }",
            "   ```",
            f"2. To query data, write a SQL SELECT against {from_clause}.",
            "   Use ONLY the table and columns listed above — do NOT invent or assume",
            "   any other table names or column names that are not listed.",
            "   ```sql",
            f"   SELECT ... FROM {from_clause} WHERE ...",
            "   ```",
            "3. For explanations or anything else, respond with plain text.",
            "",
            "Be concise. Do not mix formats in a single response.",
        ]
        return "\n".join(lines)

    def parse_llm_response(self, text: str) -> ParsedResponse:
        """Extract chart_config JSON or SQL from the LLM response."""
        # Match ```chart_config ... ```
        chart_match = re.search(
            r"```chart_config\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
        )
        if chart_match:
            raw = chart_match.group(1).strip()
            try:
                chart_config = json.loads(raw)
                return ParsedResponse(chart_config=chart_config, sql=None, text=text)
            except json.JSONDecodeError:
                logger.warning("LLM returned invalid chart_config JSON: %s", raw[:200])

        # Match ```sql ... ```
        sql_match = re.search(
            r"```sql\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE
        )
        if sql_match:
            sql = sql_match.group(1).strip()
            return ParsedResponse(chart_config=None, sql=sql, text=text)

        return ParsedResponse(chart_config=None, sql=None, text=text)

    @staticmethod
    def _parse_datasource_string(
        datasource: str,
    ) -> tuple[int, str]:
        """Parse 'N__type' datasource string into (id, type) tuple."""
        parts = datasource.split("__", 1)
        if len(parts) == 2:
            try:
                return int(parts[0]), parts[1]
            except ValueError:
                pass
        return 0, "table"

    def save_form_data(
        self, form_data: dict[str, Any], context: "ChatContext"
    ) -> str | None:
        """Persist form_data using Superset's internal command (avoids HTTP self-calls)."""
        try:
            from superset.commands.explore.form_data.create import CreateFormDataCommand
            from superset.commands.explore.form_data.parameters import CommandParameters

            # datasource_id is required by the command.  Try multiple sources:
            # 1. Explicit integer field in form_data / original form_data
            # 2. Parse the "N__type" datasource string
            # 3. Fall back to context.dataset_id
            original_fd = context.get("current_form_data") or {}

            datasource_id: int = 0
            datasource_type: str = "table"

            # Check explicit fields first
            if form_data.get("datasource_id"):
                datasource_id = int(form_data["datasource_id"])
                datasource_type = form_data.get("datasource_type", "table")
            elif original_fd.get("datasource_id"):
                datasource_id = int(original_fd["datasource_id"])
                datasource_type = original_fd.get("datasource_type", "table")
            else:
                # Parse "N__type" string from either form_data
                raw_ds = form_data.get("datasource") or original_fd.get("datasource")
                if raw_ds:
                    datasource_id, datasource_type = self._parse_datasource_string(
                        str(raw_ds)
                    )

            # Last resort: use context.dataset_id
            if not datasource_id:
                datasource_id = context.get("dataset_id") or 0
            # Merge LLM overrides on top of original form_data so the full config
            # (including datasource_id) is preserved.
            merged: dict[str, Any] = {**original_fd, **form_data}
            args = CommandParameters(
                datasource_id=datasource_id,
                datasource_type=datasource_type,
                chart_id=merged.get("slice_id"),
                tab_id=None,
                form_data=json.dumps(merged),
            )
            key: str = CreateFormDataCommand(args).run()
            return key
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Could not persist form_data: %s", exc)
        return None

    @staticmethod
    def _resolve_database_id(dataset_id: int | None) -> int | None:
        """Return the Database.id for a given SqlaTable (dataset) id.

        Falls back to the first available database when dataset_id is absent or
        cannot be resolved — common in single-database Superset setups.
        """
        if dataset_id:
            try:
                from superset.connectors.sqla.models import SqlaTable
                from superset.extensions import db

                dataset = (
                    db.session.query(SqlaTable)
                    .filter(SqlaTable.id == dataset_id)
                    .one_or_none()
                )
                if dataset:
                    return dataset.database_id
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Could not resolve database_id from dataset %s: %s",
                    dataset_id,
                    exc,
                )

        # Fallback: use the first available database connection
        try:
            from superset.daos.database import DatabaseDAO

            databases = DatabaseDAO.find_all()
            if databases:
                logger.info(
                    "No dataset_id in context; using database '%s' (id=%s) as fallback",
                    databases[0].database_name,
                    databases[0].id,
                )
                return databases[0].id
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Could not find any database: %s", exc)

        return None

    def execute_sql(
        self, sql: str, database_id: int | None
    ) -> dict[str, Any]:
        """Execute SQL directly via the Database model (avoids HTTP self-calls)."""
        if not database_id:
            return {"error": "No database_id in context — cannot execute SQL."}

        try:
            from superset.daos.database import DatabaseDAO

            db_obj = DatabaseDAO.find_by_id(database_id)
            if not db_obj:
                return {"error": f"Database {database_id} not found."}

            with db_obj.get_sqla_engine() as engine:
                with engine.connect() as conn:
                    result = conn.execute(
                        __import__("sqlalchemy").text(sql)
                    )
                    columns: list[str] = list(result.keys())
                    rows: list[dict[str, Any]] = [
                        dict(zip(columns, row)) for row in result.fetchmany(500)
                    ]
                    return {"columns": columns, "rows": rows}
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("SQL execution error: %s", exc)
            return {"error": str(exc)}

    def chat(
        self,
        message: str,
        history: list[HistoryItem],
        context: ChatContext,
    ) -> ChatResponse:
        """Full chat flow: build prompt → call LLM → parse → execute/save."""
        try:
            import litellm  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError(
                "litellm is not installed. Run `pip install litellm` in the Superset "
                "virtual environment."
            ) from exc

        cfg = current_app.config
        provider: str = cfg.get("LLM_PROVIDER", "openai")
        model: str = cfg.get("LLM_MODEL", "gpt-4o")
        api_key: str | None = cfg.get("LLM_API_KEY")
        api_base: str | None = cfg.get("LLM_API_BASE")

        system_prompt = self.build_system_prompt(context)

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for item in history:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": message})

        # Build model string for litellm.
        # If the model already contains a "/" it is fully-qualified (e.g.
        # "gemini/gemini-2.0-flash", "ollama/llama3") — use as-is.
        # OpenAI models have no slash and need no prefix.
        # Everything else gets the provider prefix.
        if "/" in model or provider == "openai":
            model_str = model
        else:
            model_str = f"{provider}/{model}"

        litellm_kwargs: dict[str, Any] = {
            "model": model_str,
            "messages": messages,
            "temperature": 0.2,
        }
        if api_key:
            litellm_kwargs["api_key"] = api_key
        if api_base:
            litellm_kwargs["api_base"] = api_base

        completion = litellm.completion(**litellm_kwargs)
        llm_text: str = completion.choices[0].message.content or ""

        parsed = self.parse_llm_response(llm_text)

        response: ChatResponse = {
            "role": "assistant",
            "text": llm_text,
            "chart_explore_url": None,
            "sql_rows": None,
            "sql_columns": None,
        }

        if parsed.get("chart_config"):
            form_data_key = self.save_form_data(parsed["chart_config"], context)
            if form_data_key:
                response["chart_explore_url"] = (
                    f"/explore/?form_data_key={form_data_key}"
                )

        elif parsed.get("sql"):
            database_id: int | None = self._resolve_database_id(
                context.get("dataset_id")  # type: ignore[arg-type]
            )
            result = self.execute_sql(parsed["sql"], database_id)
            if "error" not in result:
                response["sql_rows"] = result.get("rows")
                response["sql_columns"] = result.get("columns")
            else:
                response["text"] = llm_text + f"\n\n[SQL Error: {result['error']}]"

        return response
