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
            <a-input v-model:value="params.chunkSize" />
          </a-form-item>
          <a-form-item label="Chunk Overlap" name="chunkOverlap" >
            <a-input v-model:value="params.chunkOverlap" />
          </a-form-item>

          <a-form-item>
            <a-button type="primary" html-type="submit">Chunk Text</a-button>
          </a-form-item>
        </a-form>
        <!-- Future parameters can be added here -->
      </div>
    </div>
    <div class="result-container">
      <div class="input-container">
        <textarea v-model="text" placeholder="Enter text to chunk"></textarea>
        <div class="infos">
          <!-- <span>字数: {{ wordCount }}</span> -->
          <span>字符数: {{ charCount }}</span>
          <span>Token 数：{{ estimatedTokenCount }}</span>
        </div>
      </div>
      <div id="result-cards" class="result-cards">
        <div v-for="(chunk, index) in chunks" :key="index" class="chunk">
          <p>{{ chunk }}</p>
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
  loading: true,
})

const params = reactive({
  chunkSize: 500,
  chunkOverlap: 20
})
const chunks = ref([]);

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
  if (text.value.length === 0) {
    message.error("请输入文本")
    return
  }
  try {
    state.loading = true
    const response = await fetch('/api/tools/text_chunking', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text.value,
        chunk_size: params.chunkSize,
        chunk_overlap: params.chunkOverlap
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }

    const data = await response.json();
    chunks.value = data.nodes.map(node => node.text);
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

      textarea {
        resize: vertical;
        height: 300px;
        padding: 1rem;
        border: 1px solid var(--gray-300);
        border-radius: 8px;
        font-size: 1rem;
        transition: border-color 0.3s;
        background-color: var(--gray-50);

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
      background-color: #f9fcff;
      border-radius: 4px;
      padding: 10px;
      margin-bottom: 10px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
      break-inside: avoid; /* 避免元素被分割到不同列 */
    }
  }
}


@media (max-width: 768px) {
  #result-cards {
    column-count: 1;
  }
}

@media (min-width: 769px) and (max-width: 1200px) {
  #result-cards {
    column-count: 2;
  }
}

@media (min-width: 1201px) and (max-width: 1900px) {
  #result-cards {
    column-count: 3;
  }
}

@media (min-width: 1901px){
  #result-cards {
    column-count: 4;
  }
}
</style>