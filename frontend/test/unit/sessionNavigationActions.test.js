import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { ref } from 'vue'

const source = readFileSync(new URL('../../src/modules/session/ui/SessionNavigation.vue', import.meta.url), 'utf8')

/** 执行导航的实际动作，只替换外部请求与路由。 */
function action(start, end, dependencies) {
  const begin = source.indexOf(`const ${start} =`)
  const block = source.slice(begin, source.indexOf(`const ${end} =`, begin))
  return new Function(...Object.keys(dependencies), `${block}; return ${start}`)(...Object.values(dependencies))
}

test('旧账号归档响应不能将新账号的同名线程导航到空白页', async () => {
  let finish, navigations = 0
  const userStore = { userId: 'a' }
  const archive = action('handleArchiveChat', 'handleRenameChat', {
    userStore, route: { params: { thread_id: 'shared' } },
    chatThreadsStore: { archiveThread: () => new Promise(resolve => { finish = resolve }) },
    router: { replace: () => { navigations++ } }
  })
  const pending = archive('shared')
  userStore.userId = 'b'
  finish()
  await pending
  assert.equal(navigations, 0)
})

test('旧账号重命名响应不能改写新账号项目或解除其等待状态', async () => {
  let finish, replacements = 0
  const userStore = { userId: 'a' }, projectPendingId = ref(null)
  const rename = action('handleRenameProject', 'handleDeleteProject', {
    userStore, projectPendingId,
    projectApi: { renameProject: () => new Promise(resolve => { finish = resolve }) },
    projectsStore: { replaceProject: () => { replacements++ } },
    message: { success() { assert.fail('过期动作不应通知新账号成功') }, error() {} }
  })
  const pending = rename({ projectId: 'a-project', name: '新名称' })
  userStore.userId = 'b'
  projectPendingId.value = 'b-project'
  finish({ id: 'a-project' })
  await pending
  assert.equal(replacements, 0)
  assert.equal(projectPendingId.value, 'b-project')
})

test('删除项目排队期间切账号不能以新身份请求或解除新操作的等待状态', async () => {
  let queuedOperation, finishQueue, deletes = 0
  const userStore = { userId: 'a' }, projectPendingId = ref(null)
  // 文件末尾无下一个动作，以 script 结束标签限定实际函数。
  const start = source.indexOf('const handleDeleteProject =')
  const block = source.slice(start, source.indexOf('</script>', start))
  const dependencies = {
    userStore, projectPendingId,
    projectApi: { async deleteProject() { deletes++ } },
    chatThreadsStore: {
      withThreadListUpdate(operation) {
        queuedOperation = operation
        return new Promise(resolve => { finishQueue = resolve })
      },
      removeThreadsByProject() { assert.fail('过期动作不能清理当前账号线程') }
    },
    projectsStore: { removeProject() { assert.fail('过期动作不能清理当前账号项目') } },
    message: { success() { assert.fail('过期动作不应通知新账号成功') }, error() {} }
  }
  const remove = new Function(...Object.keys(dependencies), `${block}; return handleDeleteProject`)(...Object.values(dependencies))
  const pending = remove('a-project')
  userStore.userId = 'b'
  projectPendingId.value = 'b-project'
  finishQueue(await queuedOperation())
  await pending
  assert.equal(deletes, 0)
  assert.equal(projectPendingId.value, 'b-project')
})

test('项目新建路由等待期间切账号不能清除新账号的返回目标', async () => {
  let finish, selections = 0
  const userStore = { userId: 'a' }
  const create = action('handleCreateProjectChat', 'searchWorkspace', {
    userStore, projectPendingId: ref(null), threadCreationInFlight: ref(false),
    router: { push: () => new Promise(resolve => { finish = resolve }) },
    chatThreadsStore: { setCurrentThreadId() { selections++ } }
  })
  const pending = create('a-project')
  userStore.userId = 'b'
  finish()
  await pending
  assert.equal(selections, 0)
})

test('项目删除响应晚于账号切换时不能清除新账号线程或等待状态', async () => {
  let finish
  const userStore = { userId: 'a' }, projectPendingId = ref(null)
  const start = source.indexOf('const handleDeleteProject =')
  const block = source.slice(start, source.indexOf('</script>', start))
  const dependencies = {
    userStore, projectPendingId,
    projectApi: { deleteProject: () => new Promise(resolve => { finish = resolve }) },
    chatThreadsStore: {
      withThreadListUpdate: operation => operation(),
      removeThreadsByProject() { assert.fail('旧响应不能清理新账号线程') }
    },
    projectsStore: { removeProject() { assert.fail('旧响应不能清理新账号项目') } },
    message: { success() { assert.fail('旧响应不能通知新账号成功') }, error() {} }
  }
  const remove = new Function(...Object.keys(dependencies), `${block}; return handleDeleteProject`)(...Object.values(dependencies))
  const pending = remove('a-project')
  userStore.userId = 'b'
  projectPendingId.value = 'b-project'
  finish()
  await pending
  assert.equal(projectPendingId.value, 'b-project')
})
