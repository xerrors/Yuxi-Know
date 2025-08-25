/**
 * 消息处理工具类
 */
export class MessageProcessor {
  /**
   * 将工具结果与消息合并
   * @param {Array} msgs - 消息数组
   * @returns {Array} 合并后的消息数组
   */
  static convertToolResultToMessages(msgs) {
    const toolResponseMap = new Map();
    
    // 构建工具响应映射
    for (const item of msgs) {
      if (item.type === 'tool' && item.tool_call_id) {
        toolResponseMap.set(item.tool_call_id, item);
      }
    }

    // 合并工具调用和响应
    const convertedMsgs = msgs.map(item => {
      if (item.type === 'ai' && item.tool_calls && item.tool_calls.length > 0) {
        return {
          ...item,
          tool_calls: item.tool_calls.map(toolCall => {
            const toolResponse = toolResponseMap.get(toolCall.id);
            return {
              ...toolCall,
              tool_call_result: toolResponse || null
            };
          })
        };
      }
      return item;
    });

    return convertedMsgs;
  }

  /**
   * 将服务器历史记录转换为对话格式
   * @param {Array} serverHistory - 服务器历史记录
   * @returns {Array} 对话数组
   */
  static convertServerHistoryToMessages(serverHistory) {
    // 第一步：将所有tool消息与对应的tool call合并
    const mergedHistory = this.convertToolResultToMessages(serverHistory);

    // 第二步：按照对话分组
    const conversations = [];
    let currentConv = null;

    for (const item of mergedHistory) {
      if (item.type === 'human') {
        currentConv = {
          messages: [item],
          status: 'loading'
        };
        conversations.push(currentConv);
      } else if (item.type === 'ai' && currentConv) {
        currentConv.messages.push(item);

        if (item.response_metadata?.finish_reason === 'stop') {
          item.isLast = true;
          currentConv.status = 'finished';
          currentConv = null;
        }
      }
    }

    return conversations;
  }

  /**
   * 合并消息块
   * @param {Array} chunks - 消息块数组
   * @returns {Object|null} 合并后的消息
   */
  static mergeMessageChunk(chunks) {
    if (chunks.length === 0) return null;

    // 深拷贝第一个chunk作为结果
    const result = JSON.parse(JSON.stringify(chunks[0]));
    result.content = result.content || '';

    // 合并后续chunks
    for (let i = 1; i < chunks.length; i++) {
      const chunk = chunks[i];
      
      // 合并内容
      if (chunk.content) {
        result.content += chunk.content;
      }

      // 合并reasoning_content
      if (chunk.reasoning_content) {
        if (!result.reasoning_content) {
          result.reasoning_content = '';
        }
        result.reasoning_content += chunk.reasoning_content;
      }

      // 合并additional_kwargs中的reasoning_content
      if (chunk.additional_kwargs?.reasoning_content) {
        if (!result.additional_kwargs) result.additional_kwargs = {};
        if (!result.additional_kwargs.reasoning_content) {
          result.additional_kwargs.reasoning_content = '';
        }
        result.additional_kwargs.reasoning_content += chunk.additional_kwargs.reasoning_content;
      }

      // 合并tool_calls
      MessageProcessor._mergeToolCalls(result, chunk);
    }

    // 处理AIMessageChunk类型
    if (result.type === 'AIMessageChunk') {
      result.type = 'ai';
      if (result.additional_kwargs?.tool_calls) {
        result.tool_calls = result.additional_kwargs.tool_calls;
      }
    }

    return result;
  }

  /**
   * 合并工具调用
   * @private
   * @param {Object} result - 结果对象
   * @param {Object} chunk - 当前块
   */
  static _mergeToolCalls(result, chunk) {
    if (chunk.additional_kwargs?.tool_calls) {
      if (!result.additional_kwargs) result.additional_kwargs = {};
      if (!result.additional_kwargs.tool_calls) result.additional_kwargs.tool_calls = [];

      for (const toolCall of chunk.additional_kwargs.tool_calls) {
        const existingToolCall = result.additional_kwargs.tool_calls.find(
          t => (t.id === toolCall.id || t.index === toolCall.index)
        );

        if (existingToolCall) {
          // 合并相同ID的tool call
          if (existingToolCall.function && toolCall.function) {
            existingToolCall.function.arguments += toolCall.function.arguments;
          }
        } else {
          // 添加新的tool call
          result.additional_kwargs.tool_calls.push(JSON.parse(JSON.stringify(toolCall)));
        }
      }
    }
  }

  /**
   * 处理流式响应数据块
   * @param {Object} data - 响应数据
   * @param {Object} onGoingConv - 进行中的对话对象
   * @param {Object} state - 状态对象
   * @param {Function} getAgentHistory - 获取历史记录函数
   * @param {Function} handleError - 错误处理函数
   */
  static async processResponseChunk(data, onGoingConv, state, getAgentHistory, handleError) {
    try {
      switch (data.status) {
        case 'init':
          // 代表服务端收到请求并返回第一个响应
          state.waitingServerResponse = false;
          onGoingConv.msgChunks[data.request_id] = [data.msg];
          break;

        case 'loading':
          if (data.msg.id) {
            if (!onGoingConv.msgChunks[data.msg.id]) {
              onGoingConv.msgChunks[data.msg.id] = [];
            }
            onGoingConv.msgChunks[data.msg.id].push(data.msg);
          }
          break;

        case 'error':
          console.error("流式处理出错:", data.message);
          handleError(new Error(data.message), 'stream');
          break;

        case 'finished':
          await getAgentHistory();
          break;

        default:
          console.warn('未知的响应状态:', data.status);
      }
    } catch (error) {
      handleError(error, 'stream');
    }
  }

  /**
   * 处理流式响应
   * @param {Response} response - 响应对象
   * @param {Function} processChunk - 处理块的函数
   * @param {Function} scrollToBottom - 滚动到底部函数
   * @param {Function} handleError - 错误处理函数
   */
  static async handleStreamResponse(response, processChunk, scrollToBottom, handleError) {
    try {
      const reader = response.body.getReader();
      let buffer = '';
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // 保留最后一行可能不完整的内容

        for (const line of lines) {
          if (line.trim()) {
            try {
              const data = JSON.parse(line.trim());
              await processChunk(data);
            } catch (e) {
              console.debug('解析JSON出错:', e.message);
            }
          }
        }
        await scrollToBottom();
      }

      // 处理缓冲区中可能剩余的内容
      if (buffer.trim()) {
        try {
          const data = JSON.parse(buffer.trim());
          await processChunk(data);
        } catch (e) {
          console.warn('最终缓冲区内容无法解析:', buffer);
        }
      }
    } catch (error) {
      handleError(error, 'stream');
    }
  }
}

export default MessageProcessor;