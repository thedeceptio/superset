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
import { css } from '@apache-superset/core/ui';
import { useTheme } from '@apache-superset/core/ui';

interface ChatChartPreviewProps {
  exploreUrl: string;
}

export function ChatChartPreview({ exploreUrl }: ChatChartPreviewProps) {
  const theme = useTheme();
  const iframeSrc = exploreUrl.includes('?')
    ? `${exploreUrl}&standalone=1`
    : `${exploreUrl}?standalone=1`;

  return (
    <div
      css={css`
        border: 1px solid ${theme.colorBorderSecondary};
        border-radius: ${theme.borderRadius}px;
        overflow: hidden;
        margin-top: ${theme.sizeUnit * 2}px;
      `}
    >
      <iframe
        src={iframeSrc}
        title="Chart preview"
        css={css`
          width: 100%;
          height: 300px;
          border: none;
          display: block;
        `}
      />
      <div
        css={css`
          padding: ${theme.sizeUnit}px ${theme.sizeUnit * 2}px;
          background: ${theme.colorFillAlter};
          border-top: 1px solid ${theme.colorBorderSecondary};
          font-size: ${theme.fontSizeSM}px;
        `}
      >
        <a
          href={exploreUrl}
          target="_blank"
          rel="noreferrer"
          css={css`
            color: ${theme.colorPrimary};
            text-decoration: none;
            &:hover {
              text-decoration: underline;
            }
          `}
        >
          Open in Superset →
        </a>
      </div>
    </div>
  );
}
