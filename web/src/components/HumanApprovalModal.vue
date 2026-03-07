<template>
  <transition name="slide-up">
    <div v-if="visible" class="approval-modal">
      <div class="approval-content">
        <div class="approval-header">
          <h4>{{ question }}</h4>
        </div>

        <div v-if="operation" class="approval-operation">
          <span class="label">操作：</span>
          <span class="operation-text">{{ operation }}</span>
        </div>

        <div class="question-options">
          <label v-for="(item, index) in options" :key="`${item.value}-${index}`" class="option-item">
            <input
              v-if="multiSelect"
              type="checkbox"
              :value="item.value"
              :checked="selectedValues.includes(item.value)"
              :disabled="isProcessing"
              @change="toggleSelect(item.value)"
            />
            <input
              v-else
              type="radio"
              name="approval-option"
              :value="item.value"
              :checked="selectedValues[0] === item.value"
              :disabled="isProcessing"
              @change="setSingle(item.value)"
            />
            <span :class="{ recommended: index === 0 && String(item.label).includes('(Recommended)') }">
              {{ item.label }}
            </span>
          </label>
        </div>

        <div v-if="allowOther" class="other-input">
          <input
            v-model.trim="otherText"
            type="text"
            :disabled="isProcessing"
            placeholder="Other: 输入自定义答案"
          />
        </div>
      </div>

      <div class="approval-actions">
        <button class="btn btn-reject" @click="handleCancel" :disabled="isProcessing">取消</button>
        <button class="btn btn-approve" @click="handleSubmit" :disabled="isSubmitDisabled">提交</button>
      </div>

      <div v-if="isProcessing" class="approval-processing">
        <span class="processing-spinner"></span>
        处理中...
      </div>
    </div>
  </transition>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  question: { type: String, default: '请选择一个选项' },
  operation: { type: String, default: '' },
  options: { type: Array, default: () => [] },
  multiSelect: { type: Boolean, default: false },
  allowOther: { type: Boolean, default: true }
})

const emit = defineEmits(['submit', 'cancel'])

const isProcessing = ref(false)
const selectedValues = ref([])
const otherText = ref('')

const resetForm = () => {
  isProcessing.value = false
  selectedValues.value = []
  otherText.value = ''
}

watch(
  () => props.visible,
  (newVal) => {
    if (!newVal) {
      resetForm()
    }
  }
)

watch(
  () => props.options,
  (next) => {
    if (!Array.isArray(next) || next.length === 0) {
      selectedValues.value = []
      return
    }
    if (props.multiSelect) {
      selectedValues.value = selectedValues.value.filter((value) =>
        next.some((item) => item?.value === value)
      )
      return
    }
    const current = selectedValues.value[0]
    if (current && next.some((item) => item?.value === current)) return
    selectedValues.value = [next[0].value]
  },
  { immediate: true, deep: true }
)

watch(
  () => props.multiSelect,
  (isMulti) => {
    if (isMulti) return
    if (selectedValues.value.length > 1) {
      selectedValues.value = selectedValues.value.slice(0, 1)
    }
  }
)

const toggleSelect = (value) => {
  if (isProcessing.value) return
  if (selectedValues.value.includes(value)) {
    selectedValues.value = selectedValues.value.filter((item) => item !== value)
  } else {
    selectedValues.value = [...selectedValues.value, value]
  }
}

const setSingle = (value) => {
  if (isProcessing.value) return
  selectedValues.value = [value]
}

const isSubmitDisabled = computed(() => {
  if (isProcessing.value) return true
  const hasSelected = selectedValues.value.length > 0
  const hasOther = props.allowOther && Boolean(otherText.value)
  return !hasSelected && !hasOther
})

const buildAnswer = () => {
  const selected = selectedValues.value
  const other = otherText.value
  if (props.allowOther && other) {
    return {
      type: 'other',
      text: other,
      selected: selected
    }
  }
  if (props.multiSelect) {
    return selected
  }
  return selected[0]
}

const handleSubmit = () => {
  if (isSubmitDisabled.value) return
  isProcessing.value = true
  emit('submit', buildAnswer())
}

const handleCancel = () => {
  if (isProcessing.value) return
  emit('cancel')
}
</script>

<style scoped>
.approval-modal {
  background: var(--gray-0);
  border-radius: 12px 12px;
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.12);
  margin: 0 auto 8px;
  max-width: 800px;
  width: 100%;
  border: 1px solid var(--gray-200);
}

.approval-content {
  padding: 16px 20px;
}

.approval-header {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-bottom: 12px;
}

.approval-header h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--gray-800);
  text-align: center;
}

.approval-operation {
  background: var(--gray-50);
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.approval-operation .label {
  color: var(--gray-600);
  font-weight: 500;
  flex-shrink: 0;
}

.approval-operation .operation-text {
  color: var(--gray-800);
  word-break: break-word;
}

.question-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--gray-800);
  font-size: 14px;
}

.option-item .recommended {
  color: var(--main-color);
  font-weight: 600;
}

.other-input {
  margin-top: 10px;
}

.other-input input {
  width: 100%;
  border: 1px solid var(--gray-300);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 13px;
  outline: none;
}

.other-input input:focus {
  border-color: var(--main-color);
}

.approval-actions {
  display: flex;
  gap: 10px;
  padding: 12px 20px 16px;
}

.btn {
  flex: 1;
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-reject {
  background: var(--gray-100);
  color: var(--gray-700);
}

.btn-reject:hover:not(:disabled) {
  background: var(--gray-200);
}

.btn-approve {
  background: var(--main-color);
  color: var(--gray-0);
}

.btn-approve:hover:not(:disabled) {
  background: var(--main-700);
}

.approval-processing {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px;
  color: var(--gray-600);
  font-size: 13px;
  background: var(--gray-25);
  border-top: 1px solid var(--gray-100);
}

.processing-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--gray-300);
  border-top-color: var(--main-color);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.25s ease;
}

.slide-up-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

@media (max-width: 520px) {
  .approval-content {
    padding: 12px 16px;
  }

  .approval-header h4 {
    font-size: 14px;
  }

  .approval-operation {
    font-size: 12px;
    padding: 8px 10px;
  }

  .approval-actions {
    padding: 10px 16px 12px;
    gap: 8px;
  }

  .btn {
    padding: 8px 16px;
    font-size: 13px;
  }
}
</style>
