<!-- ChatComponent.vue -->
<template>
  <div class="chat"  ref="chatContainer">
    <div class="header">
      <div class="header__left">
        <div
          v-if="!state.isSidebarOpen"
          class="close nav-btn"
          @click="state.isSidebarOpen = true"
        >
          <MenuOutlined />
        </div>
        <div
          class="newchat nav-btn"
          @click="$emit('newconv')"
        >
          <PlusCircleOutlined /> <span class="text">新对话</span>
        </div>
      </div>
      <div class="header__right">
        <!-- <div class="nav-btn text metas">
          <CompassFilled v-if="meta.use_web" />
          <GoldenFilled v-if="meta.use_graph"/>
        </div> -->
        <a-dropdown v-if="state.selectedKB !== null">
          <a class="ant-dropdown-link nav-btn" @click.prevent>
            <component :is="state.selectedKB === null ? BookOutlined : BookFilled" />
            <span class="text">{{ state.selectedKB === null ? '不使用' : state.databases[state.selectedKB]?.name }}</span>
          </a>
          <template #overlay>
            <a-menu>
              <a-menu-item v-for="(db, index) in state.databases" :key="index" @click="state.selectedKB=index">
                <a href="javascript:;" >{{ db.name }}</a>
              </a-menu-item>
              <a-menu-item  @click="state.selectedKB = null">
                <a href="javascript:;">不使用</a>
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
        <div class="nav-btn text" @click="state.showPanel = !state.showPanel">
          <component :is="state.showPanel ? FolderOpenOutlined : FolderOutlined" /> <span class="text">选项</span>
        </div>
        <div v-if="state.showPanel" class="my-panal" ref="panel">
          <div class="graphbase flex-center">
            知识库
            <div @click.stop>
              <a-dropdown>
                <a class="ant-dropdown-link " @click.prevent>
                  <component :is="state.selectedKB === null ? BookOutlined : BookFilled" />&nbsp;
                  {{ state.selectedKB === null ? '不使用' : state.databases[state.selectedKB]?.name }}
                </a>
                <template #overlay>
                  <a-menu>
                    <a-menu-item v-for="(db, index) in state.databases" :key="index" @click="state.selectedKB=index">
                      <a href="javascript:;">{{ db.name }}</a>
                    </a-menu-item>
                    <a-menu-item  @click="state.selectedKB = null">
                      <a href="javascript:;">不使用</a>
                    </a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>
          </div>
          <div class="graphbase flex-center" @click="meta.use_graph = !meta.use_graph">
            图数据库 <div @click.stop><a-switch v-model:checked="meta.use_graph" /></div>
          </div>
          <div class="graphbase flex-center" @click="meta.use_web = !meta.use_web">
            搜索引擎（Bing） <div @click.stop><a-switch v-model:checked="meta.use_web" /></div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="conv.messages.length == 0" class="chat-examples">
      <h1>你好，我是 Athena 😊</h1>
      <div class="opt">
        <div
          class="opt__button"
          v-for="(exp, key) in examples"
          :key="key"
          @click="autoSend(exp)"
        >
          {{ exp }}
        </div>
      </div>
    </div>
    <div class="chat-box">
      <div
        v-for="message in conv.messages"
        :key="message.id"
        class="message-box"
        :class="message.role"
      >
        <p v-if="message.role=='sent'" style="white-space: pre-line" class="message-text">{{ message.text }}</p>
        <p v-else
          v-html="renderMarkdown(message.text)"
          class="message-md"
          @click="consoleMsg(message)"></p>

        <div class="refs" v-if="message.role=='received' && message.refs?.knowledge_base.results.length > 0">
          <a-tag
            v-for="(ref, index) in message.refs?.knowledge_base.results"
            :key="index"
            color="blue"
          >
            {{ ref.id }}
          </a-tag>
        </div>
      </div>
    </div>
    <div class="bottom">
      <div class="input-box">
        <a-textarea
          class="user-input"
          v-model:value="conv.inputText"
          @keydown="handleKeyDown"
          placeholder="输入问题……"
          :auto-size="{ minRows: 1, maxRows: 10 }"
        />
        <a-button size="large" @click="sendMessage" :disabled="(!conv.inputText && !isStreaming)">
          <template #icon> <SendOutlined v-if="!isStreaming" /> <LoadingOutlined v-else/> </template>
        </a-button>
      </div>
      <p class="note">即便强如雅典娜也可能会出错，请注意辨别内容的可靠性 模型供应商：{{ configStore.config?.model_provider }}</p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, toRefs, nextTick, computed } from 'vue'
import { onClickOutside } from '@vueuse/core'
import {
  SendOutlined,
  MenuOutlined,
  FormOutlined,
  LoadingOutlined,
  BookOutlined,
  BookFilled,
  CompassFilled,
  GoldenFilled,
  SettingOutlined,
  SettingFilled,
  PlusCircleOutlined,
  FolderOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons-vue'
import { marked } from 'marked';
import { useConfigStore } from '@/stores/config'

const props = defineProps({
  conv: Object,
  state: Object
})

const emit = defineEmits(['renameTitle'])
const configStore = useConfigStore()

const { conv, state } = toRefs(props)
const chatContainer = ref(null)
const isStreaming = ref(false)
const panel = ref(null)
const examples = ref([
  '写一个冒泡排序',
  '肉碱是什么？',
  '洋葱的功效是什么？',
  'A大于B，B小于C，A和C哪个大？',
  '今天天气怎么样？'
])

const meta = reactive({
  db_name: computed(() => state.value.databases[state.value.selectedKB]?.metaname),
  use_graph: false,
  use_web: false,
  graph_name: "neo4j",
})

marked.setOptions({
  gfm: true,
  breaks: true,
  tables: true,
  // 更多选项可以在 marked 文档中找到：https://marked.js.org/
});

onClickOutside(panel, () => setTimeout(() => state.value.showPanel = false, 30))

const handleKeyDown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
    console.log('Enter')
  } else if (e.key === 'Enter' && e.shiftKey) {
    console.log('Shift + Enter')
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
  const prompt = '请用一个很短的句子关于下面的对话内容的主题起一个名字，不要带标点符号：'
  const firstUserMessage = conv.value.messages[0].text
  const firstAiMessage = conv.value.messages[1].text
  const context = `${prompt}\n\n问题: ${firstUserMessage}\n\n回复: ${firstAiMessage}，主题是（一句话）：`
  simpleCall(context).then((data) => {
    emit('renameTitle', data.response.split("：")[0])
  })
}

const myAlert = (message) => alert(message)
const renderMarkdown = (text) => marked(text)

const scrollToBottom = () => {
  setTimeout(() => {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight - chatContainer.value.clientHeight
  }, 10)
}

const consoleMsg = (message) => console.log(message)

const generateRandomHash = (length) => {
    let chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let hash = '';
    for (let i = 0; i < length; i++) {
        hash += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return hash;
}

const appendMessage = (message, role) => {
  conv.value.messages.push({
    id: generateRandomHash(16),
    role,
    text: message
  })
  scrollToBottom()
}

const appendUserMessage = (message) => {
  conv.value.messages.push({
    id: generateRandomHash(16),
    role: 'sent',
    text: message
  })
  scrollToBottom()
}

const appendAiMessage = (message, refs=null) => {
  conv.value.messages.push({
    id: generateRandomHash(16),
    role: 'received',
    text: message,
    refs
  })
  scrollToBottom()
}

const updateMessage = (text, id, refs) => {
  const message = conv.value.messages.find((message) => message.id === id)
  if (message) {
    message.text = text
    message.refs = refs
  } else {
    console.error('Message not found')
  }
  scrollToBottom()
}


const simpleCall = (message) => {
  return new Promise((resolve, reject) => {
    fetch('/api/call', {
      method: 'POST',
      body: JSON.stringify({
        query: message,
      }),
      headers: {
        'Content-Type': 'application/json'
      }
    })
    .then((response) => response.json())
    .then((data) => resolve(data))
    .catch((error) => reject(error))
  })
}

const sendMessage = () => {
  if (conv.value.inputText.trim()) {
    isStreaming.value = true
    appendUserMessage(conv.value.inputText)
    appendAiMessage("检索中……", null)
    const cur_res_id = conv.value.messages[conv.value.messages.length - 1].id
    const user_input = conv.value.inputText
    conv.value.inputText = ''
    fetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        query: user_input,
        history: conv.value.history,
        meta: meta
      }),
      headers: {
        'Content-Type': 'application/json'
      }
    }).then((response) => {const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      // 逐步读取响应文本
      const readChunk = () => {
        return reader.read().then(({ done, value }) => {
          if (done) {
            console.log(conv.value)
            console.log('Finished')
            isStreaming.value = false
            if (conv.value.messages.length === 2) {
              renameTitle()
            }
            return
          }

          buffer += decoder.decode(value, { stream: true })
          const message = buffer.trim().split('\n').pop()

          try {
            const data = JSON.parse(message)
            updateMessage(data.response, cur_res_id, data.refs)
            conv.value.history = data.history
            buffer = ''
          } catch (e) {
            // console.log(e)
          }
          return readChunk()
        })
      }
      return readChunk()
    })
  } else {
    console.log('Please enter a message')
  }
}

const autoSend = (message) => {
  conv.value.inputText = message
  sendMessage()
}

const clearChat = () => {
  conv.value.messages = []
  conv.value.history = []
}

onMounted(() => {
  scrollToBottom()
})
</script>

<style lang="less" scoped>
.chat {
  position: relative;
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  background: white;
  position: relative;
  box-sizing: border-box;
  flex: 5 5 200px;
  overflow-y: scroll;
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none;  /* IE and Edge */

  &::-webkit-scrollbar {
    display: none; /* Chrome, Safari, and Opera */
  }

  .header {
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
    color: var(--c-text-light-1);
    cursor: pointer;
    font-size: 1rem;
    width: auto;
    padding: 0.5rem 1rem;

    .text {
      margin-left: 10px;
    }

    &:hover {
      background-color: var(--main-light-3);
    }
  }

}
.metas {
  display: flex;
  gap: 8px;
}

.my-panal {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 5px;
  background-color: white;
  border: 1px solid #ccc;
  box-shadow: 0px 0px 10px 1px rgba(0, 0, 0, 0.05);
  border-radius: 12px;
  padding: 12px;
  z-index: 101;
  width: 250px;

  .flex-center {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
  }

  .graphbase {
    padding: 8px 16px;
    border-radius: 12px;
    cursor: pointer;
    transition: background-color 0.3s;

    &:hover {
      background-color: var(--main-light-3);
    }
  }
}


.chat-examples {
  padding: 0 50px;
  text-align: center;
  position: absolute;
  top: 20%;
  width: 100%;
  z-index: 100;

  h1 {
    margin-bottom: 20px;
    font-size: 24px;
    color: #333;
  }

  .opt {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 10px;

    .opt__button {
      background-color: white;
      color: #222;
      padding: 6px 1rem;
      border-radius: 1rem;
      cursor: pointer;
      // border: 2px solid var(--main-light-4);
      transition: background-color 0.3s;
      box-shadow: 0px 0px 10px 4px var(--main-light-4);


      &:hover {
        background-color: #fcfcfc;
        box-shadow: 0px 0px 10px 1px rgba(0, 0, 0, 0.1);
      }
    }
  }

}

.chat-box {
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
  flex-grow: 1;
  padding: 1rem;
  display: flex;
  flex-direction: column;

  .message-box {
    max-width: 95%;
    display: inline-block;
    border-radius: 0.8rem;
    margin: 0.8rem 0;
    padding: 1rem;
    user-select: text;
    word-break: break-word;
    font-size: 16px;
    font-variation-settings: 'wght' 400, 'opsz' 10.5;
    font-weight: 400;
    box-sizing: border-box;
    color: #0D0D0D;
    /* box-shadow: 0px 0.3px 0.9px rgba(0, 0, 0, 0.12), 0px 1.6px 3.6px rgba(0, 0, 0, 0.16); */
    /* animation: slideInUp 0.1s ease-in; */
  }

  .message-box.sent {
    background-color: #efefef;
    line-height: 24px;
    background: var(--main-light-3);
    align-self: flex-end;
  }

  .message-box.received {
    color: initial;
    width: fit-content;
    padding-top: 16px;
    background-color: #F5F7F8;
    text-align: left;
    word-wrap: break-word;
    margin-bottom: 0;
    padding-bottom: 0;
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

  .refs {
    margin-bottom: 20px;
  }
}



.bottom {
  position: sticky;
  bottom: 0;
  width: 100%;
  margin: 0 auto;
  padding: 0.5rem 2rem;
  background: white;


  .input-box {
    display: flex;
    width: 100%;
    max-width: 1100px;
    margin: 0 auto;
    align-items: flex-end;
    background-color: #F5F7F8;
    border-radius: 2rem;
    height: auto;
    padding: 0.5rem;

    .user-input {
      flex: 1;
      height: 40px;
      padding: 0.5rem 1rem;
      background-color: transparent;
      border: none;
      font-size: 1.2rem;
      margin: 0 0.6rem;
      color: #111111;
      font-size: 16px;
      font-variation-settings: 'wght' 400, 'opsz' 10.5;
      outline: none;

      &:focus {
        outline: none;
        box-shadow: none;
      }

      &:active {
        outline: none;
      }
    }
  }

  .note {
    width: 100%;
    font-size: small;
    text-align: center;
    padding: 0rem;
    color: #ccc;
    margin: 4px 0;
  }
}



.ant-dropdown-link {
  color: var(--c-text-light-1);
  cursor: pointer;
}

.ant-btn-icon-only {
  font-size: 16px;
  cursor: pointer;
  background-color: transparent;
  border: none;
  height: 2.5rem;
  background-color: black;
  border-radius: 3rem;
  color: white;

  &:hover {
    color: white;
  }
}

button:disabled {
  background: #D7D7D7;
  cursor: not-allowed;
}

@media (max-width: 520px) {
  .chat {
    height: calc(100vh - 60px);
  }

  .chat-container .chat .header {
    background: var(--main-light-4);
    .header__left, .header__right {
      gap: 20px;
    }

    .nav-btn {
      font-size: 1.5rem;
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
</style>
