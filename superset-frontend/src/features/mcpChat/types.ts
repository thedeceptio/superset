/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

export interface ColumnInfo {
  name: string;
  type: string;
  is_temporal: boolean;
}

export interface ChatContext {
  page: 'explore' | 'dashboard' | 'other';
  dataset_id?: number;
  dataset_name?: string;
  columns?: ColumnInfo[];
  current_form_data?: Record<string, unknown>;
  dashboard_title?: string;
}

export type MessageContent =
  | { type: 'text'; content: string }
  | { type: 'chart'; explore_url: string }
  | { type: 'table'; columns: string[]; rows: Record<string, unknown>[] };

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  contents: MessageContent[];
}

export interface ApiChatResponse {
  role: 'assistant';
  text: string;
  chart_explore_url: string | null;
  sql_rows: Record<string, unknown>[] | null;
  sql_columns: string[] | null;
}
