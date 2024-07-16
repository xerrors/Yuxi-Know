<!-- ChatComponent.vue -->
<template>
  <div class="chat">
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
          v-if="!state.isSidebarOpen"
          class="newchat nav-btn"
          @click="$emit('newconv')"
        >
          <FormOutlined />
        </div>
      </div>
      <div class="header__right">
        <div class="nav-btn text" @click="myAlert('未开发')">张文杰</div>
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
    <div ref="chatBox" class="chat-box">
      <div
        v-for="message in conv.messages"
        :key="message.id"
        class="message-box"
        :class="message.role"
      >
        <p v-if="message.role=='sent'" style="white-space: pre-line" class="message-text">{{ message.text }}</p>
        <p v-else v-html="renderMarkdown(message.text)" class="message-md" ></p>
      </div>
    </div>
    <div class="input-box">
      <input
        class="user-input"
        v-model="conv.inputText"
        @keydown.enter="sendMessage"
        placeholder="输入问题……"
      />
      <a-button size="large" @click="sendMessage" :disabled="(!conv.inputText && !isStreaming)">
        <template #icon> <SendOutlined v-if="!isStreaming" /> <LoadingOutlined v-else/> </template>
      </a-button>
    </div>
    <p class="note">即便强如雅典娜也可能会出错，请注意辨别内容的可靠性</p>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, toRefs } from 'vue'
import { SendOutlined, MenuOutlined, FormOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import { marked } from 'marked';

const props = defineProps({
  conv: Object,
  state: Object
})

const emit = defineEmits(['renameTitle'])

const { conv, state } = toRefs(props)
const chatBox = ref(null)
const isStreaming = ref(false)
const examples = ref([
  '写一个冒泡排序',
  '介绍一下 MECT',
  '介绍一下江南大学',
  'A大于B，B小于C，A和C哪个大？',
  '今天天气怎么样？'
])

marked.setOptions({
  gfm: true,
  breaks: true,
  tables: true,
  // 更多选项可以在 marked 文档中找到：https://marked.js.org/
});

const renameTitle = () => {
  const prompt = '请用一个很短的句子关于下面的对话内容的主题起一个名字，不要带标点符号：'
  const firstUserMessage = conv.value.messages[0].text
  const firstAiMessage = conv.value.messages[1].text
  const context = `${prompt}\n\n问题: ${firstUserMessage}\n\n回复: ${firstAiMessage}，主题是（一句话）：`
  simpleCall(context).then((data) => {
    emit('renameTitle', data.response.split("：")[0])
  })
}

const myAlert = (message) => {
  alert(message)
}

const renderMarkdown = (text) => {
  return marked(text)
}

const scrollToBottom = () => {
  setTimeout(() => {
    chatBox.value.scrollTop = chatBox.value.scrollHeight - chatBox.value.clientHeight
  }, 10)
}

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

const updateMessage = (text, id) => {
  const message = conv.value.messages.find((message) => message.id === id)
  if (message) {
    message.text = text
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
    const user_input = conv.value.inputText
    var cur_res_id = null
    conv.value.inputText = ''
    fetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        query: user_input,
        history: conv.value.history,
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
            if (cur_res_id === null) {
              appendAiMessage(data.response, data.refs)
              cur_res_id = conv.value.messages[conv.value.messages.length - 1].id
            } else {
              updateMessage(data.response, cur_res_id)
            }
            conv.value.history = data.history
            buffer = ''
          } catch (e) {
            console.log(e)
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
  width: 200px;
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  background: white;
  position: relative;
  box-sizing: border-box;
  flex: 5 5 auto;
}

.chat div.header {
  height: var(--header-height);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
}

.chat div.header .header__left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.nav-btn {
  font-size: 1.2rem;
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  justify-content: center;
  align-items: center;
  border-radius: 8px;
  color: #6D6D6D;
  cursor: pointer;

  &.text {
    font-size: 1rem;
    width: auto;
    padding: 0.5rem 1rem;
  }

  &:hover {
    background-color: #ECECEC;
  }
}


div.chat-examples {
  padding: 0 50px;
  text-align: center;
  position: absolute;
  top: 20%;
  width: 100%;
  z-index: 100;
}

.chat-examples h1 {
  margin-bottom: 20px;
  font-size: 24px;
  color: #333;
}

.opt {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.opt__button {
  background-color: white;
  color: #222;
  padding: 4px 1rem;
  border-radius: 1rem;
  cursor: pointer;
  border: 2px solid white;
  transition: background-color 0.3s;
  box-shadow: 0px 0px 10px 1px rgba(0, 0, 0, 0.05);

  &:hover {
    background-color: #fcfcfc;
    box-shadow: 0px 0px 10px 1px rgba(0, 0, 0, 0.1);
  }
}

.chat-box {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;
}

.message-box {
  max-width: 90%;
  display: inline-block;
  border-radius: 0.8rem;
  margin: 0.8rem 0;
  padding: 0.8rem;
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
  background: #EDF4F5;
  align-self: flex-end;
}

.message-box.received {
  color: initial;
  width: fit-content;
  padding-top: 16px;
  background-color: #f7f7f7;
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

img.message-image {
  max-width: 300px;
  max-height: 50vh;
  object-fit: contain;
}

.input-box {
  width: calc(100% - 2rem);
  max-width: calc(1100px - 2rem);
  margin: 0 auto;
  display: flex;
  align-items: center;
  background-color: #F4F4F4;
  border-radius: 2rem;
  height: 3.5rem;
  padding: 0.5rem;
}

input.user-input {
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

  &:focus {
    outline: none;
  }
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
}

button:disabled {
  background: #D7D7D7;
  cursor: not-allowed;
}

p.note {
  width: 100%;
  font-size: small;
  text-align: center;
  padding: 0rem;
  color: #ccc;
  margin: 4px 0;
}

/*
@keyframes slideInUp {
  from {
    opacity: 0;
    transform: translateY(100%);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
  */
</style>
