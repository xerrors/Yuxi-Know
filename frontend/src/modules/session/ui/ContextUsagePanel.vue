<template>
  <section v-if="usage" class="state-section token-usage-section" aria-label="上下文使用情况">
    <button
      type="button"
      class="token-usage-context-card"
      :aria-expanded="expanded"
      aria-controls="token-usage-details"
      @click="expanded = !expanded"
    >
      <div class="token-usage-card-main-row">
        <strong class="token-usage-card-percent">{{ tokenUsageHeaderPercentLabel }}</strong>
        <span class="token-usage-card-meta">
          <span class="token-usage-card-title">上下文占用</span>
          <span class="token-usage-card-summary">{{ tokenUsageStackHeadLabel }}</span>
          <ChevronDown
            :size="14"
            class="state-section-chevron"
            :class="{
              'is-collapsed': !expanded
            }"
          />
        </span>
      </div>

      <span
        class="token-usage-context-track"
        role="progressbar"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-valuenow="tokenUsageContextRatio === null ? undefined : tokenUsageContextRatio * 100"
        :aria-valuetext="tokenUsageContextAriaLabel"
      >
        <span
          class="token-usage-context-fill"
          :class="tokenUsageContextTone"
          :style="{ width: tokenUsageContextPercent }"
        ></span>
      </span>

      <span v-if="hasTokenUsageMetrics" class="token-usage-card-metrics">
        <span v-if="tokenUsageThreadTotalLabel !== null">
          <small title="已上报模型调用的输入与输出 Token 总量">累计模型用量</small>
          <strong>{{ tokenUsageThreadTotalLabel }}</strong>
        </span>
        <span v-if="tokenUsageCacheHitLabel !== null">
          <small>累计缓存命中率</small>
          <strong>{{ tokenUsageCacheHitLabel }}</strong>
        </span>
      </span>
    </button>
    <div class="state-collapse-panel" :class="{ 'is-expanded': expanded }">
      <div class="state-collapse-inner">
        <div id="token-usage-details" class="token-usage-details">
          <div v-if="tokenUsageModelItems.length" class="token-usage-model-list">
            <article
              v-for="model in tokenUsageModelItems"
              :key="model.key"
              class="token-usage-model-item"
            >
              <header class="token-usage-model-header">
                <div>
                  <strong>{{ model.name }}</strong>
                  <span v-if="model.responseModel">响应 {{ model.responseModel }}</span>
                </div>
                <span>{{ model.callCount }} 次调用</span>
              </header>
              <div
                class="token-usage-model-stats"
                :class="{ 'has-reasoning': Boolean(model.reasoning) }"
              >
                <div class="is-io">
                  <span>输入 / 输出</span>
                  <strong>{{ model.io }}</strong>
                </div>
                <div v-if="model.cache" class="is-cache">
                  <span>缓存</span>
                  <strong>{{ model.cache }}</strong>
                </div>
                <div v-if="model.reasoning" class="is-reasoning">
                  <span>推理</span>
                  <strong>{{ model.reasoning }}</strong>
                </div>
              </div>
            </article>
          </div>

          <div class="token-usage-composition">
            <div class="token-usage-detail-heading">
              <span>最近上下文构成</span>
              <button
                type="button"
                class="context-compression-btn"
                :title="contextCompressionButtonLabel"
                :aria-label="contextCompressionButtonLabel"
                :aria-busy="compressing"
                :disabled="compressing || compressionDisabled"
                @click="emit('compress')"
              >
                <LoaderCircle
                  v-if="compressing"
                  :size="14"
                  class="is-spinning"
                  aria-hidden="true"
                />
                <ListCollapse v-else :size="14" aria-hidden="true" />
              </button>
            </div>
            <div class="token-usage-stack-track" aria-label="Token 构成">
              <div
                v-for="segment in tokenUsageBarSegments"
                :key="segment.key"
                class="token-usage-stack-segment"
                :class="segment.tone"
                :style="{ width: segment.percent }"
                :title="`${segment.label}: ${segment.valueLabel}`"
              ></div>
            </div>
            <div class="token-usage-composition-list">
              <div
                v-for="segment in tokenUsageSegments"
                :key="segment.key"
                class="token-usage-composition-item"
              >
                <span><i :class="segment.tone"></i>{{ segment.label }}</span>
                <strong>{{ segment.valueLabel }}</strong>
              </div>
            </div>
          </div>

          <div v-if="tokenUsageSupplementRows.length" class="token-usage-supplement">
            <div
              v-for="item in tokenUsageSupplementRows"
              :key="item.key"
              class="token-usage-supplement-row"
            >
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>

          <p v-if="shouldSuggestContextCompression" class="context-compression-warning">
            当前上下文已达到压缩阈值的
            {{ tokenUsageHeaderPercentLabel }}，建议先压缩再开始下一次运行。
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ChevronDown, LoaderCircle, ListCollapse } from '@lucide/vue'
import {
  formatTokenCount,
  toFiniteNumber,
  getContextUsageSegments,
  resolveContextUsageSummary,
  shouldSuggestContextCompression as isContextCompressionSuggested
} from '../model/contextUsage'

const props = defineProps({
  usage: { type: Object, default: null },
  compressing: { type: Boolean, default: false },
  compressionDisabled: { type: Boolean, default: false }
})
const emit = defineEmits(['compress'])
const expanded = ref(false)
const currentTokenUsage = computed(() => props.usage)
const summary = computed(() => resolveContextUsageSummary(props.usage))
const tokenUsageSegments = computed(() => getContextUsageSegments(props.usage))
const tokenUsageStackTotal = computed(() => summary.value.stackTotal)
const tokenUsagePressureTotal = computed(() => summary.value.usedTokens)
const tokenUsageStackLimit = computed(() => summary.value.limitTokens)
const tokenUsageContextRatio = computed(() => summary.value.ratio)
const formatTokenRatio = (value) => {
  const numeric = toFiniteNumber(value)
  return numeric === null ? '未上报' : `${Math.round(Math.max(0, Math.min(numeric, 1)) * 100)}%`
}
const shouldSuggestContextCompression = computed(() =>
  isContextCompressionSuggested(tokenUsageContextRatio.value)
)
const contextCompressionButtonLabel = computed(() =>
  props.compressing ? '正在压缩…' : '压缩上下文'
)
const tokenUsageHeaderPercentLabel = computed(() => {
  if (tokenUsageContextRatio.value === null) return '--'
  const percent = tokenUsageContextRatio.value * 100
  if (percent > 0 && percent < 1) return '<1%'
  return `${Math.round(percent)}%`
})
const tokenUsageContextPercent = computed(() => {
  return tokenUsageContextRatio.value === null
    ? '0%'
    : `${(tokenUsageContextRatio.value * 100).toFixed(2)}%`
})
const tokenUsageContextTone = computed(() => {
  const ratio = tokenUsageContextRatio.value
  if (ratio === null) return ''
  if (ratio >= 0.9) return 'is-danger'
  if (ratio >= 0.75) return 'is-warning'
  return ''
})
const tokenUsageContextAriaLabel = computed(() => {
  if (tokenUsageContextRatio.value === null) {
    return `上下文上限未知，当前估算 ${formatTokenCount(tokenUsagePressureTotal.value)}`
  }
  return `上下文占用 ${tokenUsageHeaderPercentLabel.value}`
})
const tokenUsageStackHeadLabel = computed(() => {
  const summaryTriggerTokens = toFiniteNumber(currentTokenUsage.value?.summary_trigger_tokens)
  if (summaryTriggerTokens && summaryTriggerTokens > 0) {
    return `${formatTokenCount(tokenUsagePressureTotal.value)} / ${formatTokenCount(summaryTriggerTokens)}`
  }
  return formatTokenCount(tokenUsagePressureTotal.value)
})
const tokenUsageThreadTotal = computed(() => {
  const total = toFiniteNumber(currentTokenUsage.value?.thread?.total?.total_tokens)
  return total === null ? null : Math.max(total, 0)
})
const tokenUsageThreadTotalLabel = computed(() => {
  if (!tokenUsageThreadTotal.value) return null
  return formatTokenCount(tokenUsageThreadTotal.value)
})
const tokenUsageCacheHitLabel = computed(() => {
  const models = currentTokenUsage.value?.thread?.models
  if (!models || typeof models !== 'object' || Object.keys(models).length === 0) return null
  let observedInputTokens = 0
  let cacheReadTokens = 0
  let observedCalls = 0
  Object.values(models).forEach((bucket) => {
    if (!bucket || typeof bucket !== 'object') return
    observedInputTokens += Math.max(toFiniteNumber(bucket.cache_observed_input_tokens) || 0, 0)
    cacheReadTokens += Math.max(toFiniteNumber(bucket.cache_read_input_tokens) || 0, 0)
    observedCalls += Math.max(toFiniteNumber(bucket.cache_observed_call_count) || 0, 0)
  })
  if (observedCalls <= 0 || observedInputTokens <= 0) return null
  return formatTokenRatio(cacheReadTokens / observedInputTokens)
})
// 旧会话没有累计统计，指标都为 null 时隐藏整个指标行
const hasTokenUsageMetrics = computed(
  () => tokenUsageThreadTotalLabel.value !== null || tokenUsageCacheHitLabel.value !== null
)
const tokenUsageBarSegments = computed(() => {
  const limit = tokenUsageStackLimit.value || Math.max(tokenUsageStackTotal.value, 1)
  let remaining = limit
  return tokenUsageSegments.value
    .filter((segment) => segment.key !== 'cut')
    .map((segment) => {
      const value = Math.min(segment.value, Math.max(remaining, 0))
      remaining -= value
      return {
        ...segment,
        percent: `${Math.max(0, Math.min((value / limit) * 100, 100)).toFixed(2)}%`
      }
    })
    .filter((segment) => segment.value > 0 && segment.percent !== '0.00%')
})
const tokenUsageModelItems = computed(() => {
  const usage = currentTokenUsage.value
  if (!usage) return []
  const threadUsage = usage.thread && typeof usage.thread === 'object' ? usage.thread : null
  const models =
    threadUsage?.models && typeof threadUsage.models === 'object' ? threadUsage.models : {}
  return Object.entries(models).map(([bucketKey, bucket]) => {
    const model = bucket?.model && typeof bucket.model === 'object' ? bucket.model : {}
    const modelUsage = bucket?.usage && typeof bucket.usage === 'object' ? bucket.usage : {}
    const responseModelIds = Array.isArray(model.response_model_ids)
      ? [...new Set(model.response_model_ids.filter((item) => typeof item === 'string' && item))]
      : []
    const responseModels = responseModelIds.filter((item) => item !== model.configured_model_id)
    const cacheRatio = toFiniteNumber(bucket?.cache_hit_ratio)
    const cacheObservedCalls = toFiniteNumber(bucket?.cache_observed_call_count) || 0
    const reasoning = toFiniteNumber(modelUsage.output_token_details?.reasoning)
    return {
      key: bucketKey,
      name: model.configured_model_spec || bucketKey,
      responseModel:
        responseModels.length > 1
          ? `${responseModels[0]} 等 ${responseModels.length} 个模型`
          : responseModels[0] || '',
      callCount: Math.max(toFiniteNumber(bucket?.model_call_count) || 0, 0),
      io: `${formatTokenCount(modelUsage.input_tokens)} / ${formatTokenCount(modelUsage.output_tokens)}`,
      cache:
        cacheObservedCalls === 0
          ? ''
          : cacheRatio === null
            ? formatTokenCount(bucket?.cache_read_input_tokens)
            : `${formatTokenCount(bucket?.cache_read_input_tokens)} · ${formatTokenRatio(cacheRatio)}`,
      reasoning: reasoning === null ? '' : formatTokenCount(reasoning)
    }
  })
})
const tokenUsageSupplementRows = computed(() => {
  const usage = currentTokenUsage.value
  if (!usage) return []
  const rows = []
  const latest = usage.latest && typeof usage.latest === 'object' ? usage.latest : null

  if (latest?.usage && typeof latest.usage === 'object') {
    rows.push({
      key: 'latestUsage',
      label: '最近调用',
      value: `输入 ${formatTokenCount(latest.usage.input_tokens)} · 输出 ${formatTokenCount(latest.usage.output_tokens)}`
    })
  }
  return rows
})
</script>

<style scoped lang="less">
.state-section-chevron {
  flex-shrink: 0;
  color: var(--gray-400);
  transition:
    transform 0.22s cubic-bezier(0.16, 1, 0.3, 1),
    color 0.18s ease;

  &.is-collapsed {
    transform: rotate(-90deg);
  }
}

.state-collapse-panel {
  display: grid;
  grid-template-rows: 0fr;
  transition:
    grid-template-rows 0.24s cubic-bezier(0.16, 1, 0.3, 1),
    visibility 0.24s ease;
  visibility: hidden;
  min-width: 0;

  &.is-expanded {
    grid-template-rows: 1fr;
    visibility: visible;
  }
}

.state-collapse-inner {
  overflow: hidden;
  min-height: 0;
  opacity: 0;
  transform: translateY(-4px);
  transition:
    opacity 0.2s ease,
    transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.state-collapse-panel.is-expanded .state-collapse-inner {
  opacity: 1;
  transform: translateY(0);
}

.token-usage-section {
  display: flex;
  flex-direction: column;

  .state-collapse-panel.is-expanded {
    margin-top: 8px;
  }
}

.token-usage-context-card {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--gray-150);
  border-radius: 10px;
  background: var(--gray-0);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background 0.18s ease;

  &:hover {
    border-color: var(--gray-200);
    background: var(--gray-10);

    .token-usage-card-title,
    .token-usage-card-summary,
    .state-section-chevron {
      color: var(--gray-800);
    }
  }

  &:focus-visible {
    outline: 2px solid var(--main-200);
    outline-offset: 2px;
  }
}

.token-usage-card-main-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.token-usage-card-percent {
  display: block;
  color: var(--gray-900);
  font-size: 18px;
  font-weight: 600;
  font-variant-numeric: proportional-nums;
  line-height: 1.1;
}

.token-usage-card-meta {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.token-usage-card-title {
  font-size: 11px;
  font-weight: 500;
  color: var(--gray-500);
  white-space: nowrap;
}

.token-usage-card-summary {
  min-width: 0;
  overflow: hidden;
  color: var(--gray-500);
  font-size: 11px;
  font-variant-numeric: proportional-nums;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.token-usage-context-track {
  width: 100%;
  height: 5px;
  display: block;
  overflow: hidden;
  border-radius: 999px;
  background: var(--gray-100);
}

.token-usage-context-fill {
  display: block;
  height: 100%;
  min-width: 2px;
  border-radius: inherit;
  background: var(--main-500);
  transition:
    width 0.2s ease,
    background-color 0.2s ease;

  &.is-warning {
    background: var(--color-warning-500);
  }

  &.is-danger {
    background: var(--color-error-500);
  }
}

.token-usage-card-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.token-usage-card-metrics > span {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.token-usage-card-metrics > span + span {
  padding-left: 12px;
  border-left: 1px solid var(--gray-150);
}

.token-usage-card-metrics small {
  color: var(--gray-500);
  font-size: 11px;
  line-height: 1.4;
}

.token-usage-card-metrics strong {
  overflow: hidden;
  color: var(--gray-900);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: proportional-nums;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.token-usage-details {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0 2px;
}

.token-usage-model-list {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--gray-150);
  border-radius: 9px;
  overflow: hidden;
}

.token-usage-model-item {
  padding: 11px;
  background: var(--gray-0);
  border-bottom: 1px solid var(--gray-150);
}

.token-usage-model-item:last-child {
  border-bottom: 0;
}

.token-usage-model-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.token-usage-model-header > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.token-usage-model-header strong {
  overflow: hidden;
  color: var(--gray-900);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.token-usage-model-header span {
  font-size: 11px;
  color: var(--gray-500);
}

.token-usage-model-header > span {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--gray-50);
}

.token-usage-model-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;

  &.has-reasoning {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.token-usage-model-stats > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.token-usage-model-stats span {
  color: var(--gray-500);
  font-size: 10px;
}

.token-usage-model-stats strong {
  overflow-wrap: anywhere;
  color: var(--gray-900);
  font-size: 12px;
  font-weight: 600;
  font-variant-numeric: proportional-nums;
}

.token-usage-composition {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 11px;
  border: 1px solid var(--gray-150);
  border-radius: 9px;
  background: var(--gray-0);
}

.token-usage-detail-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--gray-600);
  font-size: 11px;
  font-weight: 600;
}

.token-usage-stack-track {
  display: flex;
  gap: 1px;
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--gray-100);
}

.token-usage-stack-segment {
  height: 100%;
  min-width: 2px;
  transition: width 0.2s ease;
}

.token-usage-composition-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 12px;
}

.token-usage-composition-item {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  color: var(--gray-500);
  font-size: 11px;
}

.token-usage-composition-item > span {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.token-usage-composition-item strong {
  color: var(--gray-800);
  font-weight: 600;
  font-variant-numeric: proportional-nums;
}

.token-usage-composition-item i {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 2px;
  background: var(--gray-300);
}

.token-usage-stack-segment,
.token-usage-composition-item i {
  &.is-cut {
    background-color: var(--main-500);
    background-image: repeating-linear-gradient(
      135deg,
      var(--main-30) 0,
      var(--main-30) 1px,
      transparent 1px,
      transparent 4px
    );
  }

  &.is-messages {
    background: var(--chart-palette-1);
  }

  &.is-tool-messages {
    background: var(--chart-palette-6);
  }

  &.is-summary {
    background: var(--chart-palette-5);
  }

  &.is-system {
    background: var(--chart-palette-2);
  }

  &.is-tools {
    background: var(--chart-palette-3);
  }

  &.is-overhead {
    background: var(--gray-300);
  }
}

.token-usage-supplement {
  display: flex;
  flex-direction: column;
  padding: 0 4px;
}

.token-usage-supplement-row {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 0;
  border-bottom: 1px solid var(--gray-100);
  font-size: 11px;
  color: var(--gray-500);
}

.token-usage-supplement-row:last-child {
  border-bottom: 0;
}

.token-usage-supplement-row span,
.token-usage-supplement-row strong {
  min-width: 0;
}

.token-usage-supplement-row strong {
  color: var(--gray-800);
  font-weight: 600;
  font-variant-numeric: proportional-nums;
  text-align: right;
}

.context-compression-warning {
  margin: 0;
  color: var(--color-warning-700);
  font-size: 11px;
  line-height: 1.55;
}

.context-compression-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-500);
  cursor: pointer;

  &:hover:not(:disabled) {
    background: var(--gray-100);
    color: var(--main-700);
  }

  &:focus-visible {
    outline: 2px solid var(--main-200);
    outline-offset: 2px;
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.55;
  }

  .is-spinning {
    animation: spin 1s linear infinite;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
@media (prefers-reduced-motion: reduce) {
  .token-usage-context-fill,
  .token-usage-stack-segment,
  .state-section-chevron,
  .state-collapse-panel,
  .state-collapse-inner {
    transition: none;
  }
}
</style>
