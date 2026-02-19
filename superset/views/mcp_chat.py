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
"""Flask blueprint for the LLM chat widget endpoint."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_login import current_user

from superset.superset_typing import FlaskResponse
from superset.views.mcp_chat_handler import LLMChatHandler

logger = logging.getLogger(__name__)

mcp_chat_bp = Blueprint("mcp_chat", __name__, url_prefix="/api/v1/mcp-chat")


@mcp_chat_bp.route("/message", methods=["POST"])
@jwt_required(optional=True)
def chat_message() -> FlaskResponse:
    """
    Handle a chat message from the LLM chat widget.

    Accepts JSON body:
      {
        "message": str,
        "history": [{"role": "user"|"assistant", "content": str}],
        "context": {
          "page": "explore"|"dashboard"|"other",
          "dataset_id": int (optional),
          "dataset_name": str (optional),
          "columns": [{"name": str, "type": str, "is_temporal": bool}] (optional),
          "current_form_data": dict (optional),
          "dashboard_title": str (optional)
        }
      }

    Returns JSON:
      {
        "role": "assistant",
        "text": str,
        "chart_explore_url": str|null,
        "sql_rows": list|null,
        "sql_columns": list|null
      }
    """
    # Accept either a JWT bearer token (API clients) or a browser session cookie.
    if not get_jwt_identity() and not current_user.is_authenticated:
        return jsonify({"error": "Authentication required"}), 401

    body = request.get_json(force=True, silent=True) or {}
    message: str = body.get("message", "")
    history: list[dict[str, str]] = body.get("history", [])
    context: dict[str, object] = body.get("context", {})

    if not message:
        return jsonify({"error": "message is required"}), 400

    try:
        handler = LLMChatHandler()
        response = handler.chat(message, history, context)
        return jsonify(response)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Error in mcp_chat /message: %s", exc)
        return jsonify({"error": str(exc)}), 500
