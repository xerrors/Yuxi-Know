import assert from 'node:assert/strict'
import test from 'node:test'

import {
  DRAFT_THREAD_ID,
  createThreadDraftStore,
  createThreadDraftSession,
  createEntryDraftHandoff
} from '../../src/modules/session/model/thread_draft.js'

// 构造可注入的内存存储，模拟 localStorage 行为
const createMemoryStorage = () => {
  const storage = new Map()
  return {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
    _raw: storage
  }
}

test('首页文本经过整页登录返回后仅交接一次，不改写会话草稿', () => {
  const storage = createMemoryStorage()
  const store = createThreadDraftStore(storage)
  store.write(DRAFT_THREAD_ID, '已有的新会话草稿')
  store.write('thread-a', '已有会话草稿')
  createEntryDraftHandoff(storage).save('第一行\n第二行：整理知识')
  const afterLogin = createEntryDraftHandoff(storage)
  assert.equal(afterLogin.take(), '第一行\n第二行：整理知识')
  assert.equal(afterLogin.take(), '')
  assert.equal(createEntryDraftHandoff(storage).take(), '')
  assert.equal(store.read(DRAFT_THREAD_ID), '已有的新会话草稿')
  assert.equal(store.read('thread-a'), '已有会话草稿')
})

test('保活首页再次提交相同内容仍构成新的单次草稿交接', () => {
  const handoff = createEntryDraftHandoff(createMemoryStorage())
  assert.equal(handoff.take(), '')
  handoff.save('再次提问')
  assert.equal(handoff.take(), '再次提问')
  assert.equal(handoff.take(), '')
  handoff.save('再次提问')
  assert.equal(handoff.take(), '再次提问')
  assert.equal(handoff.take(), '')
})

test('存储写入或删除失败时优先交接本次文本且不重复读取旧值', () => {
  const handoff = createEntryDraftHandoff({
    getItem: () => '未能删除的旧文本',
    setItem: () => {
      throw new Error('quota')
    },
    removeItem: () => {
      throw new Error('unavailable')
    }
  })
  handoff.save('本次输入')
  assert.equal(handoff.take(), '本次输入')
  assert.equal(handoff.take(), '')
})

test('sessionStorage 不可用时路由交接仍保留内存文本', () => {
  const brokenStorage = {
    getItem: () => {
      throw new Error('unavailable')
    },
    setItem: () => {
      throw new Error('unavailable')
    },
    removeItem: () => {
      throw new Error('unavailable')
    }
  }
  const handoff = createEntryDraftHandoff(brokenStorage)
  assert.equal(handoff.take(), '')
  handoff.save('问题仍保留')
  assert.equal(handoff.take(), '问题仍保留')
  assert.equal(handoff.take(), '')
})

test('切换线程时保存旧线程草稿并还原新线程草稿', () => {
  const store = createThreadDraftStore(createMemoryStorage())
  const session = createThreadDraftSession(store)

  // 在线程 A 输入后切换到线程 B：B 不显示 A 的草稿
  session.switchThread('thread-a', '')
  session.saveInput('A 的未发送文本')
  const restoredInB = session.switchThread('thread-b', 'A 的未发送文本')
  assert.equal(restoredInB, '')

  // 切回 A：A 的未发送文本完整恢复
  const restoredInA = session.switchThread('thread-a', '')
  assert.equal(restoredInA, 'A 的未发送文本')
})

test('新建对话草稿独立，不继承已有对话文本', () => {
  const store = createThreadDraftStore(createMemoryStorage())
  const session = createThreadDraftSession(store)

  session.switchThread('thread-a', '')
  session.saveInput('A 的未发送文本')

  // 新建对话（无线程 ID）使用独立草稿
  const draftRestored = session.switchThread('', 'A 的未发送文本')
  assert.equal(draftRestored, '')
  assert.equal(store.read(DRAFT_THREAD_ID), '')
})

test('草稿发送创建线程后清理新建对话草稿，仅清空当前对话', () => {
  const store = createThreadDraftStore(createMemoryStorage())
  const session = createThreadDraftSession(store)

  // 新建对话中输入待发送文本
  session.saveInput('待发送文本')
  // 发送后输入清空，草稿随输入清除
  session.saveInput('')
  assert.equal(store.read(DRAFT_THREAD_ID), '')

  // 场景二：切换发生在输入清空之前（发送流程内部先创建线程）
  const session2 = createThreadDraftSession(store)
  session2.saveInput('又一次待发送文本')
  session2.switchThread('thread-new', '又一次待发送文本')
  session2.clearDraftThread()
  session2.saveInput('')
  assert.equal(store.read(DRAFT_THREAD_ID), '')
  assert.equal(store.read('thread-new'), '')
})

test('发送清空输入时仅清空当前线程草稿，其他线程不受影响', () => {
  const store = createThreadDraftStore(createMemoryStorage())
  const session = createThreadDraftSession(store)

  session.switchThread('thread-a', '')
  session.saveInput('A 的草稿')
  session.switchThread('thread-b', 'A 的草稿')
  session.saveInput('B 的草稿')

  // 在线程 B 发送：仅 B 的草稿被清空
  session.saveInput('')
  assert.equal(store.read('thread-b'), '')
  assert.equal(store.read('thread-a'), 'A 的草稿')
})

test('异常切换回退后草稿不互相污染', () => {
  const store = createThreadDraftStore(createMemoryStorage())
  const session = createThreadDraftSession(store)

  session.switchThread('thread-a', '')
  session.saveInput('A 的草稿')

  // 切换到 B 后立即回退到 A（模拟 selectChat 失败恢复）
  session.switchThread('thread-b', 'A 的草稿')
  const restored = session.switchThread('thread-a', '')
  assert.equal(restored, 'A 的草稿')
  assert.equal(store.read('thread-b'), '')
})

test('删除当前线程后输入草稿被丢弃，不残留孤儿缓存', () => {
  const storage = createMemoryStorage()
  const store = createThreadDraftStore(storage)
  const session = createThreadDraftSession(store)

  session.switchThread('thread-a', '')
  session.saveInput('A 的草稿')
  assert.equal(store.read('thread-a'), 'A 的草稿')

  // 线程删除后切走：调用方传入空文本，旧线程草稿应被清除
  session.switchThread('', '')
  assert.equal(store.read('thread-a'), '')
})

test('空草稿写入时清除缓存，避免无效条目累积', () => {
  const storage = createMemoryStorage()
  const store = createThreadDraftStore(storage)

  store.write('thread-a', '文本')
  assert.equal(storage._raw.size, 1)
  store.write('thread-a', '')
  assert.equal(storage._raw.size, 0)
})

test('localStorage 不可用时草稿功能静默降级不抛错', () => {
  const brokenStorage = {
    getItem: () => {
      throw new Error('unavailable')
    },
    setItem: () => {
      throw new Error('unavailable')
    },
    removeItem: () => {
      throw new Error('unavailable')
    }
  }
  const store = createThreadDraftStore(brokenStorage)
  const session = createThreadDraftSession(store)

  assert.equal(store.read('thread-a'), '')
  assert.doesNotThrow(() => store.write('thread-a', '文本'))
  assert.doesNotThrow(() => store.remove('thread-a'))
  assert.doesNotThrow(() => {
    session.switchThread('thread-a', '文本')
    session.saveInput('文本')
    session.clearDraftThread()
  })
})

test('同一线程的两个视图切换回来各自恢复编辑内容', () => {
  const values = new Map()
  const store = {
    read: (id) => values.get(id) || '',
    write: (id, text) => values.set(id, text),
    remove: (id) => values.delete(id)
  }
  const page = createThreadDraftSession(store, 'thread')
  const panel = createThreadDraftSession(store, 'thread')
  page.saveInput('page draft')
  panel.saveInput('panel draft')
  page.switchThread('other', 'page draft')
  panel.saveInput('panel revised')
  assert.equal(page.switchThread('thread', ''), 'page draft')
  panel.switchThread('another', 'panel revised')
  page.saveInput('page revised')
  assert.equal(panel.switchThread('thread', ''), 'panel revised')
})
