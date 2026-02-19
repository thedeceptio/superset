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
import { useState } from 'react';
import { css } from '@apache-superset/core/ui';
import { useTheme } from '@apache-superset/core/ui';
import { Icons } from '@superset-ui/core/components';
import { useChatContext } from './useChatContext';
import { ChatPanel } from './ChatPanel';

/**
 * Floating chat bubble that appears on every page.
 * Opens/closes the ChatPanel on click.
 */
export function ChatWidget() {
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const context = useChatContext();

  return (
    <>
      {open && <ChatPanel context={context} />}
      <button
        type="button"
        aria-label={open ? 'Close AI chat' : 'Open AI chat'}
        onClick={() => setOpen(prev => !prev)}
        css={css`
          position: fixed;
          bottom: 24px;
          right: 24px;
          z-index: 1000;
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: ${theme.colorPrimary};
          color: ${theme.colorWhite};
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
          transition: background 0.2s;
          &:hover {
            background: ${theme.colorPrimaryHover};
          }
        `}
      >
        {open ? (
          <Icons.CloseOutlined iconSize="m" />
        ) : (
          <Icons.CommentOutlined iconSize="m" />
        )}
      </button>
    </>
  );
}
