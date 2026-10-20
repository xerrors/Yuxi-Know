import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createTestServer } from '../helpers/createTestServer.js'

test('默认选择使用默认标记，不把其他内置角色当作默认助手', async (t) => {
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  const server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  const pinia = createPinia()
  setActivePinia(pinia)
  try {
    const { useAgentStore } = await server.ssrLoadModule('/src/modules/agents/model/agent.js')
    const { agentApi, knowledgeBaseApi, toolApi } = await server.ssrLoadModule('/src/apis/index.js')
    const agents = [
      { agent_id: 'deep-research', name: '深度研究', is_builtin: true, is_default: false, can_run: true },
      { agent_id: 'default-chatbot', name: '智能助手', is_builtin: true, is_default: true, can_run: true }
    ]
    t.mock.method(agentApi, 'getAgents', async () => ({ agents }))
    t.mock.method(agentApi, 'getAgentDetail', async (id) => ({ agent: agents.find((agent) => agent.agent_id === id) }))
    t.mock.method(knowledgeBaseApi, 'getAccessibleKnowledgeBases', async () => ({ knowledge_bases: [] }))
    t.mock.method(toolApi, 'getTools', async () => ({ data: [] }))
    const store = useAgentStore()
    await store.initialize()
    assert.equal(store.selectedAgentId, 'default-chatbot')
    assert.equal(store.agents[0].agent_id, 'default-chatbot')

    store.reset()
    store.selectedAgentId = 'deep-research'
    await store.initialize()
    assert.equal(store.selectedAgentId, 'deep-research', '保留仍可运行的已有选择')

    store.reset()
    store.selectedAgentId = 'deleted-agent'
    await store.initialize()
    assert.equal(store.selectedAgentId, 'default-chatbot', '失效的选择回到默认助手')

    store.reset()
    agents[1].can_run = false
    store.selectedAgentId = 'default-chatbot'
    await store.initialize()
    assert.equal(store.selectedAgentId, 'deep-research', '默认助手不可运行时只选择可运行角色')

    store.reset()
    agents[0].can_run = false
    await store.initialize()
    assert.equal(store.selectedAgentId, null)
  } finally {
    disposePinia(pinia)
    await server.close()
    delete globalThis.localStorage
  }
})

test('并发入口等待目录准备后再继续，重置后可以重新初始化', async (t) => {
  globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} }
  const server = await createTestServer({ server: { middlewareMode: true, hmr: false } })
  const pinia = createPinia()
  setActivePinia(pinia)
  try {
    const { useAgentStore } = await server.ssrLoadModule('/src/modules/agents/model/agent.js')
    const { agentApi, knowledgeBaseApi, toolApi } = await server.ssrLoadModule('/src/apis/index.js')
    let finish
    t.mock.method(
      agentApi,
      'getAgents',
      () =>
        new Promise((resolve) => {
          finish = resolve
        })
    )
    t.mock.method(knowledgeBaseApi, 'getAccessibleKnowledgeBases', async () => ({ knowledge_bases: [] }))
    t.mock.method(toolApi, 'getTools', async () => ({ data: [] }))
    const store = useAgentStore()
    const first = store.initialize()
    let secondReady = false
    const second = store.initialize().then(() => {
      secondReady = true
    })
    await Promise.resolve()
    assert.equal(secondReady, false, '目录响应前第二个入口必须保持等待')
    assert.equal(store.isInitialized, false)
    finish({ agents: [] })
    await Promise.all([first, second])
    assert.equal(store.isInitialized, true)
    assert.equal(secondReady, true)
    store.reset()
    const third = store.initialize()
    finish({ agents: [] })
    await third
    assert.equal(store.isInitialized, true)

    const directory = [], knowledge = [], tools = []
    t.mock.method(agentApi, 'getAgents', () => new Promise((resolve) => directory.push(resolve)))
    t.mock.method(knowledgeBaseApi, 'getAccessibleKnowledgeBases', () => new Promise((resolve) => knowledge.push(resolve)))
    t.mock.method(toolApi, 'getTools', () => new Promise((resolve) => tools.push(resolve)))
    store.reset()
    const oldUser = store.initialize()
    store.reset()
    const newUser = store.initialize()
    assert.equal(directory.length, 2, '新身份必须请求自己的目录')
    directory[0]({ agents: [{ id: 'old-user-agent', agent_id: 'old-user-agent' }] })
    knowledge[0]({ knowledge_bases: [{ id: 'old-user-kb' }] })
    tools[0]({ data: [{ name: 'old-user-tool' }] })
    await oldUser
    assert.deepEqual(store.agents, [])
    assert.deepEqual(store.availableKnowledgeBases, [])
    assert.deepEqual(store.toolMetadata, [])
    assert.equal(store.isInitialized, false)
    let joinedReady = false
    const joined = store.initialize().then(() => { joinedReady = true })
    await Promise.resolve()
    assert.equal(directory.length, 2, '旧请求 finally 不得丢失新请求的 Owner')
    assert.equal(joinedReady, false)
    directory[1]({ agents: [] })
    knowledge[1]({ knowledge_bases: [] })
    tools[1]({ data: [] })
    await Promise.all([newUser, joined])
    assert.equal(store.isInitialized, true)

    let finishDetail
    t.mock.method(agentApi, 'getAgentDetail', () => new Promise((resolve) => { finishDetail = resolve }))
    const oldSelection = store.selectAgent('old-user-agent')
    store.reset()
    finishDetail({ agent: { id: 'old-user-agent', config_json: { context: { model: 'old-model' } } } })
    await oldSelection
    assert.deepEqual(store.agentDetails, {})
    assert.equal(store.selectedAgentId, null)
    assert.deepEqual(store.agentConfig, {})
  } finally {
    disposePinia(pinia)
    await server.close()
    delete globalThis.localStorage
  }
})
