<template>
  <div class="chat"  ref="chatContainer">
    <div class="chat-header">
      <div class="header__left">
        <div
          v-if="!state.isSidebarOpen"
          class="close nav-btn nav-btn-icon-only"
          @click="state.isSidebarOpen = true"
        >
          <a-tooltip title="展开侧边栏" placement="right">
            <img src="@/assets/icons/sidebar_left.svg" class="iconfont icon-20" alt="设置" />
          </a-tooltip>
        </div>

        <div class="newchat nav-btn nav-btn-icon-only" @click="$emit('newconv')">
          <a-tooltip title="新建对话" placement="right">
            <PlusCircleOutlined />
          </a-tooltip>
        </div>
        <a-dropdown>
          <a class="model-select nav-btn" @click.prevent>
            <BulbOutlined />
            <a-tooltip :title="configStore.config?.model_name" placement="right">
              <span class="model-text text"> {{ configStore.config?.model_name }} </span>
            </a-tooltip>
            <span class="text" style="color: #aaa;">{{ configStore.config?.model_provider }} </span>
          </a>
          <template #overlay>
            <a-menu class="scrollable-menu">
              <a-menu-item-group v-for="(item, key) in modelKeys" :key="key" :title="modelNames[item]?.name">
                <a-menu-item v-for="(model, idx) in modelNames[item]?.models" :key="`${item}-${idx}`" @click="selectModel(item, model)">
                  {{ model }}
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
        v-for="message in conv.messages"
        :message="message"
        :key="message.id"
        :is-processing="isStreaming"
        :show-refs="true"
        @retry="retryMessage(message.id)"
        @retryStoppedMessage="retryStoppedMessage(message.id)"
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
  PauseOutlined,
  ReloadOutlined,
  CopyOutlined
} from '@ant-design/icons-vue'
import { onClickOutside } from '@vueuse/core'
import { useConfigStore } from '@/stores/config'
import { message } from 'ant-design-vue'
import MessageInputComponent from '@/components/MessageInputComponent.vue'
import MessageComponent from '@/components/MessageComponent.vue'

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
  summary_title: false,
  history_round: 20,
  db_id: null,
  fontSize: 'default',
  wideScreen: false,
})


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
        msg.content += info.content;
      }

      // 批量处理其他属性，只有当属性值不为null/undefined且不为空字符串时才更新
      const propertiesToUpdate = [
        'reasoning_content', 'model_name', 'status', 'message', 'showThinking', 'refs', 'meta'
      ];

      propertiesToUpdate.forEach(prop => {
        if (info[prop] != null && (typeof info[prop] !== 'string' || info[prop] !== '')) {
          msg[prop] = info[prop];
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

const simpleCall = (msg) => {
  return new Promise((resolve, reject) => {
    fetch('/api/chat/call', {
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

  const params = {
    query: user_input,
    history: getHistory().slice(0, -1), // 去掉最后一条刚添加的用户消息,
    meta: meta,
    cur_res_id: cur_res_id,
  }
  console.log(params)

  fetch('/api/chat/', {
    method: 'POST',
    body: JSON.stringify(params),
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
                content: data.response,
                reasoning_content: data.reasoning_content,
                status: data.status,
                meta: data.meta,
                ...data,
              });
              // console.log("Last message", conv.value.messages[conv.value.messages.length - 1].content)
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
  // message.success(`已切换到模型: ${name} | ${provider}`)
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
  background: var(--main-light-7);
  position: relative;
  box-sizing: border-box;
  flex: 5 5 200px;
  overflow-y: scroll;

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

  .model-select {
    // color: var(--gray-900);
    max-width: 350px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;

    .model-text {
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
// 添加全局样式以确保滚动功能在dropdown内正常工作
.ant-dropdown-menu {
  &.scrollable-menu {
    max-height: 300px;
    overflow-y: auto;
  }
}
</style>


