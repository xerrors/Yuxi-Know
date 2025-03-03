<template>
  <div class="text-chunking-container">
    <div class="sidebar">
      <div class="additional-params">
        <h4>相关参数</h4>
        <a-form
          :model="params"
          name="basic"
          autocomplete="off"
          layout="vertical"
          @finish="chunkText"
        >
          <a-form-item label="Chunk Size" name="chunkSize" >
            <a-input v-model:value="params.chunkSize" :disabled="params.useParser && state.useFile" />
          </a-form-item>
          <a-form-item label="Chunk Overlap" name="chunkOverlap" >
            <a-input v-model:value="params.chunkOverlap" :disabled="params.useParser && state.useFile" />
          </a-form-item>
          <a-form-item label="使用文件节点解析器" name="useParser" v-if="state.useFile">
            <a-switch v-model:checked="params.useParser" />
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit" :loading="state.loading">Chunk Text</a-button>
          </a-form-item>
        </a-form>
        <!-- Future parameters can be added here -->
      </div>
    </div>
    <div class="result-container">
      <div class="input-container">
        <div class="actions">
          <span :class="{'active': !state.useFile}" @click="state.useFile = false">输入文本</span>
          <span :class="{'active': state.useFile}" @click="state.useFile = true">上传文件</span>
        </div>
        <div class="upload" v-if="state.useFile">
          <a-upload-dragger
            class="upload-dragger"
            v-model:fileList="fileList"
            name="file"
            :max-count="1"
            :disabled="state.uploading"
            action="/api/data/upload"
            @change="handleFileUpload"
            @drop="handleDrop"
          >
            <p class="ant-upload-text">点击或者把文件拖拽到这里上传</p>
            <p class="ant-upload-hint">
              目前仅支持上传文本文件，如 .pdf, .txt, .md。且同名文件无法重复添加
            </p>
          </a-upload-dragger>
        </div>
        <textarea v-if="!state.useFile" v-model="text" placeholder="Enter text to chunk"></textarea>
        <div class="infos" v-if="!state.useFile">
          <!-- <span>字数: {{ wordCount }}</span> -->
          <span>字符数: {{ charCount }}</span>
          <span>Token 数：{{ estimatedTokenCount }}</span>
        </div>
      </div>
      <!-- <div>{{ chunks[0] }}</div> -->
      <div id="result-cards" class="result-cards">
        <div v-for="(chunk, index) in chunks" :key="index" class="chunk">
          <p><strong>#{{ index + 1 }}</strong> {{ chunk.text }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed } from 'vue';
import { message } from 'ant-design-vue'

const text = ref('');
const state = reactive({
  loading: false,
  uploading: false,
  useFile: false,
})

const params = reactive({
  chunkSize: 500,
  chunkOverlap: 20,
  useParser: false,
})
const chunks = ref([]);
const fileList = ref([]);

const wordCount = computed(() => text.value.split(/\s+/).filter(Boolean).length);
const charCount = computed(() => text.value.length)
const estimatedTokenCount = computed(() => {
  // 将文本分割成字符数组
  const chars = text.value.split('');
  let tokenCount = 0;
  for (let char of chars) {
    if (/[\u4e00-\u9fff]/.test(char)) {
      tokenCount += 1; // 对于中文字符，通常计为一个 token
    }
    else if (/[a-zA-Z]/.test(char)) {
      tokenCount += 0.25; // 对于英文单词，大约每 4 个字符算作一个 token
    }
    else {
      tokenCount += 0.5; // 对于中文字符，通常计为一个 token
    }
  }
  return Math.ceil(tokenCount);
})

const chunkText = async () => {
  let text_or_file = ''
  if (state.useFile) {
    if (fileList.value.length === 0) {
      message.error("请上传文件")
      return
    }
    console.log(fileList.value)
    text_or_file = fileList.value.filter(file => file.status === 'done').map(file => file.response.file_path)[0]
  } else {
    if (text.value.length === 0) {
      message.error("请输入文本")
      return
    }
    text_or_file = text.value
  }

  try {
    state.loading = true
    const response = await fetch('/api/tool/text-chunking', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text_or_file,
        params: {
          chunk_size: params.chunkSize,
          chunk_overlap: params.chunkOverlap,
          use_parser: params.useParser
        }
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }

    const data = await response.json();
    chunks.value = data.nodes;
    state.loading = false
  } catch (error) {
    console.error('Error chunking text:', error);
    state.loading = false
  }
};
</script>

<style lang="less" scoped>
.text-chunking-container {
  display: flex;
  border-radius: 8px;
  font-family: 'Arial', sans-serif;

  .sidebar {
    position: sticky;
    top: 0;
    width: 350px; /* 初始宽度 */
    background-color: var(--bg-sider);
    border-right: 1px solid var(--main-light-3);
    padding: 20px;
    min-width: 250px;
    flex: 1;

    .additional-params {
      h4 {
        font-size: 1.2em;
        margin-bottom: 10px;
      }
    }
  }

  .result-container {
    flex: 3;
    padding: 20px;

    .input-container {
      display: flex;
      flex-direction: column;
      margin-bottom: 15px;

      .actions {
        display: flex;
        justify-content: space-between;
        margin-bottom: 10px;
        width: fit-content;
        background-color: var(--gray-200);
        padding: 4px;
        border-radius: 4px;

        span {
          color: var(--gray-900);
          cursor: pointer;
          padding: 4px 10px;
          border-radius: 4px;
          transition: background-color 0.3s;

          &.active {
            background-color: white;
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03),0 1px 6px -1px rgba(0, 0, 0, 0.02),0 2px 4px 0 rgba(0, 0, 0, 0.02)
          }
        }
      }

      textarea {
        resize: vertical;
        height: 300px;
        padding: 1rem;
        border: 1px solid var(--gray-300);
        border-radius: 8px;
        font-size: 1rem;
        transition: border-color 0.3s;
        background-color: var(--gray-100);

        &:focus {
          border-color: var(--main-color);
          outline: none;
        }
      }

      .infos {
        padding: 10px; /* Padding for spacing */
        margin-top: 10px; /* Space above the infos */
        font-size: 1em; /* Font size */
        color: var(--gray-800); /* Text color */
        display: flex;
        gap: 16px;
      }

    }

    .result-cards {
      column-count: 3; /* 设置列数 */
      column-gap: 10px; /* 列之间的间距 */
    }

    .chunk {
      background-color: var(--main-5);
      border: 1px solid var(--main-light-3);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 10px;
      box-shadow: 0 0 10px 2px rgba(0, 0, 0, 0.01);
      break-inside: avoid; /* 避免元素被分割到不同列 */
      // 强制换行
      word-wrap: break-word;
      word-break: break-all;
    }
  }
}


@media (max-width: 980px) {
  #result-cards {
    column-count: 1;
  }
}

@media (min-width: 981px) and (max-width: 1500px) {
  #result-cards {
    column-count: 2;
  }
}

@media (min-width: 1501px){
  #result-cards {
    column-count: 3;
  }
}
</style>