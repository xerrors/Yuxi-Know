<template>
  <section class="feedback-list" aria-labelledby="feedback-list-title">
    <header class="feedback-heading">
      <div>
        <h2 id="feedback-list-title">反馈与改进线索</h2>
        <p>从用户评价和 Agent 的执行经验中，发现值得复盘的流程。</p>
      </div>
      <a-button class="refresh-btn" :loading="loading" @click="reload">
        <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>
        刷新
      </a-button>
    </header>

    <div class="feedback-panel">
      <div class="feedback-filters">
        <div class="filter-field source-field">
          <span id="feedback-source-label">反馈来源</span>
          <a-segmented
            v-model:value="filters.source"
            :options="sourceOptions"
            aria-labelledby="feedback-source-label"
            @change="changeSource"
          />
        </div>
        <div class="filter-field agent-field">
          <label for="feedback-agent">智能体</label>
          <a-select
            id="feedback-agent"
            :value="filters.agent_id"
            :options="agentOptions"
            :loading="agentsLoading"
            show-search
            :filter-option="filterAgentOption"
            @change="selectAgent"
          />
        </div>
        <div v-if="filters.source === 'user'" class="filter-field rating-field">
          <label for="feedback-rating">用户评价</label>
          <a-select id="feedback-rating" v-model:value="filters.rating" :options="ratingOptions" @change="reload" />
        </div>
        <a-button v-if="hasFilters" type="text" class="reset-filters" @click="clearFilters">重置筛选</a-button>
      </div>
      <p v-if="agentsError" class="agent-load-error" role="alert">
        智能体选项加载失败。
        <button type="button" class="text-action" @click="loadAgents">重新加载</button>
      </p>

      <div class="list-caption">
        <span role="status">{{ loading && !items.length ? '正在读取反馈…' : `已加载 ${items.length} 条` }}</span>
        <span>按记录时间 · 最新在前</span>
      </div>
      <div v-if="loading && !items.length" class="feedback-skeleton" aria-label="正在读取反馈" aria-busy="true">
        <a-skeleton v-for="index in 3" :key="index" active :paragraph="{ rows: 2 }" />
      </div>
      <ResourceEmptyState
        v-else-if="!items.length"
        size="compact"
        :icon="error ? AlertCircle : MessageSquare"
        :title="emptyTitle"
        :description="emptyDescription"
      >
        <template #actions>
          <a-button v-if="error" @click="loadPage()">重试读取</a-button>
          <a-button v-else-if="hasFilters" @click="clearFilters">清除筛选</a-button>
        </template>
      </ResourceEmptyState>
      <template v-else>
        <div class="list-columns" aria-hidden="true">
          <span>来源与评价</span><span>反馈内容</span><span>智能体</span><span>记录时间</span><span></span>
        </div>
        <ol class="feedback-records" :aria-busy="loading">
          <li v-for="item in items" :key="item.id" class="feedback-record">
            <span class="feedback-signal" :class="signalClass(item)">
              <component :is="signalIcon(item)" :size="14" aria-hidden="true" />
              {{ signalLabel(item) }}
            </span>
            <p class="record-reason" :class="{ 'no-reason': !item.reason }">{{ item.reason || '未填写补充说明' }}</p>
            <button type="button" class="record-agent" :title="`只看 ${item.agent_name || item.agent_id} 的反馈`" @click="selectAgent(item.agent_id)">
              <FallbackAvatar kind="agent" :seed="item.agent_id" :size="24" decorative />
              <span>{{ item.agent_name || item.agent_id }}</span>
            </button>
            <time class="record-time" :datetime="item.created_at">{{ formatDateTime(item.created_at) }}</time>
            <button type="button" class="record-details text-action" :aria-label="`查看 ${item.agent_name || item.agent_id} 的${signalLabel(item)}详情`" @click="showDetails(item, $event)">
              查看详情 <ChevronRight :size="14" aria-hidden="true" />
            </button>
          </li>
        </ol>
        <div v-if="error" class="page-error" role="alert">
          <AlertCircle :size="16" aria-hidden="true" />
          <span>{{ error }}</span>
          <a-button size="small" @click="loadPage(retryMore)">重试读取</a-button>
        </div>
        <footer class="list-footer">
          <a-button v-if="hasMore && !error" :loading="loading" @click="loadPage(true)">加载更多</a-button>
          <span v-else-if="!hasMore && !error">已显示当前筛选下的全部记录</span>
        </footer>
      </template>
    </div>

    <a-modal
      v-model:open="detailOpen"
      title="反馈详情"
      :width="detailWidth"
      :destroy-on-close="true"
      :wrap-props="{ 'aria-modal': 'true' }"
      :body-style="{ maxHeight: '60vh', overflowY: 'auto' }"
      :after-close="() => detailTrigger?.focus()"
    >
      <template v-if="selected">
        <div class="detail-heading">
          <FallbackAvatar kind="agent" :seed="selected.agent_id" :size="36" decorative />
          <div>
            <strong>{{ selected.agent_name || selected.agent_id }}</strong>
            <span class="feedback-signal" :class="signalClass(selected)">
              <component :is="signalIcon(selected)" :size="14" aria-hidden="true" />
              {{ signalLabel(selected) }}
            </span>
          </div>
        </div>
        <section class="detail-section" aria-labelledby="feedback-content-label">
          <h3 id="feedback-content-label" ref="detailHeading" tabindex="-1">{{ selected.source === 'agent' ? '改进线索' : '补充说明' }}</h3>
          <p class="detail-reason" :class="{ 'no-reason': !selected.reason }">{{ selected.reason || '用户提交了评价，未填写补充说明。' }}</p>
        </section>
        <section class="detail-section" aria-labelledby="feedback-context-label">
          <h3 id="feedback-context-label">关联执行</h3>
          <dl class="detail-metadata">
            <div><dt>记录时间</dt><dd>{{ formatDateTime(selected.created_at) }}</dd></div>
            <div v-if="selected.updated_at !== selected.created_at"><dt>更新时间</dt><dd>{{ formatDateTime(selected.updated_at) }}</dd></div>
            <div><dt>执行状态</dt><dd>{{ runStatusLabels[selected.run_status] || selected.run_status }}</dd></div>
            <div v-for="field in contextFields" :key="field.key" class="identifier"><dt>{{ field.label }}</dt><dd><code>{{ selected[field.key] }}</code></dd></div>
          </dl>
        </section>
      </template>
      <template #footer>
        <p v-if="selected && sessionErrors[selected.session_id]" class="session-error" role="alert">{{ sessionErrors[selected.session_id] }}</p>
        <div class="detail-footer">
          <span>原会话沿用现有访问权限。</span>
          <a-button v-if="selected" :loading="openingSession === selected.session_id" :disabled="!!openingSession" @click="openSession(selected)">
            查看原会话 <ArrowUpRight :size="14" aria-hidden="true" />
          </a-button>
        </div>
      </template>
    </a-modal>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import { useWindowSize } from '@vueuse/core'
import { useRouter } from 'vue-router'
import { AlertCircle, ArrowUpRight, ChevronRight, Lightbulb, MessageSquare, RefreshCw, ThumbsDown, ThumbsUp } from '@lucide/vue'
import { agentApi } from '@/apis'
import { feedbackApi } from '@/apis/feedback_api'
import { formatDateTime } from '@/shared/lib/time'
import FallbackAvatar from '@/shared/ui/FallbackAvatar.vue'
import ResourceEmptyState from '@/shared/ui/ResourceEmptyState.vue'

const sourceOptions = [{ value: '', label: '全部' }, { value: 'user', label: '用户评价' }, { value: 'agent', label: 'Agent 标记' }]
const ratingOptions = [{ value: '', label: '全部评价' }, { value: 'like', label: '点赞' }, { value: 'dislike', label: '点踩' }]
const filters = reactive({ source: '', rating: '', agent_id: '' })
const items = ref([])
const loading = ref(false)
const error = ref('')
const hasMore = ref(false)
const after = ref(null)
const retryMore = ref(false)
const agents = ref([])
const agentsLoading = ref(false)
const agentsError = ref(false)
const router = useRouter()
const openingSession = ref(null)
const sessionErrors = reactive({})
const selected = ref(null)
const detailOpen = ref(false)
const detailHeading = ref(null)
const { width } = useWindowSize()
const detailWidth = computed(() => width.value < 640 ? '100%' : 560)
const hasFilters = computed(() => !!(filters.source || filters.rating || filters.agent_id))
const emptyTitle = computed(() => {
  if (error.value) return '暂时无法读取反馈'
  return hasFilters.value ? '没有符合筛选条件的反馈' : '还没有反馈记录'
})
const emptyDescription = computed(() => {
  if (error.value) return error.value
  if (hasFilters.value) return '试试切换来源、智能体，或清除当前筛选。'
  return '用户对回答点赞或点踩、Agent 主动记录改进线索后，会显示在这里。'
})
const agentOptions = computed(() => {
  const options = agents.value.map((agent) => ({ value: agent.agent_id, label: agent.name || agent.agent_id }))
  if (filters.agent_id && !options.some((option) => option.value === filters.agent_id)) {
    const name = items.value.find((item) => item.agent_id === filters.agent_id)?.agent_name
    options.push({ value: filters.agent_id, label: name || filters.agent_id })
  }
  return [{ value: '', label: '全部智能体' }, ...options]
})
const contextFields = [{ key: 'agent_id', label: 'Agent ID' }, { key: 'session_id', label: 'Session ID' }, { key: 'turn_id', label: 'Turn ID' }, { key: 'run_id', label: 'Run ID' }, { key: 'id', label: '记录 ID' }]
const runStatusLabels = { pending: '待执行', running: '执行中', cancel_requested: '正在取消', interrupted: '已中断', completed: '已完成', failed: '执行失败', cancelled: '已取消', yielded: '已交接' }
let generation = 0
let detailTrigger = null
let detailViewRevision = 0
watch([detailOpen, detailHeading], ([open, heading]) => { if (open) heading?.focus() }, { flush: 'post' })

/** 离开列表时关闭详情，阻止迟到的会话查询接管导航。 */
function closeOnLeave() {
  detailViewRevision += 1
  detailOpen.value = false
  detailTrigger = null
}
onDeactivated(closeOnLeave)
onBeforeUnmount(closeOnLeave)

function signalLabel(item) {
  if (item.source === 'agent') return 'Agent 标记'
  return item.rating === 'like' ? '用户点赞' : '用户点踩'
}
function signalIcon(item) {
  if (item.source === 'agent') return Lightbulb
  return item.rating === 'like' ? ThumbsUp : ThumbsDown
}
function signalClass(item) {
  return item.source === 'agent' ? 'signal-agent' : `signal-${item.rating}`
}
function filterAgentOption(input, option) {
  return `${option.label} ${option.value}`.toLowerCase().includes(input.toLowerCase())
}
async function loadAgents() {
  agentsLoading.value = true
  agentsError.value = false
  try {
    agents.value = (await agentApi.getAgents()).agents
  } catch {
    agentsError.value = true
  } finally {
    agentsLoading.value = false
  }
}
async function loadPage(more = false) {
  if (more && loading.value) return
  const current = ++generation
  retryMore.value = more
  loading.value = true
  error.value = ''
  try {
    const page = await feedbackApi.list({ ...filters, after: more ? after.value : null })
    if (current !== generation) return
    items.value = more ? [...items.value, ...page.items] : page.items
    hasMore.value = page.has_more
    after.value = page.last_id
  } catch (cause) {
    if (current === generation) error.value = cause.message || '反馈读取失败，请重试'
  } finally {
    if (current === generation) loading.value = false
  }
}
function reload() {
  items.value = []
  hasMore.value = false
  return loadPage()
}
function changeSource() {
  filters.rating = ''
  return reload()
}
function selectAgent(value) {
  filters.agent_id = value || ''
  return reload()
}
function clearFilters() {
  Object.assign(filters, { source: '', rating: '', agent_id: '' })
  return reload()
}
function showDetails(item, event) {
  detailTrigger = event.currentTarget
  selected.value = item
  detailOpen.value = true
}
async function openSession(item) {
  if (openingSession.value) return
  const revision = detailViewRevision
  openingSession.value = item.session_id
  delete sessionErrors[item.session_id]
  try {
    await agentApi.getPublicThread(item.session_id)
    if (revision !== detailViewRevision) return
    await router.push({ name: 'AgentCompWithThreadId', params: { thread_id: item.session_id } })
  } catch (cause) {
    if (revision === detailViewRevision) sessionErrors[item.session_id] = cause.status === 404 ? '无权查看原会话' : (cause.message || '原会话读取失败，请重试')
  } finally {
    openingSession.value = null
  }
}
onMounted(() => { void reload(); void loadAgents() })
</script>

<style scoped lang="less">
.feedback-list { padding: var(--page-padding); }
.feedback-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  h2 { margin: 0; color: var(--gray-900); font-size: 18px; font-weight: 600; line-height: 1.4; }
  p { margin: 6px 0 0; color: var(--gray-600); font-size: 13px; line-height: 1.6; }
}
.feedback-panel { container: feedback-panel / inline-size; border: 1px solid var(--gray-150); border-radius: 8px; background: var(--gray-0); overflow: hidden; }
.feedback-filters { display: flex; align-items: flex-end; flex-wrap: wrap; gap: 16px; padding: 20px; }
.filter-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  > span, > label { font-size: 12px; color: var(--gray-600); }
}
.agent-field { width: 220px; }
.rating-field { width: 132px; }
.agent-load-error { margin: 0 20px 12px; color: var(--color-error-700); font-size: 13px; }
.list-caption { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--gray-150); color: var(--gray-600); font-size: 12px; }
.list-columns, .feedback-record { display: grid; grid-template-columns: 116px minmax(180px, 1fr) 160px 132px 88px; align-items: start; gap: 16px; padding: 16px 20px; }
.list-columns { padding-block: 10px; background: var(--gray-25); border-top: 1px solid var(--gray-150); color: var(--gray-600); font-size: 12px; }
.feedback-records { list-style: none; padding: 0; margin: 0; }
.feedback-record { border-top: 1px solid var(--gray-150); min-height: 104px; }
.feedback-signal {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 6px;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.4;
  &.signal-agent { background: var(--main-50); color: var(--main-700); }
  &.signal-like { background: var(--color-success-50); color: var(--color-success-900); }
  &.signal-dislike { background: var(--color-warning-50); color: var(--color-warning-900); }
}
.record-reason {
  margin: 0;
  color: var(--gray-800);
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}
.no-reason { color: var(--gray-600); }
.record-agent {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--gray-700);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  &:hover { color: var(--main-700); }
}
.record-time { font-size: 12px; color: var(--gray-600); line-height: 28px; font-variant-numeric: tabular-nums; }
.text-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px 0;
  min-height: 28px;
  border: 0;
  background: transparent;
  color: var(--main-700);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  &:hover { text-decoration: underline; }
}
.text-action:focus-visible, .record-agent:focus-visible { outline: 2px solid var(--main-color); outline-offset: 3px; border-radius: 4px; }
.list-footer { display: flex; justify-content: center; align-items: center; min-height: 64px; padding: 16px; border-top: 1px solid var(--gray-150); color: var(--gray-600); font-size: 12px; }
.page-error { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 16px 20px; padding: 12px; border-radius: 6px; background: var(--color-error-50); color: var(--color-error-700); font-size: 13px; span { flex: 1; } }
.feedback-skeleton { padding: 0 20px; :deep(.ant-skeleton) { padding: 20px 0; border-top: 1px solid var(--gray-150); } }
.detail-heading { display: flex; align-items: center; gap: 12px; margin-bottom: 28px; > div { display: grid; gap: 8px; min-width: 0; } strong { color: var(--gray-900); font-size: 16px; overflow-wrap: anywhere; } }
.detail-section { margin-top: 24px; h3 { margin: 0 0 12px; color: var(--gray-900); font-size: 13px; font-weight: 600; } }
.detail-reason { margin: 0; color: var(--gray-800); font-size: 14px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.detail-metadata { margin: 0; > div { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 16px; padding: 8px 0; font-size: 12px; line-height: 1.6; } dt { color: var(--gray-600); } dd { margin: 0; color: var(--gray-800); overflow-wrap: anywhere; } .identifier { code { font-size: 12px; } } }
.detail-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; span { color: var(--gray-600); font-size: 12px; } :deep(.ant-btn) { display: inline-flex; align-items: center; gap: 6px; } }
.session-error { margin: 0 0 12px; color: var(--color-error-700); font-size: 13px; }
@container feedback-panel (max-width: 780px) {
  .list-columns { display: none; }
  .feedback-record { grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: 'signal time' 'reason reason' 'agent details'; gap: 12px; }
  .feedback-record > .feedback-signal { grid-area: signal; }
  .record-reason { grid-area: reason; }
  .record-agent { grid-area: agent; }
  .record-time { grid-area: time; }
  .record-details { grid-area: details; }
}
@media (max-width: 640px) {
  .feedback-heading { gap: 12px; }
  .feedback-filters { gap: 12px; padding: 16px; }
  .source-field { width: 100%; :deep(.ant-segmented) { align-self: flex-start; max-width: 100%; } }
  .agent-field { flex: 1; min-width: 160px; }
  .list-caption, .feedback-record { padding-inline: 16px; }
  .record-reason { -webkit-line-clamp: 4; }
  .detail-metadata > div { grid-template-columns: 76px minmax(0, 1fr); gap: 8px; }
}
@media (prefers-reduced-motion: reduce) { .feedback-skeleton :deep(.ant-skeleton-content .ant-skeleton-title), .feedback-skeleton :deep(.ant-skeleton-content .ant-skeleton-paragraph > li) { animation: none; } }
</style>
