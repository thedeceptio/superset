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
import { useLocation } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { ChatContext, ColumnInfo } from './types';

interface ExploreRootState {
  explore?: {
    form_data?: Record<string, unknown>;
    datasource?: {
      id?: number;
      name?: string;
      columns?: Array<{
        column_name?: string;
        type?: string;
        is_dttm?: boolean;
      }>;
    };
  };
}

interface DashboardRootState {
  dashboardInfo?: {
    metadata?: Record<string, unknown>;
    dash_edit_perm?: boolean;
    title?: string;
    id?: number;
  };
  // All datasources used by charts on the dashboard, keyed by "id__type" uid
  datasources?: Record<
    string,
    {
      id?: number;
      table_name?: string;
      database?: { id: number };
      columns?: Array<{
        column_name?: string;
        type?: string;
        is_dttm?: boolean;
      }>;
    }
  >;
}

type RootState = ExploreRootState & DashboardRootState;

/**
 * Reads the current page context (chart form_data, dataset columns, dashboard title)
 * from the Redux store and returns it as a ChatContext object that is passed with
 * every message to the LLM backend.
 */
export function useChatContext(): ChatContext {
  const { pathname } = useLocation();

  const exploreFormData = useSelector(
    (state: RootState) => state.explore?.form_data,
  );
  const datasource = useSelector(
    (state: RootState) => state.explore?.datasource,
  );
  const dashboardTitle = useSelector(
    (state: RootState) => state.dashboardInfo?.title,
  );
  const dashboardDatasources = useSelector(
    (state: RootState) => state.datasources,
  );

  if (pathname.startsWith('/explore')) {
    const columns: ColumnInfo[] = (datasource?.columns ?? []).map(col => ({
      name: col.column_name ?? '',
      type: col.type ?? 'UNKNOWN',
      is_temporal: Boolean(col.is_dttm),
    }));

    return {
      page: 'explore',
      dataset_id: datasource?.id,
      dataset_name: datasource?.name,
      columns,
      current_form_data: exploreFormData,
    };
  }

  if (pathname.startsWith('/dashboard') || pathname.startsWith('/superset/dashboard')) {
    // Pick the first datasource from the dashboard to give the backend a
    // dataset_id it can use to resolve the database connection for SQL queries.
    const firstDs = Object.values(dashboardDatasources ?? {})[0];
    const columns: ColumnInfo[] = (firstDs?.columns ?? []).map(col => ({
      name: col.column_name ?? '',
      type: col.type ?? 'UNKNOWN',
      is_temporal: Boolean(col.is_dttm),
    }));
    return {
      page: 'dashboard',
      dashboard_title: dashboardTitle,
      dataset_id: firstDs?.id,
      dataset_name: firstDs?.table_name,
      columns,
    };
  }

  return { page: 'other' };
}
