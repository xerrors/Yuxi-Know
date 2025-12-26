<template>
  <div class="todo-list-result">
    <!-- <div class="todo-header">
      <h4><UnorderedListOutlined /> 待办事项</h4>
    </div> -->
    <div class="todo-content">
      <div v-for="(item, index) in data" :key="index" class="todo-item">
        <div class="todo-status">
          <CheckCircleOutlined v-if="item.status === 'completed'" class="icon completed" />
          <SyncOutlined v-else-if="item.status === 'in_progress'" class="icon in-progress" spin />
          <ClockCircleOutlined v-else-if="item.status === 'pending'" class="icon pending" />
          <CloseCircleOutlined v-else-if="item.status === 'cancelled'" class="icon cancelled" />
          <QuestionCircleOutlined v-else class="icon unknown" />
        </div>
        <div class="todo-text" :class="{ completed: item.status === 'completed', cancelled: item.status === 'cancelled' }">
          {{ item.content }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import {
  UnorderedListOutlined,
  CheckCircleOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons-vue'

defineProps({
  data: {
    type: Array,
    required: true
  }
})
</script>

<style lang="less" scoped>
.todo-list-result {
  background: var(--gray-0);
  border-radius: 8px;
  // border: 1px solid var(--gray-200);
  overflow: hidden;

  .todo-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--gray-100);
    background: var(--gray-25);

    h4 {
      margin: 0;
      font-size: 14px;
      font-weight: 500;
      color: var(--main-color);
      display: flex;
      align-items: center;
      gap: 6px;
    }
  }

  .todo-content {
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .todo-item {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 8px 12px;
    border-radius: 6px;
    background: var(--gray-50);
    border: 1px solid var(--gray-100);
    transition: background-color 0.2s;

    &:hover {
      background: var(--gray-100);
    }

    .todo-status {
      padding-top: 2px;
      flex-shrink: 0;

      .icon {
        font-size: 16px;

        &.completed { color: #52c41a; }
        &.in-progress { color: #1890ff; }
        &.pending { color: #faad14; }
        &.cancelled { color: #ff4d4f; }
        &.unknown { color: var(--gray-400); }
      }
    }

    .todo-text {
      font-size: 14px;
      line-height: 1.5;
      color: var(--gray-800);
      word-break: break-word;

      &.completed {
        text-decoration: line-through;
        color: var(--gray-500);
      }

      &.cancelled {
        text-decoration: line-through;
        color: var(--gray-400);
      }
    }
  }
}
</style>
