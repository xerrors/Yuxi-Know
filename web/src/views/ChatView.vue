<template>
  <div class="chat-container">
    <div class="chat">
      <div ref="chatBox" class="chat-box">
        <div
          v-for="message in state.messages"
          :key="message.id"
          class="message-box"
          :class="message.role"
        >
          <img v-if="message.filetype === 'image'" :src="message.url" class="message-image" alt="">
          <p v-else style="white-space: pre-line" class="message-text">{{ message.text }}</p>
        </div>
      </div>
      <div class="input-box">
        <a-button size="large" @click="clearChat">
          <template #icon> <ClearOutlined /> </template>
        </a-button>
        <a-input
          type="text"
          class="user-input"
          v-model:value="state.inputText"
          @keydown.enter="sendMessage"
          placeholder="输入问题……"
        />
        <a-button size="large" @click="sendMessage" :disabled="!state.inputText">
          <template #icon> <SendOutlined /> </template>
        </a-button>
      </div>
    </div>
    <!-- <div class="info">
      <h1>{{ info.title }}</h1>

      <p v-if="info.docs.length > 0" class="docs">{{ info.docs }}</p>

      <img v-if="info.image && typeof info.image === 'string'" :src="info.image" class="info-image" alt="">
      <div v-else-if="info.image && Array.isArray(info.image)">
        <img v-for="(img, index) in info.image" :key="index" :src="img" class="info-image" alt="">
      </div>

      <p v-show="info.graph?.nodes?.length > 0"><b>关联图谱</b></p>
      <div id="lite_graph" v-show="info.graph?.nodes?.length > 0"></div>
      <a-collapse v-model:activeKey="state.activeKey" v-if="info.docs.length > 0" accordion>
        <a-collapse-panel
          v-for="(doc, index) in info.docs"
          :key="index"
          :header="'来源' + (index + 1) + '：' + doc.fileName"
        >
          <p>{{ doc.text }}</p>
        </a-collapse-panel>
      </a-collapse>
      <p class="description" v-else-if="info.description && typeof info.description === 'string'">{{ info.description }}</p>
      <div v-else-if="info.description && Array.isArray(info.description)">
        <p class="description" v-for="(desc, index) in info.description" :key="index">{{ desc }}</p>
      </div>
    </div> -->
  </div>

  <p class="note">即便强如雅典娜也可能会出错，请注意辨别内容的可靠性</p>
</template>

<script setup>
// import * as echarts from 'echarts';
import { reactive, ref, onMounted } from 'vue'
import { SendOutlined, ClearOutlined } from '@ant-design/icons-vue'

// let myChart = null;
const chatBox = ref(null)
const state = reactive({
  history: [],
  messages: [],
  activeKey: [],
  inputText: ''
})

const default_info = {
  title: '你好，我是 Project: Athena',
  description: [
    '基于特定领域知识图谱的问答系统，支持多轮对话，支持外部信息检索，你可以：',
    '1. 图谱问答：输入问题，获取相关的答案',
    '2. 多轮筛选：在对话页面，可以通过多轮对话筛选来缩小搜索范围。例如，可以根据实体、具体类别、类型等进行筛选，以快速找到所需的专业知识。',
    '3. 知识图谱可视化：在知识图谱页面，用户可以通过可视化界面直观地了解实体之间的关系。可以缩放、平移和旋转图谱以查看不同层次的关系，还可以点击实体节点查看更多详细信息。',
    '4. 实体相关信息查看：可以通过右侧知识图谱下方的相关信息查看实体所有出现的地方，帮助全面查询理解，更清晰全面。',
  ],
  image: [],
  graph: null,
  docs: []
}

const info = reactive({
  ...default_info
})

const scrollToBottom = () => {
  setTimeout(() => {
    chatBox.value.scrollTop = chatBox.value.scrollHeight - chatBox.value.clientHeight
  }, 10) // 10ms 后滚动到底部
}

/**
 *
 * @param {*} message 消息内容
 * @param {*} role 消息
 */
const appendMessage = (message, role) => {
  state.messages.push({
    id: state.messages.length + 1,
    role,
    text: message
  })
  scrollToBottom()
}


// const appendPicMessage = (pic, type) => {
//   state.messages.push({
//     id: state.messages.length + 1,
//     type,
//     filetype: "image",
//     url: pic
//   })
//   scrollToBottom()
// }

const updateLastReceivedMessage = (message, id) => {
  const lastReceivedMessage = state.messages.find((message) => message.id === id)
  if (lastReceivedMessage) {
    lastReceivedMessage.text = message
  } else {
    state.messages.push({
      id,
      type: 'received',
      text: message
    })
  }
  scrollToBottom()
}

const sendMessage = () => {
  if (state.inputText.trim()) {
    appendMessage(state.inputText, 'sent')
    appendMessage('检索中……', 'received')
    const user_input = state.inputText
    const cur_res_id = state.messages[state.messages.length - 1].id
    state.inputText = ''
    fetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify({
        query: user_input,
        history: state.history,
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
            console.log('Finished')
            return
          }

          buffer += decoder.decode(value, { stream: true })
          console.log(buffer)
          const message = buffer.trim().split('\n').pop()
          // 尝试解析 message
          try {
            const data = JSON.parse(message)
            updateLastReceivedMessage(data.response, cur_res_id)
            state.history = data.history
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

const getFormattedDocs = (docs) => {
  const formattedDocs = docs.map((doc) => {
    var match = /出处 \[(\d+)\] \[([^\]]*)\]\(([^\)]*)\) \n\n(.*)/g.exec(doc);
    return {
      index: match[1],
      fileName: match[2],
      link: match[3],
      text: match[4].trim()
    }
  })
  console.log(formattedDocs)
  return formattedDocs
}

const sendDeafultMessage = () => {
  appendMessage('你好？我是 Project: Athena，有什么可以帮你？😊', 'received')
}

const clearChat = () => {
  state.messages = []
  state.history = []
  info.title = default_info.title
  info.description = default_info.description
  info.image = default_info.image
  info.graph = default_info.graph
  info.sents = default_info.sents
  info.docs = default_info.docs
  sendDeafultMessage()
}

onMounted(() => {
  sendDeafultMessage()

})
</script>

<style lang="less" scoped>
.chat-container {
  display: flex;
  gap: 1.5rem;
}

div.chat, div.info {
  height: calc(100vh - 180px);
}

.chat {
  display: flex;
  width: 100%;
  max-width: 1100px;
  flex-grow: 1;
  margin: 0 auto;
  flex-direction: column;
  background: #f5f5f5;
  border-radius: 8px;
  box-shadow: 0px 0.3px 0.9px rgba(0, 0, 0, 0.12), 0px 0.6px 2.3px rgba(0, 0, 0, 0.1),  0px 1px 5px rgba(0, 0, 0, 0.08);
}

.chat-box {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
  display: flex;
  flex-direction: column;

  // 平滑滚动
  scroll-behavior: smooth;

  &::-webkit-scrollbar {
    width: 0rem;
  }
}

.message-box {
  width: fit-content;
  max-width: 80%;
  display: inline-block;
  padding: 0.5rem;
  border-radius: 0.5rem;
  margin: 0.5rem 0;
  padding: 10px 16px;
  user-select: text;
  word-break: break-word;
  font-size: 14px;
  line-height: 20px;
  font-variation-settings: 'wght' 400, 'opsz' 10.5;
  font-weight: 400;
  box-sizing: border-box;
  box-shadow: 0px 0.3px 0.9px rgba(0, 0, 0, 0.12), 0px 1.6px 3.6px rgba(0, 0, 0, 0.16);
  animation: slideInUp 0.1s ease-in;
}

.message-box.sent {
  color: white;
  background-color: #efefef;
  // background: linear-gradient(90deg, #006880 10.79%, #005366 87.08%);
  background: linear-gradient(90deg, #40788c 10.79%, #005f77 87.08%);
  // background-color: #333;
  align-self: flex-end;
}

.message-box.received {
  color: #111111;
  background-color: #ffffff;
  text-align: left;
  // animation-delay: 0.2s; /* 延迟 100ms 开始动画 */
}

p.message-text {
  word-wrap: break-word;
  margin-bottom: 0;
}

img.message-image {
  max-width: 300px;
  max-height: 50vh;
  object-fit: contain;
}

.input-box {
  display: flex;
  align-items: center;
  padding: 1rem;
  border-top: 1px solid #ccc;
}

input.user-input {
  flex: 1;
  height: 40px;
  padding: 0.5rem 1rem;
  background-color: #fff;
  border: none;
  border-radius: 8px;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.1);
  font-size: 1.2rem;
  margin: 0 0.6rem;
  color: #111111;
  font-size: 16px;
  // line-height: 22px;
  font-variation-settings: 'wght' 400, 'opsz' 10.5;
}

.ant-btn-icon-only {
  font-size: 16px;
  border-radius: 8px;
  cursor: pointer;
}

// button:disabled {
//   // background: #ccc;
//   cursor: not-allowed;
// }

div.info {
  width: 400px;
  min-width: 400px;
  overflow-y: auto;
  flex-grow: 0;

  // 平滑滚动
  scroll-behavior: smooth;

  &::-webkit-scrollbar {
    width: 0rem;
  }
  // background-color: #ccc;
  // margin: 0 1rem;

  & > h1 {
    font-size: 1.5rem;
    margin: 0.5rem 0;
    // padding: 0.5rem;
    // text-align: center;
  }

  p.description {
    font-size: 1rem;
    margin: 0;
    // padding: 0.5rem;
    // max-height: 10rem;
    margin-bottom: 20px;
    // text-align: center;
  }

  img {
    width: 100%;
    height: fit-content;
    object-fit: contain;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 0.5rem;
  }

  #lite_graph {
    width: 400px;
    height: 300px;
    background: #f5f5f5;
    // border: 4px solid #ccc;
    border-radius: 8px;
    margin-bottom: 1rem;
    box-shadow: 0px 0.3px 0.9px rgba(0, 0, 0, 0.12), 0px 0.6px 2.3px rgba(0, 0, 0, 0.1),
      0px 1px 5px rgba(0, 0, 0, 0.08);
  }
}

p.note {
  font-size: small;
  text-align: center;
  padding: 1rem;
  color: #ccc;
}

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
</style>
