import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import test from 'node:test'
import { compileScript, parse } from 'vue/compiler-sfc'
import { computed, h, ref } from 'vue'

/** 执行检索面板真实 setup，并控制 HTTP 响应到达顺序。 */
async function createQueryPanel() {
  const source = await fs.readFile(new URL('../../src/modules/knowledge/ui/QuerySection.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const executable = compileScript(descriptor, { id: 'query-preview-state' }).content
    .replace(/^import[\s\S]*?from '[^']+'\n/gm, '').replace('export default', 'return')
  const requests = []
  const watches = []
  const store = { knowledgeBase: { kb_id: 'kb-1' }, state: { searchLoading: false }, meta: {} }
  const deps = {
    ref, computed, h, onMounted() {}, watch: (read, run) => watches.push({ read, run }),
    useKnowledgeBaseStore: () => store,
    message: { error: (error) => { throw new Error(error) } },
    queryApi: {
      queryTest: () => new Promise((resolve) => requests.push(resolve)),
      getSampleQuestions: async () => ({ questions: [] })
    },
    Braces: {}, RefreshCw: {}, SearchOutlined: {}, QueryResultChunk: {}, FileDetailModal: {}, ExternalDocumentReader: {}
  }
  const component = new Function(...Object.keys(deps), executable)(...Object.values(deps))
  const panel = component.setup({}, { expose() {}, emit() {} })
  panel.queryText.value = '测试问题'
  return { panel, store, requests, watches }
}

const chunk = { content: '原文命中', metadata: { file_id: 'file-1', chunk_id: 'chunk-g1' } }

test('新查询立即清空旧结果与原文选择，完成后只展示新结果', async () => {
  const { panel, requests } = await createQueryPanel()
  panel.queryResult.value = [chunk]
  panel.selectChunk(chunk)
  const pending = panel.onQuery()
  assert.equal(panel.queryResult.value, '')
  assert.equal(panel.selectedChunk.value, null)
  requests[0]([{ ...chunk, content: '新命中' }])
  await pending
  assert.equal(panel.queryResult.value[0].content, '新命中')
  assert.equal(panel.selectedChunk.value, null)
})

test('清空让待处理响应失效，不重新打开结果或原文', async () => {
  const { panel, requests, store } = await createQueryPanel()
  const pending = panel.onQuery()
  panel.clearQueryResult()
  requests[0]([chunk])
  await pending
  assert.equal(panel.queryResult.value, '')
  assert.equal(panel.selectedChunk.value, null)
  assert.equal(store.state.searchLoading, false)
})

test('切库与反序响应均不能覆盖当前查询', async () => {
  const { panel, requests, store, watches } = await createQueryPanel()
  const first = panel.onQuery()
  store.knowledgeBase.kb_id = 'kb-2'
  await watches.find(({ read }) => read() === 'kb-2').run('kb-2', 'kb-1')
  const second = panel.onQuery()
  requests[1]([{ ...chunk, content: '当前库命中' }])
  await second
  requests[0]([chunk])
  await first
  assert.equal(panel.queryResult.value[0].content, '当前库命中')
  assert.equal(panel.selectedChunk.value, null)
  assert.equal(store.state.searchLoading, false)
})
