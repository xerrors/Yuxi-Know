<template>
  <div class="ocr-settings-section">
    <div class="section-title">默认 OCR 方法</div>
    <section class="settings-panel">
      <div class="setting-row">
        <div class="setting-copy">
          <div class="setting-label">{{ items?.default_ocr_engine?.des || '默认 OCR 解析引擎' }}</div>
          <p class="setting-description">未单独指定解析方式时，使用此引擎识别文档内容与版面。</p>
        </div>
        <div class="setting-content is-compact">
          <OCRSelector
            :model-value="configStore.config?.default_ocr_engine"
            @update:model-value="configStore.setConfigValue('default_ocr_engine', $event)"
          />
        </div>
      </div>
    </section>

    <div class="section-title">OCR 服务配置</div>
    <p class="section-description">
      地址留空时读取对应环境变量，凭据留空时保留原值，解析选项使用所选值。
    </p>
    <div class="option-list">
      <section v-for="option in configOptions" :key="option.key" class="option-card">
        <header class="option-header">
          <div class="option-heading">
            <div class="option-title">
              <h4>{{ option.name }}</h4>
              <span v-if="option.params.fields.length === 1" class="option-field-name">
                {{ option.params.fields[0].label }}
              </span>
            </div>
            <p>{{ option.description }}</p>
          </div>
          <div class="option-actions" :class="{ editing: editingKey === option.key }">
            <template v-if="editingKey === option.key">
              <a-button size="small" :disabled="savingOption === option.key" @click="cancelEditing">
                取消
              </a-button>
              <a-button
                type="primary"
                size="small"
                class="save-button"
                :loading="savingOption === option.key"
                @click="saveOption(option)"
              >
                保存
              </a-button>
            </template>
            <a-button
              v-else
              type="text"
              size="small"
              :disabled="Boolean(editingKey)"
              @click="startEditing(option)"
            >
              编辑
            </a-button>
          </div>
        </header>
        <div v-if="editingKey === option.key" class="option-fields">
          <div
            v-for="field in option.params.fields"
            :key="field.key"
            class="option-field"
          >
            <label
              v-if="option.params.fields.length > 1"
              :for="`${option.key}-${field.key}`"
              class="setting-label"
            >{{ field.label }}</label>
            <a-input-password
              v-if="field.sensitive"
              :id="`${option.key}-${field.key}`"
              v-model:value="draftValue[field.key]"
              :aria-label="field.label"
              :placeholder="field.environment"
              autocomplete="new-password"
              :disabled="clearedFields[field.key]"
            />
            <a-select
              v-else-if="field.choices"
              :id="`${option.key}-${field.key}`"
              v-model:value="draftValue[field.key]"
              :aria-label="field.label"
              :options="
                field.choices.map((value) => ({
                  value,
                  label: field.choice_labels?.[value] || value,
                }))
              "
            />
            <a-input
              v-else
              :id="`${option.key}-${field.key}`"
              v-model:value="draftValue[field.key]"
              :aria-label="field.label"
              :placeholder="field.placeholder || field.environment"
              allow-clear
            />
            <small>
              {{ field.sensitive ? '留空保持现有凭据；勾选清除会移除数据库中的值。' : field.help }}
            </small>
            <a-checkbox
              v-if="field.sensitive && option.sensitive_state?.[field.key]?.source === 'database'"
              v-model:checked="clearedFields[field.key]"
            >
              清除已保存凭据
            </a-checkbox>
          </div>
        </div>
        <div v-else class="option-fields option-values">
          <div v-for="field in option.params.fields" :key="field.key" class="option-field">
            <span v-if="option.params.fields.length > 1" class="setting-label">{{ field.label }}</span>
            <a-input
              :aria-label="field.label"
              :value="getFieldDisplay(option, field)"
              :class="{ 'masked-value': field.sensitive }"
              disabled
            />
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { configOptionsApi } from '@/apis/system_api'
import { useConfigStore } from '@/modules/settings/model/config'
import OCRSelector from '@/modules/settings/ui/OCRSelector.vue'

const configStore = useConfigStore()
const OCR_OPTION_KEYS = new Set([
  'mineru_ocr_host_opts',
  'mineru_official_api_opts',
  'pp_structure_v3_ocr_host_opts',
  'paddleocr_api_opts'
])
const items = computed(() => configStore.config?._config_items || {})
const configOptions = ref([])
const editingKey = ref('')
const draftValue = ref({})
const clearedFields = ref({})
const savingOption = ref('')

const loadConfigOptions = async () => {
  try {
    const data = await configOptionsApi.getOptions()
    configOptions.value = (data.options || [])
      .filter((option) => OCR_OPTION_KEYS.has(option.key))
      .map((option) => ({
        ...option,
        value: { ...(option.value || {}) },
        sensitive_state: { ...(option.sensitive_state || {}) }
      }))
  } catch (error) {
    message.error(error.message || '加载 OCR 服务配置失败')
  }
}

const startEditing = (option) => {
  editingKey.value = option.key
  clearedFields.value = {}
  draftValue.value = Object.fromEntries(
    option.params.fields.map((field) => [
      field.key,
      option.value?.[field.key] ?? field.default ?? ''
    ])
  )
}

const cancelEditing = () => {
  editingKey.value = ''
  draftValue.value = {}
  clearedFields.value = {}
}

const getFieldDisplay = (option, field) => {
  if (!field.sensitive) {
    const value = option.value?.[field.key] ?? field.default
    return field.choice_labels?.[value] || value || `读取 ${field.environment}`
  }
  const state = option.sensitive_state?.[field.key]
  if (state?.source === 'database') return state.preview
  if (state?.source === 'environment') return `已通过 ${field.environment} 配置`
  return '未配置'
}

const saveOption = async (option) => {
  savingOption.value = option.key
  try {
    const value = Object.fromEntries(
      option.params.fields
        .filter((field) => !field.sensitive || draftValue.value[field.key]?.trim() || clearedFields.value[field.key])
        .map((field) => [field.key, clearedFields.value[field.key] ? '' : draftValue.value[field.key]])
    )
    const data = await configOptionsApi.updateOption(option.key, value)
    Object.assign(option, data.option, {
      value: { ...(data.option.value || {}) },
      sensitive_state: { ...(data.option.sensitive_state || {}) }
    })
    cancelEditing()
    message.success('配置已保存')
  } catch (error) {
    message.error(error.message || '保存配置失败')
  } finally {
    savingOption.value = ''
  }
}

onMounted(loadConfigOptions)
</script>

<style lang="less" scoped>
.ocr-settings-section { container: settings-services / inline-size; }
.section-description {
  margin: 0 0 12px;
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
</style>

<style lang="less" scoped src="./settings-form.less"></style>
<style lang="less" scoped src="./settings-service-card.less"></style>
