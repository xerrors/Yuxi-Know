<template>
  <div class="chat"  ref="chatContainer">
    <div class="chat-header">
      <div class="header__left">
        <div
          v-if="!state.isSidebarOpen"
          class="close nav-btn"
          @click="state.isSidebarOpen = true"
        >
          <MenuOutlined />
        </div>

        <div class="newchat nav-btn" @click="$emit('newconv')">
          <PlusCircleOutlined /> <span class="text">新对话</span>
        </div>
        <a-dropdown>
          <a class="model-select nav-btn" @click.prevent>
            <BulbOutlined /> <span class="text">{{ configStore.config?.model_provider }}/{{ configStore.config?.model_name }}</span>
          </a>
          <template #overlay>
            <a-menu class="scrollable-menu">
              <a-menu-item-group v-for="(item, key) in modelKeys" :key="key" :title="modelNames[item]?.name">
                <a-menu-item v-for="(model, idx) in modelNames[item]?.models" :key="`${item}-${idx}`" @click="selectModel(item, model)">
                  {{ item }}/{{ model }}
                </a-menu-item>
              </a-menu-item-group>
              <a-menu-item-group v-if="customModels.length > 0" title="自定义模型">
                <a-menu-item v-for="(model, idx) in customModels" :key="`custom-${idx}`" @click="selectModel('custom', model.custom_id)">
                  custom/{{ model.custom_id }}
                </a-menu-item>
              </a-menu-item-group>
            </a-menu>
          </template>
        </a-dropdown>
      </div>
      <div class="header__right">
        <div class="nav-btn text" @click="opts.showPanel = !opts.showPanel">
          <component :is="opts.showPanel ? FolderOpenOutlined : FolderOutlined" /> <span class="text">选项</span>
        </div>
        <div v-if="opts.showPanel" class="my-panal r0 top100 swing-in-top-fwd" ref="panel">
          <div class="flex-center" @click="meta.stream = !meta.stream">
            流式输出 <div @click.stop><a-switch v-model:checked="meta.stream" /></div>
          </div>
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
      <div
        v-for="message in conv.messages"
        :key="message.id"
        class="message-box"
        :class="message.role"
      >
        <div v-if="message.reasoning_content" class="reasoning-msg">
          <a-collapse
            v-model:activeKey="message.showThinking"
            :bordered="false"
            style="background: rgb(255, 255, 255)"
          >
            <template #expandIcon="{ isActive }">
              <caret-right-outlined :rotate="isActive ? 90 : 0" />
            </template>
            <a-collapse-panel
              key="show"
              :header="message.status=='reasoning' ? '正在思考...' : '推理过程'"
              :style="'background: #f7f7f7; border-radius: 8px; margin-bottom: 24px; border: 0; overflow: hidden'"
            >
              <p style="color: var(--gray-800)">{{ message.reasoning_content }}</p>
            </a-collapse-panel>
          </a-collapse>
        </div>
        <p v-if="message.role=='sent'" style="white-space: pre-line" class="message-text">{{ message.text }}</p>
        <div v-else-if="message.text.length == 0 && (message.status=='init' || message.status=='reasoning') && isStreaming"  class="loading-dots">
          <div></div>
          <div></div>
          <div></div>
        </div>
        <div v-else-if="message.status == 'searching' && isStreaming" class="searching-msg"><i>正在检索……</i></div>
        <div v-else-if="message.status == 'generating' && isStreaming" class="searching-msg"><i>正在生成……</i></div>
        <div v-else-if="message.text.length > 0"
          v-html="renderMarkdown(message)"
          class="message-md"
          @click="consoleMsg(message)">
        </div>
        <div v-else
          class="err-msg"
          @click="retryMessage(message.id)"
        >
          请求错误，请重试。{{ message.message }}
        </div>
        <div v-if="message.isStoppedByUser" class="retry-hint">
          你停止生成了本次回答 
          <span class="retry-link" @click="retryStoppedMessage(message)">重新编辑问题</span>
        </div>
        <RefsComponent v-if="message.role=='received' && message.status=='finished'" :message="message" />
      </div>
    </div>
    <div class="bottom">
      <div class="input-box" :class="{ 'wide-screen': meta.wideScreen }">
        <div class="input-area">
          <a-textarea
            class="user-input"
            v-model:value="conv.inputText"
            @keydown="handleKeyDown"
            placeholder="输入问题……"
            :auto-size="{ minRows: 2, maxRows: 10 }"
          />
        </div>
        <div class="input-options">
          <div class="options__left">
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
          </div>
          <div class="options__right">
            <a-tooltip :title="isStreaming ? '停止回答' : ''">
              <a-button 
                size="large" 
                @click="handleSendOrStop" 
                :disabled="(!conv.inputText && !isStreaming)" 
                type="link"
              >
                <template #icon>
                  <StopOutlined v-if="isStreaming" />
                  <ArrowUpOutlined v-else />
                </template>
              </a-button>
            </a-tooltip>
          </div>
        </div>
      </div>
      <p class="note">请注意辨别内容的可靠性 By {{ configStore.config?.model_provider }}: {{ configStore.config?.model_name }}</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, toRefs, nextTick, onUnmounted, watch, computed } from 'vue'
import {
  SendOutlined,
  MenuOutlined,
  FormOutlined,
  LoadingOutlined,
  BookOutlined,
  BookFilled,
  CompassOutlined,
  ArrowUpOutlined,
  CompassFilled,
  GoldenFilled,
  GoldOutlined,
  SettingOutlined,
  SettingFilled,
  PlusCircleOutlined,
  FolderOutlined,
  FolderOpenOutlined,
  GlobalOutlined,
  FileTextOutlined,
  BulbOutlined,
  CaretRightOutlined,
  DeploymentUnitOutlined,
  StopOutlined
} from '@ant-design/icons-vue'
import { onClickOutside } from '@vueuse/core'
import { Marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import { useConfigStore } from '@/stores/config'
import { message } from 'ant-design-vue'
import RefsComponent from '@/components/RefsComponent.vue'
import hljs from 'highlight.js';
import 'highlight.js/styles/github.css';

const props = defineProps({
  conv: Object,
  state: Object
})

const emit = defineEmits(['rename-title', 'newconv']);
const configStore = useConfigStore()

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
  stream: true,
  summary_title: false,
  history_round: 5,
  db_id: null,
  fontSize: 'default',
  wideScreen: false,
})

const marked = new Marked(
  {
    gfm: true,
    breaks: true,
    tables: true,
  },
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code) {
      return hljs.highlightAuto(code).value;
    }
  })
);

const consoleMsg = (msg) => console.log(msg)
onClickOutside(panel, () => setTimeout(() => opts.showPanel = false, 30))
onClickOutside(modelCard, () => setTimeout(() => opts.showModelCard = false, 30))

const renderMarkdown = (msg) => {
  if (msg.status === 'loading') {
    return marked.parse(msg.text + '🟢')
  } else {
    return marked.parse(msg.text)
  }
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
    const firstUserMessage = conv.value.messages[0].text
    const firstAiMessage = conv.value.messages[1].text
    const context = `${prompt}\n\n问题: ${firstUserMessage}\n\n回复: ${firstAiMessage}，主题是（一句话）：`
    simpleCall(context).then((data) => {
      const response = data.response.split("：")[0].replace(/^["'"']/g, '').replace(/["'"']$/g, '')
      emit('rename-title', response)
    })
  } else {
    emit('rename-title', conv.value.messages[0].text)
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
    text: msg
  })
  scrollToBottom()
}

const appendAiMessage = (text, refs=null) => {
  conv.value.messages.push({
    id: generateRandomHash(16),
    role: 'received',
    text: text,
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
      // 只有在 text 不为空时更新
      if (info.text !== null && info.text !== undefined && info.text !== '') {
        msg.text = info.text;
      }

      if (info.reasoning_content !== null && info.reasoning_content !== undefined && info.reasoning_content !== '') {
        msg.reasoning_content = info.reasoning_content;
      }

      // 只有在 refs 不为空时更新
      if (info.refs !== null && info.refs !== undefined) {
        msg.refs = info.refs;
      }

      if (info.model_name !== null && info.model_name !== undefined && info.model_name !== '') {
        msg.model_name = info.model_name;
      }

      // 只有在 status 不为空时更新
      if (info.status !== null && info.status !== undefined && info.status !== '') {
        msg.status = info.status;
      }

      if (info.meta !== null && info.meta !== undefined) {
        msg.meta = info.meta;
      }

      if (info.message !== null && info.message !== undefined) {
        msg.message = info.message;
      }

      if (info.showThinking !== null && info.showThinking !== undefined) {
        msg.showThinking = info.showThinking;
      }

      scrollToBottom();
    } catch (error) {
      console.error('Error updating message:', error);
      msg.status = 'error';
      msg.text = '消息更新失败';
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

const simpleCall = (msg) => {
  return new Promise((resolve, reject) => {
    fetch('/api/chat/call_lite', {
      method: 'POST',
      body: JSON.stringify({ query: msg, }),
      headers: { 'Content-Type': 'application/json' }
    })
    .then((response) => response.json())
    .then((data) => resolve(data))
    .catch((error) => reject(error))
  })
}

const loadDatabases = () => {
  fetch('/api/data/', { method: "GET", })
    .then(response => response.json())
    .then(data => {
      console.log(data)
      opts.databases = data.databases
    })
}

// 新函数用于处理 fetch 请求
const fetchChatResponse = (user_input, cur_res_id) => {
  const controller = new AbortController();
  const signal = controller.signal;

  fetch('/api/chat/', {
    method: 'POST',
    body: JSON.stringify({
      query: user_input,
      history: conv.value.history,
      meta: meta,
      cur_res_id: cur_res_id,
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    signal // 添加 signal 用于中断请求
  })
  .then((response) => {
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
                text: data.response,
                reasoning_content: data.reasoning_content,
                status: data.status,
                meta: data.meta,
                ...data,
              });
              // console.log("Last message", conv.value.messages[conv.value.messages.length - 1].text)
              // console.log("Last message", conv.value.messages[conv.value.messages.length - 1].status)

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
      console.error(error);
      updateMessage({
        id: cur_res_id,
        status: "error",
      });
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
  conv.value.inputText = pastMessage.text
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

  // 从本地存储加载数据
  const storedMeta = localStorage.getItem('meta');
  if (storedMeta) {
    const parsedMeta = JSON.parse(storedMeta);
    Object.assign(meta, parsedMeta);
  }
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
const retryStoppedMessage = (message) => {
  // 找到用户的原始问题
  const messageIndex = conv.value.messages.findIndex(msg => msg.id === message.id);
  if (messageIndex > 0) {
    const userMessage = conv.value.messages[messageIndex - 1];
    if (userMessage && userMessage.role === 'sent') {
      conv.value.inputText = userMessage.text;
      // 删除被停止的消息
      conv.value.messages = conv.value.messages.slice(0, messageIndex);
    }
  }

const modelNames = computed(() => configStore.config?.model_names)
const modelStatus = computed(() => configStore.config?.model_provider_status)
const customModels = computed(() => configStore.config?.custom_models || [])

// 筛选 modelStatus 中为真的key
const modelKeys = computed(() => {
  return Object.keys(modelStatus.value || {}).filter(key => modelStatus.value?.[key])
})

// 选择模型的方法
const selectModel = (provider, name) => {
  configStore.setConfigValue('model_provider', provider)
  configStore.setConfigValue('model_name', name)
  message.success(`已切换到模型: ${provider}/${name}`)

}
</script>

<style lang="less" scoped>
.chat {
  position: relative;
  width: 100%;
  max-height: 100vh;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  background: white;
  position: relative;
  box-sizing: border-box;
  flex: 5 5 200px;
  overflow-y: scroll;

  .chat-header {
    user-select: none;
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: white;
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
    padding: 0.5rem 0.75rem;

    .text {
      margin-left: 10px;
    }

    &:hover {
      background-color: var(--main-light-3);
    }
  }

  .model-select {
    // color: var(--gray-900);
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    .text {
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }
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

  .message-box {
    display: inline-block;
    border-radius: 1.5rem;
    margin: 0.8rem 0;
    padding: 0.625rem 1.25rem;
    user-select: text;
    word-break: break-word;
    font-size: 15px;
    font-variation-settings: 'wght' 400, 'opsz' 10.5;
    font-weight: 400;
    box-sizing: border-box;
    color: black;
    /* box-shadow: 0px 0.3px 0.9px rgba(0, 0, 0, 0.12), 0px 1.6px 3.6px rgba(0, 0, 0, 0.16); */
    /* animation: slideInUp 0.1s ease-in; */

    .err-msg {
      color: #eb8080;
      border: 1px solid #eb8080;
      padding: 0.5rem 1rem;
      border-radius: 8px;
      text-align: left;
      background: #FFF5F5;
      margin-bottom: 10px;
      cursor: pointer;
    }

    .searching-msg {
      color: var(--gray-500);
      animation: colorPulse 2s infinite;
    }

    @keyframes colorPulse {
      0% { color: var(--gray-700); }
      50% { color: var(--gray-300); }
      100% { color: var(--gray-700); }
    }
  }

  .message-box.sent {
    line-height: 24px;
    max-width: 95%;
    background: var(--main-light-4);
    align-self: flex-end;
  }

  .message-box.received {
    color: initial;
    width: fit-content;
    text-align: left;
    word-wrap: break-word;
    margin: 0;
    max-width: 100%;
    padding-bottom: 0;
    padding-top: 16px;
    padding-left: 0;
    padding-right: 0;
    text-align: justify;
  }

  p.message-text {
    max-width: 100%;
    word-wrap: break-word;
    margin-bottom: 0;
  }

  p.message-md {
    word-wrap: break-word;
    margin-bottom: 0;
  }
}

.bottom {
  position: sticky;
  bottom: 0;
  width: 100%;
  margin: 0 auto;
  padding: 4px 2rem 0 2rem;
  background: white;

  .input-box {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: auto;
    max-width: 800px;
    margin: 0 auto;
    padding: 0.25rem 0.5rem;
    border: 2px solid var(--gray-200);
    border-radius: 1rem;
    background: var(--gray-50);
    transition: background, border 0.3s, box-shadow 0.3s, max-width 0.3s ease;

    &.wide-screen {
      max-width: 1200px;
    }

    &:focus-within {
      border: 2px solid var(--main-500);
      background: white;
    }

    .input-options {
      display: flex;
      padding: 4px 8px;

      .options__left,
      .options__right {
        display: flex;
        align-items: center;
        gap: 8px;
      }

      .options__left {
        flex: 1;

        .opt-item {
          border-radius: 12px;
          border: 1px solid var(--gray-300);
          padding: 4px 8px;
          cursor: pointer;
          font-size: 12px;
          color: var(--gray-700);

          &.active {
            color: var(--main-600);
            border: 1px solid var(--main-500);
            background-color: var(--main-10);
          }
        }
      }
    }

    .input-area {
      display: flex;
      align-items: flex-end;
      gap: 8px;
    }

    textarea.user-input {
      flex: 1;
      height: 40px;
      padding: 0.5rem 0.5rem;
      background-color: transparent;
      border: none;
      margin: 0 0;
      color: #111111;
      font-size: 16px;
      font-variation-settings: 'wght' 400, 'opsz' 10.5;
      outline: none;
      resize: none;
      &:focus {
        outline: none;
        box-shadow: none;
      }

      &:active {
        outline: none;
      }
    }
  }

  button.ant-btn-icon-only {
    height: 32px;
    width: 32px;
    cursor: pointer;
    background-color: var(--main-color);
    border-radius: 50%;
    border: none;
    transition: color 0.3s;
    box-shadow: none;
    color: white;
    padding: 0;

    &:hover {
      background-color: var(--main-800);
    }

    &:disabled {
      background-color: var(--gray-400);
      cursor: not-allowed;
    }
  }
  .note {
    width: 100%;
    font-size: small;
    text-align: center;
    padding: 0rem;
    color: #ccc;
    margin: 4px 0;
    user-select: none;
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
.swing-in-top-fwd{-webkit-animation:swing-in-top-fwd .2s ease-out both;animation:swing-in-top-fwd .2s ease-out both}
@-webkit-keyframes swing-in-top-fwd{0%{-webkit-transform:rotateX(-100deg);transform:rotateX(-100deg);-webkit-transform-origin:top;transform-origin:top;opacity:0}100%{-webkit-transform:rotateX(0deg);transform:rotateX(0deg);-webkit-transform-origin:top;transform-origin:top;opacity:1}}@keyframes swing-in-top-fwd{0%{-webkit-transform:rotateX(-100deg);transform:rotateX(-100deg);-webkit-transform-origin:top;transform-origin:top;opacity:0}100%{-webkit-transform:rotateX(0deg);transform:rotateX(0deg);-webkit-transform-origin:top;transform-origin:top;opacity:1}}
@-webkit-keyframes slide-out-left{0%{-webkit-transform:translateX(0);transform:translateX(0);opacity:1}100%{-webkit-transform:translateX(-1000px);transform:translateX(-1000px);opacity:0}}@keyframes slide-out-left{0%{-webkit-transform:translateX(0);transform:translateX(0);opacity:1}100%{-webkit-transform:translateX(-1000px);transform:translateX(-1000px);opacity:0}}

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

.retry-hint {
  margin-top: 8px;
  padding: 8px 16px;
  color: #666;
  font-size: 14px;
  text-align: left;
}

.retry-link {
  color: #1890ff;
  cursor: pointer;
  margin-left: 4px;

  &:hover {
    text-decoration: underline;
  }
}

.ant-btn-icon-only {
  &:has(.anticon-stop) {
    background-color: #ff4d4f !important;

    &:hover {
      background-color: #ff7875 !important;
    }
.scrollable-menu {
  max-height: 300px;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--gray-400);
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb:hover {
    background: var(--gray-500);
  }
}
</style>

<style lang="less">
.message-md {
  color: var(--gray-900);
  max-width: 100%;

  pre {
    border-radius: 8px;
    font-size: 0.9rem;
    border: 1px solid var(--main-light-3);
    padding: 1rem;

    &:has(code.hljs) {
      padding: 0;
    }

    code.hljs {
      font-size: 0.8rem;
      background-color: var(--gray-100);
    }
  }

  strong {
    color: var(--gray-800);
  }

  h1, h2, h3, h4, h5, h6 {
    font-size: 1rem;
  }

  li, ol, ul {
    & > p {
      margin: 0.25rem 0;
    }
  }

  ol, ul {
    padding-left: 1rem;
  }

  hr {
    margin-bottom: 1rem;
  }

  a {
    color: var(--main-800);
    margin: auto 2px;
  }
}
</style>

<style lang="less">
// 添加全局样式以确保滚动功能在dropdown内正常工作
.ant-dropdown-menu {
  &.scrollable-menu {
    max-height: 300px;
    overflow-y: auto;
  }
}
</style>


