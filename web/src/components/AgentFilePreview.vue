<template>
  <div class="agent-file-preview" :class="[containerClass, { 'is-full-height': fullHeight }]">
    <div v-if="showHeader" class="preview-header">
      <div class="file-title">
        <component
          :is="getFileIcon(filePath)"
          :style="{ color: getFileIconColor(filePath), fontSize: '18px' }"
        />
        <span class="file-path-title">{{ filePath }}</span>
      </div>
      <div class="modal-actions">
        <div v-if="isHtmlFile" class="preview-mode-switch">
          <button
            class="preview-mode-btn"
            :class="{ active: htmlPreviewMode === 'render' }"
            @click="htmlPreviewMode = 'render'"
            title="预览"
          >
            <Globe :size="16" />
          </button>
          <button
            class="preview-mode-btn"
            :class="{ active: htmlPreviewMode === 'source' }"
            @click="htmlPreviewMode = 'source'"
            title="源码"
          >
            <Code2 :size="16" />
          </button>
        </div>
        <button
          v-if="showDownload && file"
          class="modal-action-btn"
          @click="$emit('download', file)"
          title="下载"
        >
          <Download :size="18" />
        </button>
        <button
          v-if="showFullscreen && file"
          class="modal-action-btn"
          @click="openFullscreenPreview"
          title="全屏预览"
        >
          <Maximize2 :size="18" />
        </button>
        <button v-if="showClose" class="modal-action-btn" @click="$emit('close')" title="关闭">
          <X :size="18" />
        </button>
      </div>
    </div>

    <div class="file-content" :class="contentClass">
      <template v-if="file?.previewType === 'image' && file?.previewUrl">
        <div class="image-preview-wrapper">
          <img :src="file.previewUrl" :alt="filePath" class="image-preview" />
        </div>
      </template>
      <template v-else-if="file?.previewType === 'pdf' && file?.previewUrl">
        <iframe :src="file.previewUrl" class="pdf-preview" :title="filePath" />
      </template>
      <template v-else-if="isHtmlFile && htmlPreviewMode === 'render'">
        <iframe
          :key="`embedded-${htmlPreviewRenderKey}`"
          class="html-preview"
          :srcdoc="formatContent(file?.content)"
          :title="filePath"
          sandbox="allow-scripts"
        />
      </template>
      <template v-else-if="isMarkdown">
        <MdPreview
          class="flat-md-preview"
          :modelValue="formatContent(file?.content)"
          :theme="theme"
          previewTheme="github"
        />
      </template>
      <template v-else-if="file?.supported === false">
        <div class="unsupported-preview">
          {{ file?.message || '当前文件暂不支持预览，请下载后查看' }}
        </div>
      </template>
      <template v-else>
        <pre v-if="Array.isArray(file?.content)" class="file-content-pre">{{
          formatContent(file.content)
        }}</pre>
        <pre
          v-else-if="isCodePreview && typeof file?.content === 'string'"
          :class="['file-content-pre', 'code-highlight', codeThemeClass]"
        ><code class="hljs" v-html="highlightedCodeContent"></code></pre>
        <pre v-else-if="typeof file?.content === 'string'" class="file-content-pre">{{
          file.content
        }}</pre>
        <pre v-else>{{ JSON.stringify(file, null, 2) }}</pre>
      </template>
    </div>

    <Teleport to="body">
      <div v-if="fullscreenPreviewVisible && file" class="fullscreen-preview-overlay">
        <div class="fullscreen-preview-actions">
          <div v-if="isHtmlFile" class="preview-mode-switch fullscreen-preview-switch">
            <button
              class="preview-mode-btn"
              :class="{ active: htmlPreviewMode === 'render' }"
              @click="htmlPreviewMode = 'render'"
              title="预览"
            >
              <Globe :size="16" />
            </button>
            <button
              class="preview-mode-btn"
              :class="{ active: htmlPreviewMode === 'source' }"
              @click="htmlPreviewMode = 'source'"
              title="源码"
            >
              <Code2 :size="16" />
            </button>
          </div>
          <button
            v-if="showDownload && file"
            class="modal-action-btn fullscreen-action-btn"
            @click="$emit('download', file)"
            title="下载"
          >
            <Download :size="18" />
          </button>
          <button
            class="modal-action-btn fullscreen-action-btn"
            @click="closeFullscreenPreview"
            title="关闭"
          >
            <X :size="18" />
          </button>
        </div>
        <div class="fullscreen-preview-content">
          <div class="file-content fullscreen-file-content">
            <template v-if="file?.previewType === 'image' && file?.previewUrl">
              <div class="image-preview-wrapper fullscreen-image-preview-wrapper">
                <img :src="file.previewUrl" :alt="filePath" class="image-preview" />
              </div>
            </template>
            <template v-else-if="file?.previewType === 'pdf' && file?.previewUrl">
              <iframe
                :src="file.previewUrl"
                class="pdf-preview fullscreen-embed-preview"
                :title="filePath"
              />
            </template>
            <template v-else-if="isHtmlFile && htmlPreviewMode === 'render'">
              <iframe
                :key="`fullscreen-${htmlPreviewRenderKey}`"
                class="html-preview fullscreen-embed-preview"
                :srcdoc="formatContent(file?.content)"
                :title="filePath"
                sandbox="allow-scripts"
              />
            </template>
            <template v-else-if="isMarkdown">
              <MdPreview
                class="flat-md-preview"
                :modelValue="formatContent(file?.content)"
                :theme="theme"
                previewTheme="github"
              />
            </template>
            <template v-else-if="file?.supported === false">
              <div class="unsupported-preview fullscreen-unsupported-preview">
                {{ file?.message || '当前文件暂不支持预览，请下载后查看' }}
              </div>
            </template>
            <template v-else>
              <pre v-if="Array.isArray(file?.content)" class="file-content-pre">{{
                formatContent(file.content)
              }}</pre>
              <pre
                v-else-if="isCodePreview && typeof file?.content === 'string'"
                :class="['file-content-pre', 'code-highlight', codeThemeClass]"
              ><code class="hljs" v-html="highlightedCodeContent"></code></pre>
              <pre v-else-if="typeof file?.content === 'string'" class="file-content-pre">{{
                file.content
              }}</pre>
              <pre v-else>{{ JSON.stringify(file, null, 2) }}</pre>
            </template>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { Code2, Download, Globe, Maximize2, X } from 'lucide-vue-next'
import { MdPreview } from 'md-editor-v3'
import hljs from 'highlight.js/lib/common'
import 'md-editor-v3/lib/preview.css'
import { useThemeStore } from '@/stores/theme'
import { getFileIcon, getFileIconColor } from '@/utils/file_utils'
import { getCodeLanguageByPath, isHtmlPreview, isMarkdownPreview } from '@/utils/file_preview'

const props = defineProps({
  file: {
    type: Object,
    default: null
  },
  filePath: {
    type: String,
    default: ''
  },
  showHeader: {
    type: Boolean,
    default: true
  },
  showDownload: {
    type: Boolean,
    default: true
  },
  showClose: {
    type: Boolean,
    default: false
  },
  showFullscreen: {
    type: Boolean,
    default: false
  },
  fullHeight: {
    type: Boolean,
    default: false
  },
  containerClass: {
    type: [String, Array, Object],
    default: ''
  },
  contentClass: {
    type: [String, Array, Object],
    default: ''
  }
})

defineEmits(['close', 'download'])

const themeStore = useThemeStore()
const theme = computed(() => (themeStore.isDark ? 'dark' : 'light'))
const htmlPreviewMode = ref('render')
const fullscreenPreviewVisible = ref(false)
const htmlPreviewRenderKey = ref(0)

const isMarkdown = computed(() => isMarkdownPreview(props.filePath, props.file?.previewType))
const isHtmlFile = computed(
  () =>
    props.file?.previewType === 'text' &&
    typeof props.file?.content === 'string' &&
    isHtmlPreview(props.filePath)
)
const codeThemeClass = computed(() => (themeStore.isDark ? 'hljs-theme-dark' : 'hljs-theme-light'))
const codeLanguage = computed(() => getCodeLanguageByPath(props.filePath))
const isCodePreview = computed(
  () =>
    props.file?.previewType === 'text' &&
    typeof props.file?.content === 'string' &&
    !isHtmlFile.value &&
    Boolean(codeLanguage.value)
)

const escapeHtml = (content) =>
  String(content)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

const highlightedCodeContent = computed(() => {
  const content = props.file?.content
  if (!isCodePreview.value || typeof content !== 'string') {
    return ''
  }

  try {
    if (codeLanguage.value) {
      return hljs.highlight(content, { language: codeLanguage.value }).value
    }
    return hljs.highlightAuto(content).value
  } catch (error) {
    console.warn('代码高亮失败:', error)
    return escapeHtml(content)
  }
})

const formatContent = (content) => {
  if (Array.isArray(content)) return content.join('\n')
  if (content === undefined || content === null) return ''
  return String(content)
}

const openFullscreenPreview = () => {
  if (!props.file) return
  fullscreenPreviewVisible.value = true
}

const closeFullscreenPreview = () => {
  fullscreenPreviewVisible.value = false
}

watch(
  () => props.filePath,
  () => {
    htmlPreviewMode.value = 'render'
  }
)

watch([() => props.filePath, () => props.file?.previewType, () => props.file?.content], () => {
  if (isHtmlFile.value) {
    htmlPreviewRenderKey.value += 1
  }
})

watch(fullscreenPreviewVisible, (visible) => {
  document.body.style.overflow = visible ? 'hidden' : ''
})

onUnmounted(() => {
  document.body.style.overflow = ''
})
</script>

<style scoped lang="less">
.agent-file-preview {
  min-width: 0;
  border-radius: 8px;
  overflow: hidden;
}

.agent-file-preview.is-full-height {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.preview-header {
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 12px;
  border-bottom: 1px solid var(--gray-150);
  background: var(--gray-25);
}

.file-title,
.modal-actions,
.preview-mode-switch {
  display: flex;
  align-items: center;
}

.file-title {
  gap: 8px;
  min-width: 0;
}

.modal-actions,
.preview-mode-switch {
  gap: 8px;
}

.preview-mode-switch {
  padding: 2px;
  border-radius: 8px;
  background: var(--gray-100);
}

.file-path-title {
  font-weight: 400;
  color: var(--gray-700);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.modal-action-btn,
.preview-mode-btn {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--gray-600);
  cursor: pointer;
  transition: all 0.15s ease;
  padding: 0;
}

.modal-action-btn:hover,
.preview-mode-btn:hover {
  background: var(--gray-100);
  color: var(--gray-900);
}

.preview-mode-btn.active {
  background: var(--gray-0);
  color: var(--gray-900);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.file-content {
  min-height: 300px;
  max-height: 80vh;
  overflow-y: auto;
  border-radius: 0px;

  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: var(--gray-50);
    border-radius: 4px;
  }

  &::-webkit-scrollbar-thumb {
    background: var(--gray-300);
    border-radius: 4px;

    &:hover {
      background: var(--gray-400);
    }
  }

  .flat-md-preview {
    padding: 12px;
  }
}

.file-content pre,
.file-content-pre {
  font-family: 'JetBrains Mono', 'Fira Code', 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
  white-space: pre-wrap;
  word-wrap: break-word;
  color: var(--gray-1000);
  background: transparent;
  padding: 12px;
}

.file-content-pre.code-highlight {
  border-radius: 8px;
  background: var(--gray-25);
  white-space: pre;
  overflow-x: auto;
}

.file-content-pre.code-highlight code {
  padding: 14px 16px;
  display: block;
  white-space: pre;
  color: inherit;
  min-height: calc(80vh - 40px);
}

.image-preview-wrapper {
  display: flex;
  justify-content: center;
  align-items: flex-start;
}

.image-preview {
  display: block;
  max-width: 100%;
  max-height: calc(80vh - 32px);
  object-fit: contain;
  border-radius: 6px;
}

.pdf-preview {
  width: 100%;
  min-height: calc(80vh - 40px);
  border: none;
  border-radius: 6px;
  background: var(--gray-25);
}

.html-preview {
  width: 100%;
  min-height: calc(80vh - 40px);
  border: none;
  border-radius: 0px;
  background: #fff; // HTML 内容通常需要白色背景以保证可读性
}

.unsupported-preview {
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: var(--gray-600);
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.fullscreen-preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  background: var(--gray-0);
}

.fullscreen-preview-actions {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 8px;
}

.fullscreen-preview-switch {
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
}

.fullscreen-action-btn {
  width: 40px;
  height: 40px;
  border-radius: 999px;
  background: var(--color-trans-light);
  border: 1px solid var(--gray-200);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(10px);
}

.fullscreen-preview-content {
  position: absolute;
  inset: 0;
  min-height: 0;
}

.fullscreen-file-content {
  height: 100vh;
  max-height: none;
  min-height: 100vh;
  padding: 0px;
  border-radius: 0;
}

.fullscreen-image-preview-wrapper {
  min-height: calc(100vh - 48px);
  align-items: center;
}

.fullscreen-embed-preview {
  height: 100vh;
  border-radius: 0px;
}

.fullscreen-unsupported-preview {
  min-height: calc(100vh - 48px);
}

.fullscreen-file-content .file-content-pre.code-highlight code {
  min-height: calc(100vh - 48px);
}

.fullscreen-file-content .image-preview {
  max-height: calc(100vh - 48px);
}

:deep(.flat-md-preview .md-editor) {
  background: transparent;
}

:deep(.flat-md-preview .md-editor-preview-wrapper) {
  padding: 0;
}
</style>
