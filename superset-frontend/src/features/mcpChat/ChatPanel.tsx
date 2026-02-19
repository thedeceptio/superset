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
import { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { css } from '@apache-superset/core/ui';
import { useTheme } from '@apache-superset/core/ui';
import { SupersetClient } from '@superset-ui/core';
import { Spin } from 'antd';
import { v4 as uuidv4 } from 'uuid';
import { ChatContext, Message, ApiChatResponse, MessageContent } from './types';
import { ChatMessage } from './ChatMessage';

interface ChatPanelProps {
  context: ChatContext;
}

function buildContextChip(context: ChatContext): string {
  if (context.page === 'explore' && context.dataset_name) {
    return `Chatting about: ${context.dataset_name} chart`;
  }
  if (context.page === 'dashboard' && context.dashboard_title) {
    return `Chatting about: ${context.dashboard_title}`;
  }
  return 'Chat with your data';
}

function apiResponseToContents(resp: ApiChatResponse): MessageContent[] {
  const contents: MessageContent[] = [];

  if (resp.text) {
    // Strip the chart_config / sql code fence from display text
    const displayText = resp.text
      .replace(/```chart_config[\s\S]*?```/gi, '')
      .replace(/```sql[\s\S]*?```/gi, '')
      .trim();
    if (displayText) {
      contents.push({ type: 'text', content: displayText });
    }
  }

  if (resp.chart_explore_url) {
    contents.push({ type: 'chart', explore_url: resp.chart_explore_url });
  }

  if (resp.sql_rows && resp.sql_columns) {
    contents.push({
      type: 'table',
      columns: resp.sql_columns,
      rows: resp.sql_rows,
    });
  }

  if (contents.length === 0) {
    contents.push({ type: 'text', content: resp.text || '(no response)' });
  }

  return contents;
}

export function ChatPanel({ context }: ChatPanelProps) {
  const theme = useTheme();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: uuidv4(),
      role: 'user',
      contents: [{ type: 'text', content: text }],
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const history = messages.map(m => ({
        role: m.role,
        content: m.contents
          .filter(c => c.type === 'text')
          .map(c => (c as { type: 'text'; content: string }).content)
          .join('\n'),
      }));

      const response = await SupersetClient.post({
        endpoint: '/api/v1/mcp-chat/message',
        jsonPayload: { message: text, history, context },
      });

      const json = response.json as ApiChatResponse;
      const assistantMsg: Message = {
        id: uuidv4(),
        role: 'assistant',
        contents: apiResponseToContents(json),
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err) {
      // SupersetClient throws plain objects on HTTP errors, not Error instances.
      let detail = 'Unknown error';
      if (err instanceof Error) {
        detail = err.message;
      } else if (err && typeof err === 'object') {
        const e = err as Record<string, unknown>;
        detail =
          (e.message as string) ||
          (e.error as string) ||
          JSON.stringify(e).slice(0, 200);
      } else if (typeof err === 'string') {
        detail = err;
      }
      // eslint-disable-next-line no-console
      console.error('[ChatWidget] sendMessage error:', err);
      const errMsg: Message = {
        id: uuidv4(),
        role: 'assistant',
        contents: [{ type: 'text', content: `Error: ${detail}` }],
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.stopPropagation();
      sendMessage();
    }
  };

  return (
    <div
      css={css`
        position: fixed;
        bottom: 80px;
        right: 24px;
        width: 380px;
        height: 520px;
        background: ${theme.colorBgContainer};
        border: 1px solid ${theme.colorBorderSecondary};
        border-radius: ${theme.borderRadiusLG}px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
        display: flex;
        flex-direction: column;
        z-index: 1001;
        overflow: hidden;
      `}
    >
      {/* Header */}
      <div
        css={css`
          padding: ${theme.sizeUnit * 2}px ${theme.sizeUnit * 3}px;
          background: ${theme.colorPrimary};
          color: ${theme.colorWhite};
          font-weight: ${theme.fontWeightStrong};
          font-size: ${theme.fontSize}px;
        `}
      >
        AI Assistant
      </div>

      {/* Context chip */}
      <div
        css={css`
          padding: ${theme.sizeUnit}px ${theme.sizeUnit * 2}px;
          background: ${theme.colorPrimaryBg};
          font-size: ${theme.fontSizeSM}px;
          color: ${theme.colorPrimaryText};
          border-bottom: 1px solid ${theme.colorBorderSecondary};
        `}
      >
        {buildContextChip(context)}
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        css={css`
          flex: 1;
          overflow-y: auto;
          padding: ${theme.sizeUnit * 2}px;
        `}
      >
        {messages.length === 0 && (
          <div
            css={css`
              color: ${theme.colorTextTertiary};
              font-size: ${theme.fontSizeSM}px;
              text-align: center;
              margin-top: ${theme.sizeUnit * 6}px;
            `}
          >
            Ask me anything about your data or chart.
            <br />
            <span
              css={css`
                font-style: italic;
              `}
            >
              e.g. "Show this for the last year" or "Top 5 regions by revenue"
            </span>
          </div>
        )}
        {messages.map(msg => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        {loading && (
          <div
            css={css`
              display: flex;
              justify-content: flex-start;
              padding: ${theme.sizeUnit}px 0;
            `}
          >
            <Spin size="small" />
          </div>
        )}
      </div>

      {/* Input */}
      <div
        css={css`
          display: flex;
          gap: ${theme.sizeUnit}px;
          padding: ${theme.sizeUnit * 2}px;
          border-top: 1px solid ${theme.colorBorderSecondary};
        `}
      >
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your data… (Enter to send)"
          rows={2}
          disabled={loading}
          css={css`
            flex: 1;
            resize: none;
            border: 1px solid ${theme.colorBorder};
            border-radius: ${theme.borderRadius}px;
            padding: ${theme.sizeUnit}px ${theme.sizeUnit * 1.5}px;
            font-size: ${theme.fontSizeSM}px;
            font-family: inherit;
            outline: none;
            &:focus {
              border-color: ${theme.colorPrimary};
            }
          `}
        />
        <button
          type="button"
          onClick={e => {
            e.stopPropagation();
            sendMessage();
          }}
          disabled={loading || !input.trim()}
          css={css`
            padding: ${theme.sizeUnit}px ${theme.sizeUnit * 2}px;
            background: ${theme.colorPrimary};
            color: ${theme.colorWhite};
            border: none;
            border-radius: ${theme.borderRadius}px;
            cursor: pointer;
            font-size: ${theme.fontSizeSM}px;
            font-weight: ${theme.fontWeightStrong};
            align-self: flex-end;
            &:disabled {
              opacity: 0.5;
              cursor: not-allowed;
            }
            &:hover:not(:disabled) {
              background: ${theme.colorPrimaryHover};
            }
          `}
        >
          Send
        </button>
      </div>
    </div>
  );
}
