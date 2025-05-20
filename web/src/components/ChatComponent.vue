<template>
  <div class="chat"  ref="chatContainer" :class="{ 'refs-sidebar-open': refsSidebarVisible && refsSidebarPinned }">
    <div class="chat-header">
      <div class="header__left">
        <div
          v-if="!state.isSidebarOpen"
          class="close nav-btn nav-btn-icon-only"
          @click="state.isSidebarOpen = true"
        >
          <a-tooltip title="展开侧边栏" placement="right">
            <PanelLeftOpen size="20" color="var(--gray-800)"/>
          </a-tooltip>
        </div>

        <div class="newchat nav-btn nav-btn-icon-only" @click="$emit('newconv')">
          <a-tooltip title="新建对话" placement="right">
            <MessageSquarePlus size="20" color="var(--gray-800)"/>
          </a-tooltip>
        </div>
        <ModelSelectorComponent
          class="nav-btn borderless max-width"
          @select-model="handleModelSelect"
          :model_name="configStore.config?.model_name"
          :model_provider="configStore.config?.model_provider"
        />
      </div>
      <div class="header__right">
        <div class="nav-btn text" @click="opts.showPanel = !opts.showPanel">
          <Ellipsis />
          <!-- <span class="text">选项</span> -->
        </div>
        <div v-if="opts.showPanel" class="my-panal r0 top100 swing-in-top-fwd" ref="panel">
          <div class="flex-center" @click="meta.summary_title = !meta.summary_title">
            总结对话标题 <div @click.stop><a-switch v-model:checked="meta.summary_title" /></div>
          </div>
          <div class="flex-center">
            最大历史轮数 <a-input-number id="inputNumber" v-model:value="meta.history_round" :min="1" :max="50" />
          </div>
          <div class="flex-center">
            字体大小
            <a-select v-model:value="meta.fontSize" style="width: 100px" placeholder="选择字体大小">
              <a-select-option value="smaller">更小</a-select-option>
              <a-select-option value="default">默认</a-select-option>
              <a-select-option value="larger">更大</a-select-option>
            </a-select>
          </div>
          <div class="flex-center" @click="meta.wideScreen = !meta.wideScreen">
            宽屏模式 <div @click.stop><a-switch v-model:checked="meta.wideScreen" /></div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="conv.messages.length == 0" class="chat-examples">
      <h1>你好，我是语析，一个基于知识图谱的智能助手</h1>
      <div class="opts">
        <div
          class="opt__button"
          v-for="(exp, key) in examples"
          :key="key"
          @click="conv.inputText = exp"
        >
          {{ exp }}
        </div>
      </div>
    </div>
    <div class="chat-box" :class="{ 'wide-screen': meta.wideScreen, 'font-smaller': meta.fontSize === 'smaller', 'font-larger': meta.fontSize === 'larger' }">
      <MessageComponent
        v-for="(message, index) in conv.messages"
        :message="message"
        :key="message.id"
        :is-processing="isStreaming"
        :show-refs="['copy', 'regenerate', 'subGraph', 'webSearch', 'knowledgeBase']"
        :is-latest-message="isLatestMessage(index)"
        @retry="retryMessage(message.id)"
        @retryStoppedMessage="retryStoppedMessage(message.id)"
        @openRefs="handleOpenRefs"
      >
      </MessageComponent>
    </div>
    <div class="bottom">
      <div class="message-input-wrapper"  :class="{ 'wide-screen': meta.wideScreen}">
        <MessageInputComponent
          v-model="conv.inputText"
          :is-loading="isStreaming"
          :send-button-disabled="!conv.inputText && !isStreaming"
          :auto-size="{ minRows: 2, maxRows: 10 }"
          @send="handleSendOrStop"
          @keydown="handleKeyDown"
        >
          <template #options-left>
            <div
              :class="{'switch': true, 'opt-item': true, 'active': meta.use_web}"
              v-if="configStore.config.enable_web_search"
              @click="meta.use_web=!meta.use_web"
            >
              <CompassOutlined style="margin-right: 3px;"/>
              联网搜索
            </div>
            <div
              :class="{'switch': true, 'opt-item': true, 'active': meta.use_graph}"
              v-if="configStore.config.enable_knowledge_graph"
              @click="meta.use_graph=!meta.use_graph"
            >
              <DeploymentUnitOutlined style="margin-right: 3px;"/>
              知识图谱
            </div>
            <a-dropdown
              v-if="configStore.config.enable_knowledge_base && opts.databases.length > 0"
              :class="{'opt-item': true, 'active': meta.selectedKB !== null}"
            >
              <a class="ant-dropdown-link" @click.prevent>
                <BookOutlined style="margin-right: 3px;"/>
                <span class="text">{{ meta.selectedKB === null ? '不使用知识库' : opts.databases[meta.selectedKB]?.name }}</span>
              </a>
              <template #overlay>
                <a-menu>
                  <a-menu-item v-for="(db, index) in opts.databases" :key="index" @click="useDatabase(index)">
                    <a href="javascript:;">{{ db.name }}</a>
                  </a-menu-item>
                  <a-menu-item @click="useDatabase(null)">
                    <a href="javascript:;">不使用</a>
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </template>
        </MessageInputComponent>
        <p class="note">请注意辨别内容的可靠性 By {{ configStore.config?.model_provider }}: {{ configStore.config?.model_name }}</p>
      </div>
    </div>
    <!-- 添加全局Refs侧边栏 -->
    <RefsSidebar
      ref="refsSidebarRef"
      :visible="refsSidebarVisible"
      :latestRefs="currentRefs"
      @update:visible="refsSidebarVisible = $event"
      @pin-change="handleRefsPinChange"
    />
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, toRefs, nextTick, onUnmounted, watch, computed } from 'vue'
import {
  BookOutlined,
  CompassOutlined,
  PlusCircleOutlined,
  DeploymentUnitOutlined,
} from '@ant-design/icons-vue'
import { Ellipsis, PanelLeftOpen, MessageSquarePlus } from 'lucide-vue-next'
import { onClickOutside } from '@vueuse/core'
import { useConfigStore } from '@/stores/config'
import { useUserStore } from '@/stores/user'
import { message } from 'ant-design-vue'
import MessageInputComponent from '@/components/MessageInputComponent.vue'
import MessageComponent from '@/components/MessageComponent.vue'
import RefsSidebar from '@/components/RefsSidebar.vue'
import ModelSelectorComponent from '@/components/ModelSelectorComponent.vue'
import { chatApi } from '@/apis/auth_api'
import { knowledgeBaseApi } from '@/apis/admin_api'

const props = defineProps({
  conv: Object,
  state: Object
})

const emit = defineEmits(['rename-title', 'newconv']);
const configStore = useConfigStore()
const userStore = useUserStore()

const { conv, state } = toRefs(props)
const chatContainer = ref(null)

const isStreaming = ref(false)
const userIsScrolling = ref(false);
const shouldAutoScroll = ref(true);

const panel = ref(null)
const modelCard = ref(null)
const examples = ref([
  '写一个简单的冒泡排序',
  '今天无锡天气怎么样？',
  '介绍一下红楼梦',
  '今天星期几？'
])

const opts = reactive({
  showPanel: false,
  showModelCard: false,
  openDetail: false,
  databases: [],
})

const meta = reactive(JSON.parse(localStorage.getItem('meta')) || {
  use_graph: false,
  use_web: false,
  graph_name: "neo4j",
  selectedKB: null,
  summary_title: false,
  history_round: 20,
  db_id: null,
  fontSize: 'default',
  wideScreen: false,
})

// 添加全局refs状态
const refsSidebarVisible = ref(false)
const currentRefs = ref({})

// 添加侧边栏固定状态
const refsSidebarPinned = ref(false)

// 处理侧边栏固定状态变化
const handleRefsPinChange = (pinned) => {
  refsSidebarPinned.value = pinned
}

// 处理打开refs侧边栏
const handleOpenRefs = ({ type, refs }) => {
  console.log('ChatComponent handleOpenRefs called with type:', type);
  console.log('Refs data structure:', JSON.stringify(refs));

  // 先更新引用数据，确保数据在设置标签页之前已更新
  currentRefs.value = Object.assign({}, refs);

  // 强制在下一个tick更新，确保数据已经被正确应用
  nextTick(() => {
    // 显示抽屉
    refsSidebarVisible.value = true;

    // 再次检查引用是否正确
    console.log('Updated refs data:', JSON.stringify(currentRefs.value));

    // 根据type自动选择标签页
    if (refsSidebarRef.value) {
      console.log('Setting active tab to:', type);
      // 延迟50毫秒设置标签页，确保抽屉已打开
      setTimeout(() => {
        refsSidebarRef.value.setActiveTab(type);
      }, 50);
    } else {
      console.error('refsSidebarRef is not available');
    }
  });
}

// 添加对RefsSidebar的ref
const refsSidebarRef = ref(null)

const consoleMsg = (msg) => console.log(msg)
onClickOutside(panel, () => setTimeout(() => opts.showPanel = false, 30))
onClickOutside(modelCard, () => setTimeout(() => opts.showModelCard = false, 30))

// 从 message 中获取 history 信息，每个消息都是 {role, content} 的格式
const getHistory = () => {
  const history = conv.value.messages.map((msg) => {
    if (msg.content) {
      return {
        role: msg.role === 'sent' ? 'user' : 'assistant',
        content: msg.content
      }
    }
  }).reduce((acc, cur) => {
    if (cur) {
      acc.push(cur)
    }
    return acc
  }, [])
  return history.slice(-meta.history_round)
}

const useDatabase = (index) => {
  const selected = opts.databases[index]
  console.log(selected)
  if (index != null && configStore.config.embed_model != selected.embed_model) {
    console.log(selected.embed_model, configStore.config.embed_model)
    message.error(`所选知识库的向量模型（${selected.embed_model}）与当前向量模型（${configStore.config.embed_model}) 不匹配，请重新选择`)
  } else {
    meta.selectedKB = index
  }
}

const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  } else if (e.key === 'Enter' && e.shiftKey) {
    // Insert a newline character at the current cursor position
    const textarea = e.target;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    conv.value.inputText.value =
      conv.value.inputText.value.substring(0, start) +
      '\n' +
      conv.value.inputText.value.substring(end);
    nextTick(() => {
      textarea.setSelectionRange(start + 1, start + 1);
    });
  }
}

const renameTitle = () => {
  if (meta.summary_title) {
    const prompt = '请用一个很短的句子关于下面的对话内容的主题起一个名字，不要带标点符号：'
    const firstUserMessage = conv.value.messages[0].content
    const firstAiMessage = conv.value.messages[1].content
    const context = `${prompt}\n\n问题: ${firstUserMessage}\n\n回复: ${firstAiMessage}，主题是（一句话）：`
    simpleCall(context).then((data) => {
      const response = data.response.split("：")[0].replace(/^["'"']/g, '').replace(/["'"']$/g, '')
      emit('rename-title', response)
    })
  } else {
    emit('rename-title', conv.value.messages[0].content)
  }
}

const handleUserScroll = () => {
  // 计算我们是否接近底部（100像素以内）
  const isNearBottom = chatContainer.value.scrollHeight - chatContainer.value.scrollTop - chatContainer.value.clientHeight < 20;

  // 如果用户不在底部，则仅将其标记为用户滚动
  userIsScrolling.value = !isNearBottom;

  // 如果用户再次滚动到底部，请恢复自动滚动
  shouldAutoScroll.value = isNearBottom;
};

const scrollToBottom = () => {
  if (shouldAutoScroll.value) {
    setTimeout(() => {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight - chatContainer.value.clientHeight;
    }, 10);
  }
}

const generateRandomHash = (length) => {
    let chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let hash = '';
    for (let i = 0; i < length; i++) {
        hash += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return hash;
}

const appendUserMessage = (msg) => {
  conv.value.messages.push({
    id: generateRandomHash(16),
    role: 'sent',
    content: msg
  })
  scrollToBottom()
}

const appendAiMessage = (content, refs=null) => {
  conv.value.messages.push({
    id: generateRandomHash(16),
    role: 'received',
    content: content,
    reasoning_content: '',
    refs,
    status: "init",
    meta: {},
    showThinking: "show"
  })
  scrollToBottom()
}

const updateMessage = (info) => {
  const msg = conv.value.messages.find((msg) => msg.id === info.id);
  if (msg) {
    try {
      // 特殊处理：content需要追加而不是替换
      if (info.content != null && info.content !== '') {
        // 检查新内容中是否有<think>标签
        if (info.content.includes('<think>') && !msg.isCollectingThinking) {
          // 开始收集思考内容
          msg.isCollectingThinking = true;

          // 分割内容，获取标签前后的部分
          const parts = info.content.split('<think>');
          msg.content += parts[0]; // 添加标签前的内容到正文

          // 如果有标签后的内容，添加到思考内容
          if (parts.length > 1) {
            if (parts[1].includes('</think>')) {
              const thinkParts = parts[1].split('</think>');
              msg.reasoning_content = (msg.reasoning_content || '') + thinkParts[0];
              msg.content += thinkParts[1]; // 添加结束标签后的内容到正文
              msg.isCollectingThinking = false;
            } else {
              msg.reasoning_content = (msg.reasoning_content || '') + parts[1];
            }
          }
        }
        // 检查是否正在收集思考内容
        else if (msg.isCollectingThinking) {
          if (info.content.includes('</think>')) {
            const parts = info.content.split('</think>');
            msg.reasoning_content = (msg.reasoning_content || '') + parts[0];
            msg.content += parts[1]; // 添加结束标签后的内容到正文
            msg.isCollectingThinking = false;
          } else {
            msg.reasoning_content = (msg.reasoning_content || '') + info.content;
          }
        }
        // 不在收集思考内容，正常追加
        else {
          msg.content += info.content;
        }
      }

      // 批量处理其他属性，只有当属性值不为null/undefined且不为空字符串时才更新
      const propertiesToUpdate = [
        'reasoning_content', 'model_name', 'status', 'message', 'showThinking', 'refs', 'meta'
      ];

      propertiesToUpdate.forEach(prop => {
        if (info[prop] != null && (typeof info[prop] !== 'string' || info[prop] !== '')) {
          msg[prop] = info[prop];

          // 如果更新了refs，同时更新全局refs
          if (prop === 'refs' && info.refs) {
            currentRefs.value = info.refs;
          }
        }
      });

      scrollToBottom();
    } catch (error) {
      console.error('Error updating message:', error);
      msg.status = 'error';
      msg.content = '消息更新失败';
    }
  } else {
    console.error('Message not found:', info.id);
  }
};


const groupRefs = (id) => {
  const msg = conv.value.messages.find((msg) => msg.id === id)
  if (msg.refs && msg.refs.knowledge_base.results.length > 0) {
    msg.groupedResults = msg.refs.knowledge_base.results
    .filter(result => result.file && result.file.filename)
    .reduce((acc, result) => {
      const { filename } = result.file;
      if (!acc[filename]) {
        acc[filename] = []
      }
      acc[filename].push(result)
      return acc;
    }, {})
  }
  scrollToBottom()
}

const loadDatabases = () => {
  // 由于这是管理功能，需要检查用户是否有管理权限
  if (!userStore.isAdmin) {
    console.log('非管理员用户，跳过加载数据库列表');
    return;
  }

  try {
    knowledgeBaseApi.getDatabases()
      .then(data => {
        console.log(data)
        opts.databases = data.databases
      })
      .catch(error => {
        console.error('加载数据库列表失败:', error)
      })
  } catch (error) {
    console.error('获取数据库列表失败:', error);
  }
}

const simpleCall = (msg) => {
  return new Promise((resolve, reject) => {
    chatApi.simpleCall(msg)
      .then(data => resolve(data))
      .catch(error => reject(error))
  })
}

// 替换fetchChatResponse函数
const fetchChatResponse = (user_input, cur_res_id) => {
  const controller = new AbortController();
  const signal = controller.signal;

  const params = {
    query: user_input,
    history: getHistory().slice(0, -1), // 去掉最后一条刚添加的用户消息
    meta: meta,
    cur_res_id: cur_res_id,
  }
  console.log(params)

  // 使用API函数发送请求
  chatApi.sendMessageWithAbort(params, signal)
  .then((response) => {
    if (!response.ok) {
      // 检查是否是401错误（令牌过期）
      if (response.status === 401) {
        const userStore = useUserStore();
        if (userStore.isLoggedIn) {
          message.error('登录已过期，请重新登录');
          userStore.logout();

          // 使用setTimeout确保消息显示后再跳转
          setTimeout(() => {
            window.location.href = '/login';
          }, 1500);
        }
        throw new Error('未授权，请先登录');
      }
      throw new Error(`请求失败: ${response.status} ${response.statusText}`);
    }

    if (!response.body) throw new Error("ReadableStream not supported.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = '';

    const readChunk = () => {
      return reader.read().then(({ done, value }) => {
        if (done) {
          const msg = conv.value.messages.find((msg) => msg.id === cur_res_id)
          console.log(msg)
          groupRefs(cur_res_id);
          updateMessage({showThinking: "no", id: cur_res_id});
          // 更新全局refs为最新消息的refs
          if (msg && msg.refs) {
            // 深拷贝refs以确保不会出现引用问题
            currentRefs.value = JSON.parse(JSON.stringify(msg.refs));
            console.log('Updated currentRefs on response completion:', currentRefs.value);
          }
          isStreaming.value = false;
          if (conv.value.messages.length === 2) { renameTitle(); }
          return;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');

        // 处理除最后一行外的所有完整行
        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (line) {
            try {
              const data = JSON.parse(line);
              updateMessage({
                id: cur_res_id,
                content: data.response,
                reasoning_content: data.reasoning_content,
                status: data.status,
                meta: data.meta,
                ...data,
              });

              if (data.history) {
                conv.value.history = data.history;
              }
            } catch (e) {
              console.error('JSON 解析错误:', e, line);
            }
          }
        }

        // 保留最后一个可能不完整的行
        buffer = lines[lines.length - 1];

        return readChunk(); // 继续读取
      });
    };
    readChunk();
  })
  .catch((error) => {
    if (error.name === 'AbortError') {
      console.log('Fetch aborted');
    } else {
      console.error('聊天请求错误:', error);

      // 检查是否是认证错误
      if (error.message.includes('未授权') || error.message.includes('令牌已过期')) {
        // 已在上面处理，这里不需要重复处理
      } else {
        updateMessage({
          id: cur_res_id,
          status: "error",
          message: error.message || '请求失败',
        });
      }
    }
    isStreaming.value = false;
  });

  // 监听 isStreaming 变化，当为 false 时中断请求
  watch(isStreaming, (newValue) => {
    if (!newValue) {
      controller.abort();
    }
  });
}


// 更新后的 sendMessage 函数
const sendMessage = () => {
  const user_input = conv.value.inputText.trim();
  const dbID = opts.databases.length > 0 ? opts.databases[meta.selectedKB]?.db_id : null;
  if (isStreaming.value) {
    message.error('请等待上一条消息处理完成');
    return
  }
  if (user_input) {
    isStreaming.value = true;
    appendUserMessage(user_input);
    appendAiMessage("", null);
    forceScrollToBottom();

    const cur_res_id = conv.value.messages[conv.value.messages.length - 1].id;
    conv.value.inputText = '';
    meta.db_id = dbID;
    fetchChatResponse(user_input, cur_res_id)
  } else {
    console.log('请输入消息');
  }
}

const retryMessage = (id) => {
  // 找到 id 对应的 message，然后删除包含 message 在内以及后面所有的 message
  const index = conv.value.messages.findIndex(msg => msg.id === id);
  const pastMessage = conv.value.messages[index-1]
  console.log("retryMessage", id, pastMessage)
  conv.value.inputText = pastMessage.content
  if (index !== -1) {
    conv.value.messages = conv.value.messages.slice(0, index-1);
  }
  console.log(conv.value.messages)
  sendMessage();
}

// 从本地存储加载数据
onMounted(() => {
  scrollToBottom()
  loadDatabases()

  chatContainer.value.addEventListener('scroll', handleUserScroll);

  // 检查现有消息中是否有内容为空的情况
  if (conv.value.messages && conv.value.messages.length > 0) {
    conv.value.messages.forEach(msg => {
      if (msg.role === 'received' && (!msg.content || msg.content.trim() === '')) {
        msg.status = 'error';
        msg.message = '内容加载失败';
      }
    });
  }

  console.log(conv.value.messages)

  // 从本地存储加载数据
  const storedMeta = localStorage.getItem('meta');
  if (storedMeta) {
    const parsedMeta = JSON.parse(storedMeta);
    Object.assign(meta, parsedMeta);
  }

  // 检查refsSidebarRef是否正确挂载
  nextTick(() => {
    console.log('Is refsSidebarRef mounted?', !!refsSidebarRef.value);
  });
});

onUnmounted(() => {
  if (chatContainer.value) {
    chatContainer.value.removeEventListener('scroll', handleUserScroll);
  }
});

// 添加新函数来处理特定的滚动行为
const forceScrollToBottom = () => {
  shouldAutoScroll.value = true;
  setTimeout(() => {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight - chatContainer.value.clientHeight;
  }, 10);
};

// 监听 meta 对象的变化，并保存到本地存储
watch(
  () => meta,
  (newMeta) => {
    localStorage.setItem('meta', JSON.stringify(newMeta));
  },
  { deep: true }
);

// 处理发送或停止
const handleSendOrStop = () => {
  if (isStreaming.value) {
    // 停止生成
    isStreaming.value = false;
    const lastMessage = conv.value.messages[conv.value.messages.length - 1];
    if (lastMessage) {
      lastMessage.isStoppedByUser = true;
      lastMessage.status = 'stopped';
    }
  } else {
    // 发送消息
    sendMessage();
  }
}

// 重试被停止的消息
const retryStoppedMessage = (id) => {
  // 找到用户的原始问题
  const messageIndex = conv.value.messages.findIndex(msg => msg.id === id);
  if (messageIndex > 0) {
    const userMessage = conv.value.messages[messageIndex - 1];
    if (userMessage && userMessage.role === 'sent') {
      conv.value.inputText = userMessage.content;
      // 删除被停止的消息，以及所有后面的消息
      conv.value.messages = conv.value.messages.slice(0, messageIndex-1);
      // sendMessage();
    }
  }
}

// 处理模型选择
const handleModelSelect = ({ provider, name }) => {
  configStore.setConfigValues({
    model_provider: provider,
    model_name: name,
  })
}

// 判断是否是最新的助手消息
const isLatestMessage = (index) => {
  // 找到最后一条助手消息的索引
  const lastAssistantMsgIndex = findLastIndex(conv.value.messages,
    msg => (msg.role === 'received' || msg.role === 'assistant') && msg.status === 'finished');

  // 如果当前索引等于最后一条助手消息的索引，则为最新消息
  return index === lastAssistantMsgIndex;
}

// 辅助函数：从后向前查找满足条件的元素索引
const findLastIndex = (array, predicate) => {
  for (let i = array.length - 1; i >= 0; i--) {
    if (predicate(array[i])) {
      return i;
    }
  }
  return -1;
}
</script>

<style lang="less">
.chat {
  --refs-sidebar-floating-width: 700px;
  --refs-sidebar-pinned-width: min(40%, 450px);
}

</style>

<style lang="less" scoped>
.chat {
  position: relative;
  width: 100%;
  max-height: 100vh;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  background: var(--main-light-7);
  position: relative;
  box-sizing: border-box;
  flex: 5 5 200px;
  overflow-y: scroll;
  transition: padding-right 0.3s ease;

  &.refs-sidebar-open {
    padding-right: var(--refs-sidebar-pinned-width); /* 与侧边栏固定时的宽度一致 */
  }

  .chat-header {
    user-select: none;
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: rgba(255, 255, 255, 0.9);
    backdrop-filter: blur(10px);
    height: var(--header-height);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;

    .header__left, .header__right {
      display: flex;
      align-items: center;
    }
  }

  .nav-btn {
    height: 2.5rem;
    display: flex;
    justify-content: center;
    align-items: center;
    border-radius: 8px;
    color: var(--gray-900);
    cursor: pointer;
    // font-size: 1rem;
    width: auto;
    transition: background-color 0.3s;
    padding: 0.5rem 0.75rem;

    .text {
      margin-left: 10px;
    }

    &:hover {
      background-color: var(--main-light-3);
    }
  }

  .nav-btn-icon-only {
    font-size: 1rem;
  }

  // Model selection is now handled by ModelSelectorComponent
}
.metas {
  display: flex;
  gap: 8px;
}

.my-panal {
  position: absolute;
  margin-top: 5px;
  background-color: white;
  border: 1px solid #ccc;
  box-shadow: 0px 0px 10px 1px rgba(0, 0, 0, 0.05);
  border-radius: 12px;
  padding: 12px;
  z-index: 11;
  width: 280px;
  transition: transform 0.3s ease, opacity 0.3s ease;

  .flex-center {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.3s;

    &:hover {
      background-color: var(--main-light-3);
    }

    .anticon {
      margin-right: 8px;
      font-size: 16px;
    }
    .ant-switch {
      &.ant-switch-checked {
        background-color: var(--main-500);
      }
    }
  }
}

.my-panal.r0.top100 {
  top: 100%;
  right: 0;
}

.my-panal.l0.top100 {
  top: 100%;
  left: 0;
}

.chat-examples {
  padding: 0 50px;
  text-align: center;
  position: absolute;
  top: 20%;
  width: 100%;
  z-index: 9;
  animation: slideInUp 0.5s ease-out;

  h1 {
    margin-bottom: 20px;
    font-size: 1.2rem;
    color: #333;
  }

  .opts {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 10px;

    .opt__button {
      background-color: var(--gray-200);
      color: #333;
      padding: .5rem 1.5rem;
      border-radius: 2rem;
      cursor: pointer;
      // border: 2px solid var(--main-light-4);
      transition: background-color 0.3s;
      // box-shadow: 0px 0px 10px 2px var(--main-light-4);


      &:hover {
        background-color: #f0f1f1;
        // box-shadow: 0px 0px 10px 1px rgba(0, 0, 0, 0.1);
      }
    }
  }

}

.chat-box {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  flex-grow: 1;
  padding: 1rem 2rem;
  display: flex;
  flex-direction: column;
  transition: max-width 0.3s ease;

  &.wide-screen {
    max-width: 1200px;
  }

  &.font-smaller {
    font-size: 14px;

    .message-box {
      font-size: 14px;
    }
  }

  &.font-larger {
    font-size: 16px;

    .message-box {
      font-size: 16px;
    }
  }
}

.bottom {
  position: sticky;
  bottom: 0;
  width: 100%;
  margin: 0 auto;
  padding: 4px 2rem 0 2rem;

  .message-input-wrapper {
    width: 100%;
    max-width: 800px;
    margin: 0 auto;
    background-color: white;
    animation: width 0.3s ease-in-out;

    &.wide-screen {
      max-width: 1200px;
    }

    .note {
      width: 100%;
      font-size: small;
      text-align: center;
      padding: 0;
      color: #ccc;
      margin-top: 4px;
      margin-bottom: 0;
      user-select: none;
    }
  }
}

.ant-dropdown-link {
  color: var(--gray-900);
  cursor: pointer;
}



.chat::-webkit-scrollbar {
  position: absolute;
  width: 4px;
}

.chat::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.chat::-webkit-scrollbar-thumb {
  background: var(--gray-400);
  border-radius: 4px;
}

.chat::-webkit-scrollbar-thumb:hover {
  background: rgb(100, 100, 100);
  border-radius: 4px;
}

.chat::-webkit-scrollbar-thumb:active {
  background: rgb(68, 68, 68);
  border-radius: 4px;
}

.loading-dots {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.loading-dots div {
  width: 8px;
  height: 8px;
  margin: 0 4px;
  background-color: #666;
  border-radius: 50%;
  opacity: 0.3;
  animation: pulse 0.5s infinite ease-in-out both;
}

.loading-dots div:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots div:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes pulse {
  0%, 80%, 100% {
    transform: scale(0.8);
    opacity: 0.3;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

@keyframes loading {0%,80%,100%{transform:scale(0.5);}40%{transform:scale(1);}}

.slide-out-left{-webkit-animation:slide-out-left .2s cubic-bezier(.55,.085,.68,.53) both;animation:slide-out-left .5s cubic-bezier(.55,.085,.68,.53) both}
.swing-in-top-fwd {
  -webkit-animation: swing-in-top-fwd 0.3s cubic-bezier(0.175, 0.885, 0.320, 1.275) both;
  animation: swing-in-top-fwd 0.3s cubic-bezier(0.175, 0.885, 0.320, 1.275) both;
}

@keyframes swing-in-top-fwd {
  0% {
    -webkit-transform: rotateX(-100deg);
    transform: rotateX(-100deg);
    -webkit-transform-origin: top;
    transform-origin: top;
    opacity: 0;
  }
  100% {
    -webkit-transform: rotateX(0deg);
    transform: rotateX(0deg);
    -webkit-transform-origin: top;
    transform-origin: top;
    opacity: 1;
  }
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideInUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

@media (max-width: 520px) {
  .chat {
    height: calc(100vh - 60px);
  }

  .chat-container .chat .chat-header {
    background: var(--main-light-4);
    .header__left, .header__right {
      gap: 24px;
    }

    .nav-btn {
      font-size: 1.3rem;
      padding: 0;

      &:hover {
        background-color: transparent;
        color: black;
      }

      .text {
        display: none;
      }
    }
  }

  .bottom {
    padding: 0.5rem 0.5rem;

    .input-box {
      border-radius: 8px;
      padding: 0.5rem;

      textarea.user-input {
        padding: 0.5rem 0;
      }
    }
    .note {
      display: none;
    }
  }
}

.controls {
  display: flex;
  align-items: center;
  gap: 8px;
  .search-switch {
    margin-right: 8px;
  }
}

// Scrollable menu styles moved to ModelSelectorComponent

@media (max-width: 768px) {
  &.refs-sidebar-open {
    padding-right: 280px; /* 中等屏幕上固定时的宽度 */
  }
}

@media (max-width: 480px) {
  &.refs-sidebar-open {
    padding-right: 0; /* 小屏幕上不调整内容区域 */
  }
}
</style>

<!-- Global styles for dropdown moved to ModelSelectorComponent -->


