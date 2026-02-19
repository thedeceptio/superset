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
"""Unit tests for LLMChatHandler (no LLM calls, no DB required)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from superset.views.mcp_chat_handler import LLMChatHandler


@pytest.fixture()
def handler() -> LLMChatHandler:
    return LLMChatHandler()


# ---------------------------------------------------------------------------
# parse_llm_response
# ---------------------------------------------------------------------------


def test_parse_plain_text(handler: LLMChatHandler) -> None:
    result = handler.parse_llm_response("Hello, this is plain text.")
    assert result["chart_config"] is None
    assert result["sql"] is None
    assert result["text"] == "Hello, this is plain text."


def test_parse_chart_config(handler: LLMChatHandler) -> None:
    payload = {"viz_type": "bar", "time_range": "Last year"}
    llm_output = f"```chart_config\n{json.dumps(payload)}\n```"
    result = handler.parse_llm_response(llm_output)
    assert result["chart_config"] == payload
    assert result["sql"] is None


def test_parse_chart_config_case_insensitive(handler: LLMChatHandler) -> None:
    payload = {"viz_type": "line"}
    llm_output = f"```Chart_Config\n{json.dumps(payload)}\n```"
    result = handler.parse_llm_response(llm_output)
    assert result["chart_config"] == payload


def test_parse_sql(handler: LLMChatHandler) -> None:
    sql = "SELECT name, COUNT(*) FROM birth_names GROUP BY name LIMIT 5"
    llm_output = f"```sql\n{sql}\n```"
    result = handler.parse_llm_response(llm_output)
    assert result["sql"] == sql
    assert result["chart_config"] is None


def test_parse_invalid_chart_config_json_falls_through_to_text(
    handler: LLMChatHandler,
) -> None:
    llm_output = "```chart_config\nnot valid json\n```"
    result = handler.parse_llm_response(llm_output)
    # Should not raise; chart_config stays None
    assert result["chart_config"] is None
    assert result["text"] == llm_output


# ---------------------------------------------------------------------------
# _parse_datasource_string
# ---------------------------------------------------------------------------


def test_parse_datasource_string_valid(handler: LLMChatHandler) -> None:
    ds_id, ds_type = handler._parse_datasource_string("1__table")
    assert ds_id == 1
    assert ds_type == "table"


def test_parse_datasource_string_query_type(handler: LLMChatHandler) -> None:
    ds_id, ds_type = handler._parse_datasource_string("42__query")
    assert ds_id == 42
    assert ds_type == "query"


def test_parse_datasource_string_invalid(handler: LLMChatHandler) -> None:
    ds_id, ds_type = handler._parse_datasource_string("not-valid")
    assert ds_id == 0
    assert ds_type == "table"


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_explore(handler: LLMChatHandler) -> None:
    context = {
        "page": "explore",
        "dataset_name": "sales",
        "columns": [
            {"name": "revenue", "type": "DECIMAL", "is_temporal": False},
            {"name": "order_date", "type": "DATETIME", "is_temporal": True},
        ],
        "current_form_data": {"viz_type": "line", "time_range": "Last month"},
    }
    prompt = handler.build_system_prompt(context)  # type: ignore[arg-type]
    assert '"sales"' in prompt
    assert "revenue" in prompt
    assert "order_date" in prompt
    assert "(temporal)" in prompt
    assert "chart_config" in prompt
    # Table name must appear in the SQL FROM example so the LLM doesn't hallucinate
    assert 'FROM "sales"' in prompt


def test_build_system_prompt_columns_listed_on_dashboard(handler: LLMChatHandler) -> None:
    context = {
        "page": "dashboard",
        "dashboard_title": "Sales KPIs",
        "dataset_name": "sales",
        "columns": [{"name": "revenue", "type": "DECIMAL", "is_temporal": False}],
    }
    prompt = handler.build_system_prompt(context)  # type: ignore[arg-type]
    assert "Sales KPIs" in prompt
    assert "revenue" in prompt
    assert 'FROM "sales"' in prompt


def test_build_system_prompt_other_page(handler: LLMChatHandler) -> None:
    context = {"page": "other"}
    prompt = handler.build_system_prompt(context)  # type: ignore[arg-type]
    assert "chart_config" in prompt  # format rules always included


# ---------------------------------------------------------------------------
# chat() — mocked LLM, no real network calls
# ---------------------------------------------------------------------------


def _make_mock_completion(content: str) -> MagicMock:
    completion = MagicMock()
    completion.choices[0].message.content = content
    return completion


@patch("superset.views.mcp_chat_handler.LLMChatHandler.save_form_data")
@patch("litellm.completion")
def test_chat_plain_text(
    mock_completion: MagicMock,
    mock_save: MagicMock,
    handler: LLMChatHandler,
) -> None:
    mock_completion.return_value = _make_mock_completion("Hello!")

    with patch("flask.current_app") as mock_app:
        mock_app.config = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o",
            "LLM_API_KEY": "sk-test",
            "LLM_API_BASE": None,
        }
        result = handler.chat("Hi", [], {"page": "other"})  # type: ignore[arg-type]

    assert result["text"] == "Hello!"
    assert result["chart_explore_url"] is None
    assert result["sql_rows"] is None
    mock_save.assert_not_called()


@patch("superset.views.mcp_chat_handler.LLMChatHandler.save_form_data")
@patch("litellm.completion")
def test_chat_chart_config_response(
    mock_completion: MagicMock,
    mock_save: MagicMock,
    handler: LLMChatHandler,
) -> None:
    payload = {"viz_type": "bar", "time_range": "Last year", "datasource": "1__table"}
    mock_completion.return_value = _make_mock_completion(
        f"```chart_config\n{json.dumps(payload)}\n```"
    )
    mock_save.return_value = "abc123"

    context = {
        "page": "explore",
        "dataset_id": 1,
        "current_form_data": {"datasource": "1__table", "viz_type": "bar"},
    }

    with patch("flask.current_app") as mock_app:
        mock_app.config = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o",
            "LLM_API_KEY": "sk-test",
            "LLM_API_BASE": None,
        }
        result = handler.chat(
            "Show last year",
            [],
            context,  # type: ignore[arg-type]
        )

    assert result["chart_explore_url"] == "/explore/?form_data_key=abc123"
    mock_save.assert_called_once()


@patch("superset.views.mcp_chat_handler.LLMChatHandler._resolve_database_id")
@patch("superset.views.mcp_chat_handler.LLMChatHandler.execute_sql")
@patch("litellm.completion")
def test_chat_sql_response(
    mock_completion: MagicMock,
    mock_execute: MagicMock,
    mock_resolve: MagicMock,
    handler: LLMChatHandler,
) -> None:
    sql = "SELECT name, COUNT(*) as n FROM birth_names GROUP BY name LIMIT 5"
    mock_completion.return_value = _make_mock_completion(f"```sql\n{sql}\n```")
    mock_execute.return_value = {
        "columns": ["name", "n"],
        "rows": [{"name": "Alice", "n": 100}],
    }
    # dataset_id=1 resolves to database_id=2
    mock_resolve.return_value = 2

    context = {"page": "explore", "dataset_id": 1}

    with patch("flask.current_app") as mock_app:
        mock_app.config = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o",
            "LLM_API_KEY": "sk-test",
            "LLM_API_BASE": None,
        }
        result = handler.chat("Top names", [], context)  # type: ignore[arg-type]

    assert result["sql_columns"] == ["name", "n"]
    assert result["sql_rows"] == [{"name": "Alice", "n": 100}]
    mock_resolve.assert_called_once_with(1)
    mock_execute.assert_called_once_with(sql, 2)


def test_resolve_database_id_returns_none_without_dataset(
    handler: LLMChatHandler,
) -> None:
    assert handler._resolve_database_id(None) is None
    assert handler._resolve_database_id(0) is None


@patch("superset.extensions.db")
def test_resolve_database_id_queries_sqla_table(
    mock_db: MagicMock,
    handler: LLMChatHandler,
) -> None:
    fake_dataset = MagicMock()
    fake_dataset.database_id = 7
    (
        mock_db.session.query.return_value.filter.return_value.one_or_none.return_value
    ) = fake_dataset

    result = handler._resolve_database_id(3)
    assert result == 7


@patch("litellm.completion")
def test_chat_model_string_with_slash_not_double_prefixed(
    mock_completion: MagicMock,
    handler: LLMChatHandler,
) -> None:
    """gemini/gemini-2.0-flash should not become google/gemini/gemini-2.0-flash."""
    mock_completion.return_value = _make_mock_completion("OK")

    with patch("flask.current_app") as mock_app:
        mock_app.config = {
            "LLM_PROVIDER": "google",
            "LLM_MODEL": "gemini/gemini-2.0-flash",
            "LLM_API_KEY": "key",
            "LLM_API_BASE": None,
        }
        handler.chat("Hi", [], {"page": "other"})  # type: ignore[arg-type]

    called_model = mock_completion.call_args[1]["model"]
    assert called_model == "gemini/gemini-2.0-flash"
    assert called_model.count("/") == 1  # not double-prefixed
