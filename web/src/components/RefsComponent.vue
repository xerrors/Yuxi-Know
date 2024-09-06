<!-- RefsComponent.vue -->
<template>
  <div class="refs" v-if="showRefs">
    <div class="tags">
      <span class="item"><GlobalOutlined /> {{ message.model_name }}</span>
      <span class="filetag item"
        v-for="(results, filename) in message.groupedResults"
        :key="filename"
        @click="openDetail = true"
      >
        <FileTextOutlined /> {{ filename }}
        <a-drawer
          v-model:open="openDetail"
          title="检索详情"
          width="800"
          :contentWrapperStyle="{ maxWidth: '100%'}"
          placement="right"
          class="retrieval-detail"
          rootClassName="root"
        >
          <div class="fileinfo">
            <p><strong>文件名:</strong> {{ results[0].file.filename }}</p>
            <p><strong>文件类型:</strong> {{ results[0].file.type }}</p>
            <p><strong>创建时间:</strong> {{ new Date(results[0].file.created_at * 1000).toLocaleString() }}</p>
          </div>
          <div v-for="(res, idx) in results" :key="idx" class="result-item">
            <p class="result-id"><strong>ID:</strong> #{{ res.id }}</p>
            <p class="result-distance">
              <strong>相似度距离:</strong>
              <div class="scorebar">
                <a-progress :percent="parseFloat((res.distance * 100).toFixed(2))" stroke-color="#1677FF" :size="[200, 10]"/>
              </div>
            </p>
            <p class="result-rerank-score" v-if="res.rerank_score">
              <strong>重排序分数:</strong>
              <div class="scorebar">
                <a-progress :percent="parseFloat((res.rerank_score * 100).toFixed(2))" stroke-color="#1677FF" :size="[200, 10]"/>
              </div>
            </p>
            <a-divider />
            <p class="result-text">{{ res.entity.text }}</p>
          </div>
        </a-drawer>
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  GlobalOutlined,
  FileTextOutlined,
} from '@ant-design/icons-vue'

const props = defineProps({
  message: Object,
})

const message = ref(props.message)

const openDetail = ref(false)
const showRefs = computed(() => message.value.role=='received' && message.value.status=='finished')
</script>

<style lang="less" scoped>
.refs {
  display: flex;
  margin-bottom: 20px;
  color: var(--c-text-light-4);
  font-size: 14px;
  gap: 10px;

  .item {
    background: var(--main-10);
    color: var(--main-600);
    padding: 2px 8px;
    border-radius: 8px;
    font-size: 14px;
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;

    .filetag {
      display: flex;
      align-items: center;
      gap: 5px;
      cursor: pointer;

      &:hover {
        background: var(--main-25);
      }
    }
  }
}


.retrieval-detail {
  .fileinfo {
    margin-bottom: 20px;
    padding: 1rem;
    background: var(--main-25);
    color: var(--main-800);
    border-radius: 8px;
    border: 1px solid var(--main-100);
    p {
      margin: 10px;
      line-height: 1.5;
    }
  }

  .result-item {
    margin-bottom: 20px;
    padding: 24px 16px 10px 16px;
    border: 1px solid #e8e8e8;
    border-radius: 8px;
    background: var(--main-light-6);

    .result-id,
    .result-distance,
    .result-rerank-score,
    .result-text-label,
    .result-text {
      margin: 5px 0;
    }

    .scorebar {
      margin-left: 10px;
      display: inline-block;
      width: 200px;
      padding-bottom: 2px;


      & > * {
        margin: 0;
      }
    }
  }
}
</style>
