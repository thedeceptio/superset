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
import { Message } from './types';
import { ChatChartPreview } from './ChatChartPreview';
import { ChatTablePreview } from './ChatTablePreview';

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const theme = useTheme();
  const isUser = message.role === 'user';

  return (
    <div
      css={css`
        display: flex;
        flex-direction: column;
        align-items: ${isUser ? 'flex-end' : 'flex-start'};
        margin-bottom: ${theme.sizeUnit * 2}px;
      `}
    >
      {message.contents.map((content, idx) => {
        if (content.type === 'text') {
          return (
            <div
              // eslint-disable-next-line react/no-array-index-key
              key={idx}
              css={css`
                max-width: 85%;
                padding: ${theme.sizeUnit * 1.5}px ${theme.sizeUnit * 2}px;
                border-radius: ${theme.borderRadiusLG}px;
                background: ${isUser
                  ? theme.colorPrimary
                  : theme.colorFillAlter};
                color: ${isUser ? theme.colorWhite : theme.colorText};
                font-size: ${theme.fontSizeSM}px;
                line-height: 1.5;
                white-space: pre-wrap;
                word-break: break-word;
              `}
            >
              {content.content}
            </div>
          );
        }

        if (content.type === 'chart') {
          return (
            <div
              // eslint-disable-next-line react/no-array-index-key
              key={idx}
              css={css`
                width: 100%;
              `}
            >
              <ChatChartPreview exploreUrl={content.explore_url} />
            </div>
          );
        }

        if (content.type === 'table') {
          return (
            <div
              // eslint-disable-next-line react/no-array-index-key
              key={idx}
              css={css`
                width: 100%;
              `}
            >
              <ChatTablePreview columns={content.columns} rows={content.rows} />
            </div>
          );
        }

        return null;
      })}
    </div>
  );
}
