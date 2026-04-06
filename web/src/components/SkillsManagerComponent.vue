<template>
  <div class="skills-manager-container extension-page-root">
    <div v-if="loading" class="loading-bar-wrapper">
      <div class="loading-bar"></div>
    </div>
    <div class="layout-wrapper" :class="{ 'content-loading': loading }">
      <!-- 左侧：技能列表 -->
      <div class="sidebar-list">
        <div class="sidebar-toolbar">
          <div class="search-box">
            <a-input
              v-model:value="searchQuery"
              placeholder="搜索技能..."
              allow-clear
              class="search-input"
            >
              <template #prefix><Search :size="14" class="text-muted" /></template>
            </a-input>
          </div>

          <a-tooltip title="刷新 Skills">
            <a-button class="sidebar-tool" :disabled="loading" @click="fetchSkills">
              <RotateCw :size="14" />
            </a-button>
          </a-tooltip>
        </div>

        <div class="list-container">
          <div
            v-if="
              filteredInstalledSkills.length === 0 && filteredUninstalledBuiltinSkills.length === 0
            "
            class="empty-text"
          >
            <a-empty :image="false" description="无匹配技能" />
          </div>
          <div v-if="filteredInstalledSkills.length" class="list-section-title">已添加 Skills</div>
          <template
            v-for="(skill, index) in filteredInstalledSkills"
            :key="`installed-${skill.slug}`"
          >
            <div
              class="list-item extension-list-item"
              :class="{ active: currentSkill?.slug === skill.slug }"
              @click="selectSkill(skill)"
            >
              <div class="item-main-row">
                <div class="item-header">
                  <BookMarked :size="16" class="item-icon" />
                  <span class="item-name">{{ skill.name }}</span>
                </div>
                <div class="item-status">
                  <span class="status-chip status-chip-success">已添加</span>
                  <button
                    type="button"
                    class="inline-hover-action"
                    @click.stop="confirmDeleteSkill(skill)"
                  >
                    移除
                  </button>
                </div>
              </div>
              <div class="item-details">
                <span class="item-desc">{{ skill.description || '暂无描述' }}</span>
                <div class="item-tags">
                  <span class="source-tag" :class="{ builtin: skill.sourceType === 'builtin' }">{{
                    skill.sourceLabel
                  }}</span>
                </div>
              </div>
            </div>
            <div
              v-if="
                index < filteredInstalledSkills.length - 1 ||
                filteredUninstalledBuiltinSkills.length > 0
              "
              class="list-separator"
            ></div>
          </template>

          <div v-if="filteredUninstalledBuiltinSkills.length" class="list-section-title">
            可添加 Skills
          </div>
          <template
            v-for="(skill, index) in filteredUninstalledBuiltinSkills"
            :key="`builtin-${skill.slug}`"
          >
            <div
              class="list-item extension-list-item"
              :class="{ active: currentSkill?.slug === skill.slug }"
              @click="selectSkill(skill)"
            >
              <div class="item-main-row">
                <div class="item-header">
                  <BookMarked :size="16" class="item-icon" />
                  <span class="item-name">{{ skill.name }}</span>
                </div>
                <div class="item-status">
                  <button
                    type="button"
                    class="skill-inline-action skill-inline-action-primary"
                    @click.stop="handleInstallBuiltin(skill)"
                  >
                    安装
                  </button>
                </div>
              </div>
              <div class="item-details">
                <span class="item-desc">{{ skill.description || '暂无描述' }}</span>
                <div class="item-tags">
                  <span class="source-tag builtin">内置</span>
                </div>
              </div>
            </div>
            <div
              v-if="index < filteredUninstalledBuiltinSkills.length - 1"
              class="list-separator"
            ></div>
          </template>
        </div>
      </div>

      <!-- 右侧：详情面板 -->
      <div class="main-panel">
        <div v-if="!currentSkill" class="unselected-state">
          <div class="hint-box">
            <FileCode :size="40" class="text-muted" />
            <p>请在左侧选择技能包进行编辑</p>
          </div>
        </div>

        <template v-else>
          <div class="panel-top-bar">
            <div class="panel-title-stack">
              <h2>{{ currentSkill.name }}</h2>
              <!-- <code>{{ currentSkill.slug }}</code> -->
            </div>
            <div class="panel-actions">
              <a-space :size="8">
                <span
                  v-if="currentSkillStatusLabel"
                  class="panel-status-chip"
                  :class="{ warning: currentSkillStatusTone === 'warning' }"
                >
                  {{ currentSkillStatusLabel }}
                </span>
                <button
                  v-if="currentSkill.is_builtin_spec && currentSkill.status === 'not_installed'"
                  type="button"
                  @click="handleInstallBuiltin(currentSkill)"
                  class="lucide-icon-btn extension-panel-action extension-panel-action-primary"
                >
                  <span>安装</span>
                </button>
                <button
                  v-if="currentSkill.is_builtin_spec && currentSkill.status === 'update_available'"
                  type="button"
                  @click="handleUpdateBuiltin(currentSkill)"
                  class="lucide-icon-btn extension-panel-action extension-panel-action-secondary"
                >
                  <span>更新</span>
                </button>
                <button
                  v-if="isInstalledSkill"
                  type="button"
                  @click="handleExport"
                  class="lucide-icon-btn extension-panel-action extension-panel-action-secondary"
                >
                  <Download :size="14" />
                  <span>导出</span>
                </button>
                <button
                  v-if="isInstalledSkill"
                  type="button"
                  @click="confirmDeleteSkill"
                  class="lucide-icon-btn extension-panel-action extension-panel-action-danger"
                >
                  <Trash2 :size="14" />
                  <span>{{ isBuiltinInstalledSkill ? '卸载' : '删除' }}</span>
                </button>
              </a-space>
            </div>
          </div>

          <div v-if="!isInstalledSkill" class="builtin-uninstalled-state">
            <h3>{{ currentSkill.description }}</h3>
            <p>版本 {{ currentSkill.version }}</p>
            <a-button type="primary" @click="handleInstallBuiltin(currentSkill)"
              >安装内置 Skill</a-button
            >
          </div>

          <a-tabs v-else v-model:activeKey="activeTab" class="minimal-tabs">
            <a-tab-pane key="editor">
              <template #tab>
                <span class="tab-title"><FileText :size="14" />代码管理</span>
              </template>
              <div class="workspace">
                <div class="tree-container">
                  <div class="tree-header">
                    <span class="label">项目结构</span>
                    <div class="tree-actions">
                      <a-tooltip v-if="!isBuiltinInstalledSkill" title="新建文件"
                        ><button @click="openCreateModal(false)"><FilePlus :size="14" /></button
                      ></a-tooltip>
                      <a-tooltip v-if="!isBuiltinInstalledSkill" title="新建目录"
                        ><button @click="openCreateModal(true)"><FolderPlus :size="14" /></button
                      ></a-tooltip>
                      <a-tooltip title="刷新"
                        ><button @click="reloadTree"><RotateCw :size="14" /></button
                      ></a-tooltip>
                    </div>
                  </div>
                  <div class="tree-content">
                    <FileTreeComponent
                      v-model:selectedKeys="selectedTreeKeys"
                      v-model:expandedKeys="expandedKeys"
                      :tree-data="treeData"
                      @select="handleTreeSelect"
                    />
                  </div>
                </div>

                <div class="editor-container">
                  <div class="editor-header">
                    <div class="current-path">
                      <File :size="14" />
                      <span>{{ selectedPath || '未选择文件' }}</span>
                      <span v-if="canSave" class="save-hint">●</span>
                    </div>
                    <div class="header-actions">
                      <a-button
                        v-if="isMarkdownFile && selectedPath"
                        size="small"
                        @click="viewMode = viewMode === 'edit' ? 'preview' : 'edit'"
                        class="lucide-icon-btn view-toggle-btn"
                        :title="viewMode === 'edit' ? '预览' : '编辑'"
                      >
                        <Eye v-if="viewMode === 'edit'" :size="14" />
                        <Edit3 v-else :size="14" />
                        <span>{{ viewMode === 'edit' ? '预览' : '编辑' }}</span>
                      </a-button>
                      <a-button
                        v-if="!isBuiltinInstalledSkill"
                        type="primary"
                        size="small"
                        @click="saveCurrentFile"
                        :disabled="!canSave"
                        :loading="savingFile"
                        class="lucide-icon-btn"
                      >
                        <Save :size="14" />
                        <span>保存</span>
                      </a-button>
                    </div>
                  </div>
                  <div class="editor-main">
                    <a-empty
                      v-if="!selectedPath || selectedIsDir"
                      description="选择文件以开始编辑"
                      class="mt-40"
                    />
                    <template v-else>
                      <MdPreview
                        v-if="viewMode === 'preview'"
                        :modelValue="fileContent"
                        :theme="theme"
                        previewTheme="github"
                        class="markdown-preview flat-md-preview"
                      />
                      <a-textarea
                        v-else
                        v-model:value="fileContent"
                        class="pure-editor"
                        :readonly="isBuiltinInstalledSkill"
                        spellcheck="false"
                      />
                    </template>
                  </div>
                </div>
              </div>
            </a-tab-pane>

            <a-tab-pane key="dependencies">
              <template #tab>
                <span class="tab-title"><Layers :size="14" />依赖管理</span>
              </template>
              <div class="config-view">
                <div class="config-header">
                  <div class="text">
                    <h3>依赖声明</h3>
                    <p>配置此 Skill 所需的工具、MCP 及其他 Skill 依赖。</p>
                  </div>
                  <a-button
                    type="primary"
                    :loading="savingDependencies"
                    @click="saveDependencies"
                    class="lucide-icon-btn"
                  >
                    <Save :size="14" />
                    <span>更新依赖</span>
                  </a-button>
                </div>

                <div class="config-form">
                  <a-form layout="vertical">
                    <a-form-item label="工具依赖 (Tools)">
                      <a-select
                        v-model:value="dependencyForm.tool_dependencies"
                        mode="multiple"
                        :options="toolDependencyOptions"
                        placeholder="选择工具..."
                        allow-clear
                        show-search
                      />
                    </a-form-item>
                    <a-form-item label="MCP 依赖 (Model Context Protocol)">
                      <a-select
                        v-model:value="dependencyForm.mcp_dependencies"
                        mode="multiple"
                        :options="mcpDependencyOptions"
                        placeholder="选择 MCP 服务..."
                        allow-clear
                        show-search
                      />
                    </a-form-item>
                    <a-form-item label="Skill 依赖">
                      <a-select
                        v-model:value="dependencyForm.skill_dependencies"
                        mode="multiple"
                        :options="skillDependencyOptions"
                        placeholder="选择 Skill..."
                        allow-clear
                        show-search
                      />
                    </a-form-item>
                  </a-form>
                </div>
              </div>
            </a-tab-pane>
          </a-tabs>
        </template>
      </div>
    </div>

    <!-- 弹窗 -->
    <a-modal
      v-model:open="createModalVisible"
      :title="createForm.isDir ? '新建目录' : '新建文件'"
      @ok="handleCreateNode"
      :confirm-loading="creatingNode"
      width="400px"
    >
      <a-form layout="vertical" class="pt-12">
        <a-form-item label="路径 (相对于根目录)" required>
          <a-input v-model:value="createForm.path" placeholder="src/main.py" />
        </a-form-item>
        <a-form-item v-if="!createForm.isDir" label="内容">
          <a-textarea v-model:value="createForm.content" :rows="5" />
        </a-form-item>
      </a-form>
    </a-modal>

    <a-modal
      v-model:open="remoteInstallModalVisible"
      title="远程安装 Skill"
      :footer="null"
      width="560px"
      :closable="!installingRemoteSkill"
      :mask-closable="!installingRemoteSkill"
      :keyboard="!installingRemoteSkill"
    >
      <div class="remote-install-panel modal-mode">
        <div class="panel-header-text">
          <span class="title">基于 skills.sh 的能力拉取并导入到当前系统</span>
          <span class="desc">
            支持 `owner/repo` 或完整 GitHub URL，可前往
            <a href="https://skills.sh/" target="_blank" rel="noopener noreferrer">skills.sh</a>
            查询可用 skills
          </span>
        </div>
        <a-form layout="vertical" class="remote-install-form">
          <a-form-item label="来源仓库">
            <a-input
              v-model:value="remoteInstallForm.source"
              placeholder="anthropics/skills 或 GitHub URL"
              :disabled="installingRemoteSkill"
            />
          </a-form-item>
          <a-form-item label="Skill 名称">
            <a-select
              v-model:value="remoteInstallForm.skills"
              mode="tags"
              :options="filteredRemoteSkillOptions"
              placeholder="frontend-design"
              allow-clear
              show-search
              :disabled="installingRemoteSkill"
              :filter-option="filterRemoteSkillOption"
              :max-tag-count="6"
            />
          </a-form-item>
          <div class="remote-install-actions">
            <a-button
              :loading="listingRemoteSkills"
              :disabled="installingRemoteSkill"
              @click="handleListRemoteSkills"
            >
              查看可安装 Skills
            </a-button>
            <a-button
              type="primary"
              :loading="installingRemoteSkill"
              :disabled="listingRemoteSkills"
              @click="handleInstallRemoteSkill"
            >
              安装
            </a-button>
            <span v-if="remoteInstallStatusText" class="remote-install-status">
              {{ remoteInstallStatusText }}
            </span>
          </div>
          <div v-if="remoteSkillOptions.length" class="remote-skill-summary">
            共发现 {{ remoteSkillOptions.length }} 个 skills，可按输入内容筛选候选项。
          </div>
        </a-form>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { useThemeStore } from '@/stores/theme'
import {
  RotateCw,
  Download,
  Trash2,
  Save,
  FileText,
  Layers,
  FilePlus,
  FolderPlus,
  File,
  Search,
  BookMarked,
  FileCode,
  Eye,
  Edit3
} from 'lucide-vue-next'
import { skillApi } from '@/apis/skill_api'
import FileTreeComponent from '@/components/FileTreeComponent.vue'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const themeStore = useThemeStore()
const theme = computed(() => (themeStore.isDark ? 'dark' : 'light'))

const loading = ref(false)
const importing = ref(false)
const listingRemoteSkills = ref(false)
const installingRemoteSkill = ref(false)
const savingFile = ref(false)
const creatingNode = ref(false)
const savingDependencies = ref(false)
const activeTab = ref('editor')
const searchQuery = ref('')
const viewMode = ref('edit') // 'edit' | 'preview'

const skills = ref([])
const builtinSkills = ref([])
const currentSkill = ref(null)
const treeData = ref([])
const selectedTreeKeys = ref([])
const expandedKeys = ref([])
const selectedPath = ref('')
const selectedIsDir = ref(false)
const fileContent = ref('')
const originalFileContent = ref('')

const createModalVisible = ref(false)
const remoteInstallModalVisible = ref(false)
const createForm = reactive({ path: '', isDir: false, content: '' })
const remoteInstallForm = reactive({
  source: 'https://github.com/anthropics/skills',
  skills: []
})
const remoteSkillOptions = ref([])
const remoteInstallProgress = reactive({
  visible: false,
  total: 0,
  completed: 0,
  success: 0,
  failed: 0,
  currentSkill: ''
})
const remoteInstallResults = reactive({
  success: [],
  failed: []
})
const dependencyOptions = reactive({ tools: [], mcps: [], skills: [] })
const dependencyForm = reactive({
  tool_dependencies: [],
  mcp_dependencies: [],
  skill_dependencies: []
})

const matchesSearch = (skill) => {
  if (!searchQuery.value) return true
  const q = searchQuery.value.toLowerCase()
  return skill.name.toLowerCase().includes(q) || skill.slug.toLowerCase().includes(q)
}

const installedSkillCards = computed(() => {
  const builtinInstalledMap = new Map(
    (builtinSkills.value || [])
      .filter((skill) => skill.status !== 'not_installed')
      .map((skill) => [
        skill.slug,
        {
          ...skill,
          sourceType: 'builtin',
          sourceLabel: '内置',
          statusLabel: skill.status === 'update_available' ? '更新可用' : '已安装',
          statusTone: skill.status === 'update_available' ? 'warning' : 'default'
        }
      ])
  )

  const importedInstalled = (skills.value || [])
    .filter((skill) => !builtinInstalledMap.has(skill.slug))
    .map((skill) => ({
      ...skill,
      sourceType: 'imported',
      sourceLabel: '导入',
      statusLabel: '已上传',
      statusTone: 'default'
    }))

  return [...builtinInstalledMap.values(), ...importedInstalled]
})

const filteredInstalledSkills = computed(() => installedSkillCards.value.filter(matchesSearch))

const filteredUninstalledBuiltinSkills = computed(() => {
  return (builtinSkills.value || []).filter(
    (skill) => skill.status === 'not_installed' && matchesSearch(skill)
  )
})

const isInstalledSkill = computed(() => {
  return !!(
    currentSkill.value &&
    (currentSkill.value.installed_record || currentSkill.value.dir_path)
  )
})

const isBuiltinInstalledSkill = computed(() => {
  return !!(
    isInstalledSkill.value &&
    (currentSkill.value?.is_builtin || currentSkill.value?.installed_record)
  )
})

const currentSkillStatusLabel = computed(() => {
  const skill = currentSkill.value
  if (!skill) return ''
  if (skill.is_builtin_spec) {
    if (skill.status === 'not_installed') return '未安装'
    if (skill.status === 'update_available') return '更新可用'
    return '已安装'
  }
  if (skill.is_builtin) return '已安装'
  return '已上传'
})

const currentSkillStatusTone = computed(() => {
  return currentSkill.value?.status === 'update_available' ? 'warning' : 'default'
})

const canSave = computed(() => {
  if (!selectedPath.value || selectedIsDir.value) return false
  return fileContent.value !== originalFileContent.value
})

const isMarkdownFile = computed(() => {
  if (!selectedPath.value) return false
  return selectedPath.value.toLowerCase().endsWith('.md')
})

// 切换到非markdown文件时重置为编辑模式
watch(selectedPath, (newPath) => {
  if (newPath && !newPath.toLowerCase().endsWith('.md')) {
    viewMode.value = 'edit'
  }
})

const toolDependencyOptions = computed(() =>
  (dependencyOptions.tools || []).map((i) =>
    typeof i === 'object' ? { label: i.name, value: i.id } : { label: i, value: i }
  )
)
const mcpDependencyOptions = computed(() =>
  (dependencyOptions.mcps || []).map((i) => ({ label: i, value: i }))
)
const skillDependencyOptions = computed(() =>
  (dependencyOptions.skills || [])
    .filter((s) => s !== currentSkill.value?.slug)
    .map((i) => ({ label: i, value: i }))
)
const filteredRemoteSkillOptions = computed(() =>
  remoteSkillOptions.value.map((item) => ({
    value: item.name,
    label: item.description ? `${item.name} - ${item.description}` : item.name
  }))
)
const remoteInstallStatusText = computed(() => {
  if (!remoteInstallProgress.visible || !remoteInstallProgress.total) return ''
  const progressText = `[${remoteInstallProgress.completed}/${remoteInstallProgress.total}]`
  const currentSkill = remoteInstallProgress.currentSkill || ''
  const failedText =
    remoteInstallProgress.failed > 0 ? `, ${remoteInstallProgress.failed} failed` : ''
  return `${progressText} ${currentSkill}${failedText}`.trim()
})
const filterRemoteSkillOption = (input, option) => {
  const keyword = input.trim().toLowerCase()
  if (!keyword) return true
  const value = String(option?.value || '').toLowerCase()
  const label = String(option?.label || '').toLowerCase()
  return value.includes(keyword) || label.includes(keyword)
}

const normalizeRemoteSkillNames = (skills) => {
  const seen = new Set()
  return (skills || []).reduce((acc, skill) => {
    const normalized = String(skill || '').trim()
    if (!normalized || seen.has(normalized)) return acc
    seen.add(normalized)
    acc.push(normalized)
    return acc
  }, [])
}

const resetRemoteInstallState = () => {
  remoteInstallProgress.visible = false
  remoteInstallProgress.total = 0
  remoteInstallProgress.completed = 0
  remoteInstallProgress.success = 0
  remoteInstallProgress.failed = 0
  remoteInstallProgress.currentSkill = ''
  remoteInstallResults.success = []
  remoteInstallResults.failed = []
}

const normalizeTree = (nodes) =>
  (nodes || []).map((node) => ({
    title: node.name,
    key: node.path,
    isLeaf: !node.is_dir,
    path: node.path,
    is_dir: node.is_dir,
    children: node.is_dir ? normalizeTree(node.children || []) : undefined
  }))

const resetFileState = () => {
  selectedPath.value = ''
  selectedIsDir.value = false
  selectedTreeKeys.value = []
  expandedKeys.value = []
  fileContent.value = ''
  originalFileContent.value = ''
  viewMode.value = 'preview'
}

const expandAllKeys = (nodes) =>
  nodes.flatMap((node) => (node.is_dir ? [node.key, ...expandAllKeys(node.children || [])] : []))

const fetchSkills = async () => {
  loading.value = true
  try {
    const [skillResult, builtinResult] = await Promise.all([
      skillApi.listSkills(),
      skillApi.listBuiltinSkills()
    ])
    skills.value = skillResult?.data || []
    builtinSkills.value = (builtinResult?.data || []).map((item) => ({
      ...item,
      ...(item.installed_record || {}),
      is_builtin_spec: true
    }))

    // 默认选中第一个技能并加载 SKILL.md
    const preferredList = filteredInstalledSkills.value.length
      ? filteredInstalledSkills.value
      : filteredUninstalledBuiltinSkills.value
    if (!currentSkill.value && preferredList.length > 0) {
      await selectSkill(preferredList[0])
    } else if (currentSkill.value) {
      const latest =
        builtinSkills.value.find((i) => i.slug === currentSkill.value.slug) ||
        skills.value.find((i) => i.slug === currentSkill.value.slug)
      if (latest) {
        currentSkill.value = latest
        syncDependencyFormFromSkill(latest.installed_record || latest)
      } else {
        currentSkill.value = null
        treeData.value = []
        resetFileState()
      }
    }
    await fetchDependencyOptions()
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

const fetchDependencyOptions = async () => {
  try {
    const result = await skillApi.getSkillDependencyOptions()
    const data = result?.data || {}
    dependencyOptions.tools = data.tools || []
    dependencyOptions.mcps = data.mcps || []
    dependencyOptions.skills = data.skills || []
  } catch {
    // ignore error
  }
}

const syncDependencyFormFromSkill = (skillRecord) => {
  dependencyForm.tool_dependencies = [...(skillRecord?.tool_dependencies || [])]
  dependencyForm.mcp_dependencies = [...(skillRecord?.mcp_dependencies || [])]
  dependencyForm.skill_dependencies = [...(skillRecord?.skill_dependencies || [])]
}

const reloadTree = async () => {
  if (!currentSkill.value || !isInstalledSkill.value) return
  loading.value = true
  try {
    const result = await skillApi.getSkillTree(currentSkill.value.slug)
    const normalized = normalizeTree(result?.data || [])
    treeData.value = normalized
    expandedKeys.value = expandAllKeys(normalized)
  } catch {
    message.error('加载目录树失败')
  } finally {
    loading.value = false
  }
}

const loadSkillFile = async (slug, path = 'SKILL.md') => {
  try {
    const fileResult = await skillApi.getSkillFile(slug, path)
    const content = fileResult?.data?.content || ''
    fileContent.value = content
    originalFileContent.value = content
    selectedPath.value = path
    selectedIsDir.value = false
    selectedTreeKeys.value = [path]
  } catch {
    // 文件不存在时忽略
  }
}

const selectSkill = async (record) => {
  currentSkill.value = record
  resetFileState()
  syncDependencyFormFromSkill(record.installed_record || record)

  if (!record.installed_record && !record.dir_path) {
    treeData.value = []
    return
  }

  // 并行执行：加载树结构和获取 SKILL.md
  await Promise.all([reloadTree(), loadSkillFile(record.slug)])
}

const handleTreeSelect = async (keys, info) => {
  if (!keys?.length) {
    resetFileState()
    return
  }
  const node = info?.node || {}
  const path = node.path || node.key
  const isDir = !!node.is_dir
  selectedTreeKeys.value = [path]
  selectedPath.value = path
  selectedIsDir.value = isDir
  if (isDir) {
    fileContent.value = ''
    originalFileContent.value = ''
    return
  }
  try {
    const result = await skillApi.getSkillFile(currentSkill.value.slug, path)
    const content = result?.data?.content || ''
    fileContent.value = content
    originalFileContent.value = content
  } catch {
    message.error('文件读取失败')
  }
}

const saveCurrentFile = async () => {
  if (
    !currentSkill.value ||
    !selectedPath.value ||
    selectedIsDir.value ||
    isBuiltinInstalledSkill.value
  )
    return
  savingFile.value = true
  try {
    await skillApi.updateSkillFile(currentSkill.value.slug, {
      path: selectedPath.value,
      content: fileContent.value
    })
    originalFileContent.value = fileContent.value
    message.success('已保存')
    if (selectedPath.value === 'SKILL.md') await fetchSkills()
  } catch {
    message.error('保存失败')
  } finally {
    savingFile.value = false
  }
}

const handleInstallBuiltin = async (record) => {
  if (!record?.slug) return
  loading.value = true
  try {
    await skillApi.installBuiltinSkill(record.slug)
    await fetchSkills()
    const latest = builtinSkills.value.find((item) => item.slug === record.slug)
    if (latest) await selectSkill(latest)
    message.success('安装成功')
  } catch (error) {
    message.error(error?.response?.data?.detail || error.message || '安装失败')
  } finally {
    loading.value = false
  }
}

const handleUpdateBuiltin = async (record) => {
  if (!record?.slug) return
  loading.value = true
  try {
    await skillApi.updateBuiltinSkill(record.slug, false)
    await fetchSkills()
    const latest = builtinSkills.value.find((item) => item.slug === record.slug)
    if (latest) await selectSkill(latest)
    message.success('更新成功')
  } catch (error) {
    if (error.response?.data?.detail?.needs_confirm) {
      loading.value = false
      Modal.confirm({
        title: '确认覆盖更新？',
        content: '检测到你修改过此 skill，更新将覆盖你的修改，是否继续？',
        okText: '继续更新',
        cancelText: '取消',
        onOk: async () => {
          loading.value = true
          try {
            await skillApi.updateBuiltinSkill(record.slug, true)
            await fetchSkills()
            const latest = builtinSkills.value.find((item) => item.slug === record.slug)
            if (latest) await selectSkill(latest)
            message.success('更新成功')
          } catch (forceError) {
            message.error(forceError?.response?.data?.detail || forceError.message || '更新失败')
          } finally {
            loading.value = false
          }
        }
      })
      return
    }
    message.error(error?.response?.data?.detail || error.message || '更新失败')
  } finally {
    loading.value = false
  }
}

const openCreateModal = (isDir) => {
  if (!currentSkill.value) return
  createForm.path = ''
  createForm.content = ''
  createForm.isDir = isDir
  createModalVisible.value = true
}

const handleCreateNode = async () => {
  if (!currentSkill.value || !createForm.path.trim() || isBuiltinInstalledSkill.value) return
  creatingNode.value = true
  try {
    await skillApi.createSkillFile(currentSkill.value.slug, {
      path: createForm.path.trim(),
      is_dir: createForm.isDir,
      content: createForm.content
    })
    createModalVisible.value = false
    await reloadTree()
    message.success('创建成功')
  } catch {
    message.error('创建失败')
  } finally {
    creatingNode.value = false
  }
}

const confirmDeleteSkill = (targetSkill = null) => {
  const target = targetSkill || currentSkill.value
  if (!target) return

  const installed = !!(
    target &&
    (target.installed_record || target.dir_path || target.is_builtin || target.sourceType)
  )
  if (!installed) return

  const isBuiltinTarget = !!(
    target?.is_builtin ||
    target?.installed_record ||
    target?.sourceType === 'builtin'
  )
  const actionText = isBuiltinTarget ? '卸载' : '删除'
  const detailText = isBuiltinTarget
    ? '卸载后会移除已安装文件和数据库记录，但仍可从“未安装 Skills”中重新安装。'
    : '删除后无法恢复，所有文件和配置将永久消失。'
  Modal.confirm({
    title: `确认${actionText}技能「${target.slug}」？`,
    content: detailText,
    okText: `确认${actionText}`,
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await skillApi.deleteSkill(target.slug)
        message.success(`已${actionText}`)
        if (currentSkill.value?.slug === target.slug) {
          currentSkill.value = null
          treeData.value = []
          resetFileState()
        }
        await fetchSkills()
      } catch {
        message.error(`${actionText}失败`)
      }
    }
  })
}

const handleExport = async () => {
  if (!currentSkill.value || !isInstalledSkill.value) return
  try {
    const response = await skillApi.exportSkill(currentSkill.value.slug)
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${currentSkill.value.slug}.zip`
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    message.error('导出失败')
  }
}

const handleImportUpload = async ({ file, onSuccess, onError }) => {
  importing.value = true
  try {
    const result = await skillApi.importSkillZip(file)
    message.success('导入完成')
    await fetchSkills()
    const imported = result?.data
    if (imported?.slug) {
      const record = skills.value.find((i) => i.slug === imported.slug)
      if (record) await selectSkill(record)
    }
    onSuccess?.(result)
  } catch (e) {
    message.error('导入失败')
    onError?.(e)
  } finally {
    importing.value = false
  }
}

const handleListRemoteSkills = async () => {
  const source = remoteInstallForm.source.trim()
  if (!source) {
    message.warning('请输入来源仓库')
    return
  }
  listingRemoteSkills.value = true
  try {
    const result = await skillApi.listRemoteSkills(source)
    remoteSkillOptions.value = result?.data || []
    remoteInstallForm.skills = normalizeRemoteSkillNames(remoteInstallForm.skills)
    if (!remoteSkillOptions.value.length) {
      message.warning('未发现可安装的 Skills')
      return
    }
    message.success(`已发现 ${remoteSkillOptions.value.length} 个 Skills`)
  } catch (error) {
    message.error(error?.response?.data?.detail || error.message || '获取远程 Skills 失败')
  } finally {
    listingRemoteSkills.value = false
  }
}

const handleInstallRemoteSkill = async () => {
  const source = remoteInstallForm.source.trim()
  const skillsToInstall = normalizeRemoteSkillNames(remoteInstallForm.skills)
  if (!source || !skillsToInstall.length) {
    message.warning('请填写来源仓库和 Skill 名称')
    return
  }
  remoteInstallForm.skills = skillsToInstall
  resetRemoteInstallState()
  installingRemoteSkill.value = true
  remoteInstallProgress.visible = true
  remoteInstallProgress.total = skillsToInstall.length
  let lastInstalledSlug = ''
  try {
    for (const skill of skillsToInstall) {
      remoteInstallProgress.currentSkill = skill
      try {
        const result = await skillApi.installRemoteSkill({ source, skill })
        const installed = result?.data
        const installedSlug = installed?.slug || skill
        remoteInstallResults.success.push(installedSlug)
        remoteInstallProgress.success += 1
        lastInstalledSlug = installedSlug
      } catch (error) {
        remoteInstallResults.failed.push({
          skill,
          error: error?.response?.data?.detail || error.message || '远程 Skill 安装失败'
        })
        remoteInstallProgress.failed += 1
      } finally {
        remoteInstallProgress.completed += 1
      }
    }
    remoteInstallProgress.currentSkill = ''
    await fetchSkills()
    if (lastInstalledSlug) {
      const record =
        skills.value.find((item) => item.slug === lastInstalledSlug) ||
        builtinSkills.value.find((item) => item.slug === lastInstalledSlug)
      if (record) await selectSkill(record)
    }
    if (remoteInstallResults.failed.length === 0) {
      remoteInstallModalVisible.value = false
      message.success(`远程 Skills 安装成功，共 ${remoteInstallResults.success.length} 个`)
      resetRemoteInstallState()
      remoteInstallForm.skills = []
      return
    }
    message.warning(
      `远程 Skills 安装完成，成功 ${remoteInstallResults.success.length} 个，失败 ${remoteInstallResults.failed.length} 个`
    )
  } catch (error) {
    message.error(error?.response?.data?.detail || error.message || '远程 Skill 安装失败')
  } finally {
    remoteInstallProgress.currentSkill = ''
    installingRemoteSkill.value = false
  }
}

const openRemoteInstallModal = () => {
  if (!remoteInstallModalVisible.value) {
    remoteInstallForm.skills = []
    resetRemoteInstallState()
  }
  remoteInstallModalVisible.value = true
}

watch(remoteInstallModalVisible, (visible) => {
  if (!visible && !installingRemoteSkill.value) {
    remoteInstallForm.skills = []
    resetRemoteInstallState()
  }
})

const saveDependencies = async () => {
  if (!currentSkill.value || !isInstalledSkill.value) return
  savingDependencies.value = true
  try {
    const result = await skillApi.updateSkillDependencies(currentSkill.value.slug, {
      tool_dependencies: dependencyForm.tool_dependencies,
      mcp_dependencies: dependencyForm.mcp_dependencies,
      skill_dependencies: dependencyForm.skill_dependencies
    })
    const updated = result?.data
    if (updated) {
      currentSkill.value = updated
      syncDependencyFormFromSkill(updated)
    }
    await fetchSkills()
    message.success('依赖已更新')
  } catch {
    message.error('更新失败')
  } finally {
    savingDependencies.value = false
  }
}

onMounted(fetchSkills)

// 暴露方法给父组件
defineExpose({
  fetchSkills,
  handleImportUpload,
  openRemoteInstallModal
})
</script>

<style scoped lang="less">
@import '@/assets/css/extensions.less';

.builtin-uninstalled-state {
  padding: 24px;
  h3 {
    margin: 0 0 8px;
    font-size: 16px;
  }
  p {
    margin: 0 0 16px;
    color: var(--gray-500);
  }
}

.workspace {
  display: flex;
  flex: 1;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.remote-install-panel {
  background: linear-gradient(180deg, var(--gray-0) 0%, var(--gray-50) 100%);
  border: 1px solid @border-color;
  border-radius: 12px;
  padding: 16px;

  &.modal-mode {
    border: none;
    border-radius: 0;
    padding: 0;
    background: transparent;
  }

  .panel-header-text {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 12px;

    .title {
      font-size: 14px;
      font-weight: 600;
      color: var(--gray-900);
    }

    .desc {
      font-size: 12px;
      color: var(--gray-500);
    }
  }

  .remote-install-form {
    :deep(.ant-form-item) {
      margin-bottom: 12px;
    }
  }

  .remote-install-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .remote-install-status {
    min-width: 0;
    flex: 1;
    font-size: 12px;
    color: var(--gray-600);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .remote-skill-hints {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }

  .remote-skill-summary {
    margin-top: 12px;
    font-size: 12px;
    color: var(--gray-500);
  }
}

/* 文件 tree */
.tree-container {
  width: 240px;
  border-right: 1px solid @border-color;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;

  .tree-header {
    padding: 10px 12px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    .label {
      font-size: 12px;
      font-weight: 600;
      color: var(--gray-500);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .tree-actions {
      display: flex;
      gap: 4px;
      button {
        background: none;
        border: none;
        padding: 2px;
        cursor: pointer;
        color: var(--gray-500);
        display: flex;
        align-items: center;
        &:hover {
          color: var(--gray-900);
        }
      }
    }
  }

  .tree-content {
    flex: 1;
    overflow-y: auto;
    height: 100%;
    padding: 8px 0;
  }
}

/* 编辑器 */
.editor-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;

  .editor-header {
    padding: 8px 16px 4px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background-color: var(--gray-0);
    flex-shrink: 0;

    .current-path {
      display: flex;
      align-items: center;
      gap: 8px;
      font-family: monospace;
      font-size: 12px;
      color: var(--gray-500);
      .save-hint {
        color: var(--color-warning-500);
        font-size: 10px;
        margin-left: 4px;
      }
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .view-toggle-btn {
      background-color: var(--gray-100);
      border-color: var(--gray-300);
      &:hover {
        background-color: var(--gray-200);
        border-color: var(--gray-400);
      }
    }
  }

  .editor-main {
    flex: 1;
    min-height: 0;
    background-color: var(--gray-0);
    display: flex;
    flex-direction: column;
  }

  .editor-main :deep(.ant-empty) {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .editor-main :deep(textarea) {
    flex: 1;
    min-height: 0;
  }

  .pure-editor {
    width: 100%;
    height: 100%;
    border: none;
    resize: none;
    padding: 16px;
    font-family: 'Fira Code', 'Monaco', monospace;
    font-size: 13px;
    line-height: 1.6;
    &:focus {
      outline: none;
    }
  }

  .markdown-preview {
    flex: 1;
    height: 100%;
    overflow-y: auto;
    :deep(.md-editor) {
      height: 100%;
      background: var(--gray-0);
    }
    :deep(.md-editor-preview-wrapper) {
      padding: 16px 20px;
    }
  }
}

/* 依赖配置 */
.config-view {
  padding: 16px;
  flex: 1;
  overflow-y: auto;
  .config-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 32px;
    flex-shrink: 0;
    .text {
      h3 {
        margin: 0 0 4px 0;
        font-size: 16px;
        font-weight: 600;
      }
      p {
        margin: 0;
        color: var(--gray-500);
        font-size: 13px;
      }
    }
  }
  .config-form {
    max-width: 600px;
    :deep(.ant-form-item-label label) {
      font-weight: 500;
      font-size: 13px;
    }
  }
}

.mt-40 {
  margin-top: 40px;
}
.pt-12 {
  padding-top: 12px;
}

@media (max-width: 1000px) {
  .sidebar-list {
    width: 220px;
  }
  .tree-container {
    width: 180px;
  }
}
</style>
