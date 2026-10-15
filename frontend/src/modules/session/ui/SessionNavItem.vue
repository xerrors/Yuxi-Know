<template>
  <div
    class="session-item"
    :class="{
      active: currentChatId === chat.id,
      nested,
      'has-status': isRunning || Boolean(activityLabel) || chat.yuxi.unread
    }"
  >
    <button
      type="button"
      class="session-select"
      :aria-current="currentChatId === chat.id ? 'page' : undefined"
      @click="$emit('select-chat', chat.id)"
      @dblclick.stop="renameChat"
      @click.middle="$emit('archive-chat', chat.id)"
    >
      <span class="session-title">{{ chat.yuxi.title || '新的对话' }}</span>
      <span
        v-if="chat.status === 'failed'"
        class="thread-status thread-status-failed"
        role="img"
        aria-label="执行失败"
      >
        <CircleAlert :size="14" aria-hidden="true" />
      </span>
      <span
        v-else-if="activityLabel"
        class="activity-badge"
        :class="`activity-${chat.status}`"
        role="status"
        :title="activityLabel"
      >
        {{ activityLabel }}
      </span>
      <span class="actions-mask"></span>
      <span
        v-if="isRunning"
        class="thread-status"
        role="status"
        aria-label="正在运行"
        title="正在运行"
      >
        <span class="status-spinner" aria-hidden="true"></span>
      </span>
      <span
        v-else-if="!activityLabel && chat.yuxi.unread"
        class="thread-status thread-status-ready"
        role="status"
        title="有新回复"
      ></span>
    </button>
    <span class="session-actions" @click.stop @dblclick.stop>
      <a-dropdown :trigger="['click']">
        <template #overlay>
          <a-menu>
            <a-menu-item
              key="pin"
              :icon="h(chat.yuxi.is_pinned ? PinOff : Pin, { size: 14 })"
              @click.stop="$emit('toggle-pin', chat.id)"
            >
              {{ chat.yuxi.is_pinned ? '取消置顶' : '置顶' }}
            </a-menu-item>
            <a-menu-item key="rename" :icon="h(SquarePen, { size: 14 })" @click.stop="renameChat">
              重命名
            </a-menu-item>
            <a-menu-item
              key="archive"
              :icon="h(Archive, { size: 14 })"
              @click.stop="$emit('archive-chat', chat.id)"
            >
              归档
            </a-menu-item>
          </a-menu>
        </template>
        <span class="action-btn-wrapper">
          <a-button type="text" class="more-btn" aria-label="对话操作">
            <MoreVertical :size="16" />
          </a-button>
          <Pin v-if="chat.yuxi.is_pinned" :size="14" class="pinned-indicator" />
        </span>
      </a-dropdown>
    </span>
  </div>
</template>

<script setup>
import { computed, h } from 'vue'
import { SESSION_ACTIVITY_LABELS } from '@/modules/session/model/sessionActivity'
import { message, Modal } from 'ant-design-vue'
import { Archive, CircleAlert, MoreVertical, Pin, PinOff, SquarePen } from '@lucide/vue'

const props = defineProps({
  chat: { type: Object, required: true },
  currentChatId: { type: String, default: null },
  nested: { type: Boolean, default: false }
})

const emit = defineEmits(['select-chat', 'archive-chat', 'rename-chat', 'toggle-pin'])
const activityLabel = computed(() => SESSION_ACTIVITY_LABELS[props.chat.status] || '')
const isRunning = computed(() => props.chat.status === 'in_progress')

const renameChat = () => {
  let newTitle = props.chat.yuxi.title || ''
  Modal.confirm({
    title: '重命名对话',
    icon: null,
    closable: false,
    maskClosable: true,
    centered: true,
    width: 400,
    class: 'rename-session-modal',
    content: h('div', [
      h('p', { class: 'rename-session-description' }, '保持简短且易于识别'),
      h('input', {
        value: newTitle,
        class: 'rename-session-input',
        onInput: (event) => {
          newTitle = event.target.value
        }
      })
    ]),
    okText: '保存',
    cancelText: '取消',
    onOk: () => {
      if (!newTitle.trim()) {
        message.warning('标题不能为空')
        return Promise.reject()
      }
      emit('rename-chat', { chatId: props.chat.id, title: newTitle })
    }
  })
}
</script>

<style lang="less">
.rename-session-modal {
  .ant-modal-content {
    padding: 22px 24px 20px;
  }

  .ant-modal-confirm-title {
    line-height: 1.4;
  }

  .ant-modal-confirm-body .ant-modal-confirm-content {
    width: 100%;
    max-width: none !important;
    margin-top: 4px;
  }

  .ant-modal-confirm-btns {
    display: flex;
    justify-content: flex-end;
    margin-top: 18px;

    .ant-btn {
      min-width: 68px;
      height: 34px;
      font-size: 14px;
    }
  }
}

.rename-session-description {
  margin: 0 0 14px;
  color: var(--gray-500);
  font-size: 13px;
}

.rename-session-input {
  width: 100%;
  height: 38px;
  padding: 0 12px;
  color: var(--gray-900);
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  outline: none;

  &:focus {
    border-color: var(--main-400);
    box-shadow: 0 0 0 2px var(--main-50);
  }
}
</style>

<style lang="less" scoped>
.session-item {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  height: 32px;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;

  &.nested {
    .session-select {
      padding-left: 30px;
    }
  }

  &:hover {
    background: var(--gray-50);

    .actions-mask,
    .session-actions {
      opacity: 1;
    }

    .actions-mask {
      background: linear-gradient(to right, transparent, var(--gray-50) 28px);
    }

    .more-btn {
      display: inline-flex;
    }

    .pinned-indicator,
    .thread-status {
      display: none;
    }
  }

  &.active {
    background-color: color-mix(in srgb, var(--gray-100) 6%, var(--gray-100));
    color: var(--gray-1000);

    .session-title {
      font-weight: 600;
    }

  }

  &.has-status {
    .actions-mask {
      display: none;
    }
    .session-select {
      padding-right: 32px;
    }

    .session-title {
      text-overflow: clip;
      mask-image: linear-gradient(to right, #000 calc(100% - 16px), transparent);
    }
  }

  &:has(.pinned-indicator) {
    .actions-mask,
    .session-actions {
      opacity: 1;
    }
  }

  &.has-status:not(:hover) {
    .actions-mask,
    .session-actions {
      opacity: 0;
    }
  }
}

.session-select {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  height: 100%;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  text-align: left;

  &:focus-visible {
    outline: 2px solid var(--main-300);
    outline-offset: -2px;
  }
}

.session-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-badge {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  gap: 4px;
  margin-left: 6px;
  padding: 2px 6px;
  border-radius: 10px;
  background: var(--gray-100);
  color: var(--gray-600);
  font-size: 11px;
  line-height: 16px;
}

.activity-waiting_approval,
.activity-waiting_answer {
  background: var(--main-100);
  color: var(--main-700);
  font-weight: 600;
}

.thread-status {
  position: absolute;
  top: 50%;
  right: 16px;
  display: inline-flex;
  align-items: center;
  color: var(--main-color);
  pointer-events: none;
  transform: translateY(-50%) translateX(50%);
}

.thread-status-failed {
  color: var(--gray-500);
}

.status-spinner {
  width: 14px;
  height: 14px;
  box-sizing: border-box;
  border: 2px solid var(--gray-200);
  border-top-color: var(--gray-600);
  border-radius: 50%;
  animation: thread-status-spin 1s linear infinite;
}

.thread-status-ready {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--main-color);
}

.actions-mask {
  position: absolute;
  inset: 0 0 0 auto;
  width: 56px;
  background: linear-gradient(to right, transparent, var(--main-5) 28px);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.session-actions {
  position: absolute;
  top: 50%;
  right: 4px;
  display: flex;
  align-items: center;
  opacity: 0;
  transform: translateY(-50%);
  transition: opacity 0.2s ease;
}

.action-btn-wrapper {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
}

.more-btn {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  color: var(--gray-600);
}

.pinned-indicator {
  color: var(--gray-400);
}

@keyframes thread-status-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
