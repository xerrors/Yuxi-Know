/**
 * 聊天对话HTML导出工具类
 * 用于将聊天对话导出为HTML文件
 */

export class ChatExporter {
  /**
   * 导出聊天对话为HTML文件
   * @param {Object} options 导出选项
   * @param {string} options.chatTitle 对话标题
   * @param {string} options.agentName 智能体名称
   * @param {string} options.agentDescription 智能体描述
   * @param {Array} options.messages 消息列表
   * @param {Array} options.onGoingMessages 进行中的消息列表
   */
  static async exportToHTML(options) {
    const {
      chatTitle = '新对话',
      agentName = '智能助手',
      agentDescription = '',
      messages = [],
      onGoingMessages = []
    } = options;

    try {
      // 生成HTML内容
      const htmlContent = this.generateHTML({
        chatTitle,
        agentName,
        agentDescription,
        messages,
        onGoingMessages
      });

      // 创建下载链接
      const blob = new Blob([htmlContent], { type: 'text/html;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');

      // 生成文件名
      const timestamp = new Date().toLocaleString('zh-CN').replace(/[:/\s]/g, '-');
      const filename = `${chatTitle}-${timestamp}.html`;

      link.href = url;
      link.download = filename;
      link.style.display = 'none';

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      // 清理URL对象
      URL.revokeObjectURL(url);

      return { success: true, filename };
    } catch (error) {
      console.error('导出对话失败:', error);
      throw new Error(`导出失败: ${error.message}`);
    }
  }

  /**
   * 生成HTML内容
   * @param {Object} options 生成选项
   * @returns {string} HTML内容
   */
  static generateHTML(options) {
    const {
      chatTitle,
      agentName,
      agentDescription,
      messages,
      onGoingMessages
    } = options;

    const exportTime = new Date().toLocaleString('zh-CN');

    // 合并所有消息
    const allMessages = [];

    // 添加历史对话消息
    messages.forEach(conv => {
      if (conv.messages) {
        conv.messages.forEach(msg => {
          allMessages.push(msg);
        });
      }
    });

    // 添加当前进行中的对话消息
    onGoingMessages.forEach(msg => {
      allMessages.push(msg);
    });

    if (allMessages.length === 0) {
      throw new Error('没有可导出的对话内容');
    }

    // 生成消息HTML
    const messagesHTML = this.generateMessagesHTML(allMessages, agentName);

    // 返回完整的HTML文档
    return this.generateHTMLTemplate({
      chatTitle,
      agentName,
      agentDescription,
      exportTime,
      messagesHTML
    });
  }

  /**
   * 生成消息HTML
   * @param {Array} messages 消息列表
   * @param {string} agentName 智能体名称
   * @returns {string} 消息HTML
   */
  static generateMessagesHTML(messages, agentName) {
    return messages.map((msg, index) => {
      const isUser = msg.type === 'human';
      const avatar = isUser ? '👤' : '🤖';
      const senderName = isUser ? '用户' : agentName;
      const messageClass = isUser ? 'user-message' : 'ai-message';

      // 处理消息内容
      let content = (msg.content || '').trim();
      content = content.replace(/\n/g, '<br>');

      // 处理思考过程
      const reasoningHTML = this.generateReasoningHTML(msg, isUser);

      // 处理工具调用
      const toolCallsHTML = this.generateToolCallsHTML(msg);

      return `
        <div class="message ${messageClass}">
          <div class="message-header">
            <span class="avatar">${avatar}</span>
            <span class="sender">${senderName}</span>
            <span class="time">${new Date().toLocaleString('zh-CN')}</span>
          </div>
          <div class="message-content">
            ${reasoningHTML}
            ${content}
            ${toolCallsHTML}
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * 生成思考过程HTML
   * @param {Object} msg 消息对象
   * @param {boolean} isUser 是否为用户消息
   * @returns {string} 思考过程HTML
   */
  static generateReasoningHTML(msg, isUser) {
    if (isUser) return '';

    const reasoningContent = msg.additional_kwargs?.reasoning_content || msg.reasoning_content;
    if (!reasoningContent) return '';

    const content = reasoningContent.trim().replace(/\n/g, '<br>');
    return `
      <div class="reasoning-section">
        <div class="reasoning-header">💭 思考过程</div>
        <div class="reasoning-content">${content}</div>
      </div>
    `;
  }

  /**
   * 生成工具调用HTML
   * @param {Object} msg 消息对象
   * @returns {string} 工具调用HTML
   */
  static generateToolCallsHTML(msg) {
    if (!msg.tool_calls || msg.tool_calls.length === 0) return '';

    let toolCallsHTML = '<div class="tool-calls">';
    
    msg.tool_calls.forEach(toolCall => {
      const args = toolCall.function?.arguments 
        ? JSON.parse(toolCall.function.arguments) 
        : toolCall?.args || '{}';
      
      toolCallsHTML += `
        <div class="tool-call">
          <div class="tool-call-header">
            <strong>🔧 ${toolCall.function?.name || '工具调用'}</strong>
          </div>
          <div class="tool-call-args">
            <pre>${JSON.stringify(args, null, 2)}</pre>
          </div>
          ${toolCall.tool_call_result ? `
            <div class="tool-call-result">
              <div class="tool-result-header">执行结果:</div>
              <div class="tool-result-content">${toolCall.tool_call_result.content || ''}</div>
            </div>
          ` : ''}
        </div>
      `;
    });
    
    toolCallsHTML += '</div>';
    return toolCallsHTML;
  }

  /**
   * 生成完整的HTML模板
   * @param {Object} options 模板选项
   * @returns {string} 完整的HTML文档
   */
  static generateHTMLTemplate(options) {
    const { chatTitle, agentName, agentDescription, exportTime, messagesHTML } = options;

    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${chatTitle} - 对话导出</title>
    <style>
        ${this.getCSS()}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>${chatTitle}</h1>
            <div class="agent-info">
                <strong>智能体:</strong> ${agentName}
                ${agentDescription ? `<br><strong>描述:</strong> ${agentDescription}` : ''}
            </div>
            <div class="export-info">
                导出时间: ${exportTime}
            </div>
        </div>
        <div class="messages">
            ${messagesHTML}
        </div>
        <div class="footer">
            <p>此对话由 <a href="#" target="_blank">智能助手平台</a> 导出</p>
        </div>
    </div>
</body>
</html>`;
  }

  /**
   * 获取CSS样式
   * @returns {string} CSS样式字符串
   */
  static getCSS() {
    return `
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: white;
            margin: 0;
            padding: 0;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            min-height: 100vh;
        }

        .header {
            background: #f8f9fa;
            border-bottom: 2px solid #e9ecef;
            padding: 24px;
            text-align: center;
        }

        .header h1 {
            font-size: 24px;
            margin-bottom: 8px;
            color: #212529;
            font-weight: 600;
        }

        .header .agent-info {
            font-size: 14px;
            color: #6c757d;
            margin-bottom: 12px;
        }

        .header .export-info {
            font-size: 12px;
            color: #868e96;
            padding-top: 12px;
            border-top: 1px solid #dee2e6;
        }

        .messages {
            padding: 32px 48px;
            max-width: 100%;
        }

        .message {
            margin-bottom: 32px;
            max-width: 100%;
        }

        .message:last-child {
            margin-bottom: 0;
        }

        .message-header {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            font-size: 14px;
            color: #666;
        }

        .avatar {
            font-size: 16px;
            margin-right: 8px;
        }

        .sender {
            font-weight: 600;
            margin-right: 12px;
        }

        .time {
            font-size: 12px;
            color: #999;
        }

        .message-content {
            padding: 16px 20px;
            border-radius: 8px;
            width: 100%;
            max-width: 100%;
        }

        .user-message .message-content {
            color: white;
            background: #1C6586;
            border: 1px solid #1C6586;
            width: fit-content;
        }

        .ai-message .message-content {
            background: white;
            border: 1px solid #e9ecef;
        }

        .reasoning-section {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 16px;
        }

        .reasoning-header {
            font-size: 13px;
            font-weight: 600;
            color: #495057;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
        }

        .reasoning-content {
            font-size: 14px;
            color: #6c757d;
            font-style: italic;
            line-height: 1.5;
        }

        .tool-calls {
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid #e9ecef;
        }

        .tool-call {
            background: #fff8e1;
            border: 1px solid #ffe082;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 12px;
        }

        .tool-call:last-child {
            margin-bottom: 0;
        }

        .tool-call-header {
            font-size: 14px;
            color: #f57f17;
            margin-bottom: 8px;
            font-weight: 600;
        }

        .tool-call-args {
            background: rgba(0,0,0,0.04);
            border-radius: 4px;
            padding: 8px;
            margin-bottom: 8px;
        }

        .tool-call-args pre {
            font-size: 12px;
            color: #666;
            white-space: pre-wrap;
            word-break: break-all;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        }

        .tool-call-result {
            background: #e8f5e8;
            border: 1px solid #c8e6c9;
            border-radius: 4px;
            padding: 8px;
            word-break: break-all;
        }

        .tool-result-header {
            font-size: 12px;
            color: #2e7d32;
            font-weight: 600;
            margin-bottom: 4px;
        }

        .tool-result-content {
            font-size: 13px;
            color: #388e3c;
        }

        .footer {
            background: #f8f9fa;
            text-align: center;
            padding: 16px;
            font-size: 12px;
            color: #666;
            border-top: 1px solid #e9ecef;
        }

        .footer a {
            color: #007bff;
            text-decoration: none;
        }

        @media (max-width: 768px) {
            .messages {
                padding: 24px 16px;
            }

            .header {
                padding: 16px;
            }

            .user-message .message-content {
                margin-left: 10%;
            }

            .ai-message .message-content {
                margin-right: 10%;
            }
        }

        @media (max-width: 480px) {
            .user-message .message-content,
            .ai-message .message-content {
                margin-left: 0;
                margin-right: 0;
            }
        }

        @media print {
            body {
                background: white;
                margin: 0;
                padding: 0;
            }

            .container {
                box-shadow: none;
                border-radius: 0;
                max-width: 100%;
            }

            .header {
                background: #f8f9fa !important;
                -webkit-print-color-adjust: exact;
            }

            .messages {
                padding: 20px;
            }

            .user-message .message-content {
                background: #e3f2fd !important;
                -webkit-print-color-adjust: exact;
            }

            .reasoning-section {
                background: #f8f9fa !important;
                -webkit-print-color-adjust: exact;
            }
        }
    `;
  }
}

export default ChatExporter;