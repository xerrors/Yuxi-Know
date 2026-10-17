/**
 * 对话输入框草稿的本地存储与线程切换管理。
 *
 * 草稿按线程 ID 保存在 localStorage 中，刷新页面后仍可还原；
 * 新建但尚未创建线程的对话使用 DRAFT_THREAD_ID 作为临时标识，
 * 线程创建成功后由调用方清理临时草稿（内容已随消息发送）。
 */

const STORAGE_KEY_PREFIX = 'yuxi:thread-input-draft:'

// 新建对话尚未取得线程 ID 时的草稿标识
export const DRAFT_THREAD_ID = '__draft__'

/**
 * 创建基于 localStorage 的线程草稿存储。
 *
 * @param {Storage} storage 可注入的存储实现，默认使用全局 localStorage
 */
export const createThreadDraftStore = (storage = globalThis.localStorage) => {
  const keyOf = (threadId) => `${STORAGE_KEY_PREFIX}${threadId}`

  return {
    read(threadId) {
      try {
        return storage.getItem(keyOf(threadId)) || ''
      } catch {
        return ''
      }
    },
    // 空草稿直接清除对应缓存，避免无效条目持续累积
    write(threadId, text) {
      try {
        if (text) {
          storage.setItem(keyOf(threadId), text)
        } else {
          storage.removeItem(keyOf(threadId))
        }
      } catch {
        // 隐私模式或配额满时写入失败，草稿降级为仅会话内有效，不影响输入
      }
    },
    remove(threadId) {
      try {
        storage.removeItem(keyOf(threadId))
      } catch {
        // 同上，删除失败无需处理
      }
    }
  }
}

// 线程列表清理和当前编辑器共享同一个存储 Owner。
export const threadDraftStore = createThreadDraftStore()

/** 暂存入口文本，跨登录返回后只向新会话追加一次。 */
export function createEntryDraftHandoff(storage = globalThis.sessionStorage) {
  const key = 'yuxi:session-entry-draft'
  let pending = ''
  let consumed = false
  return {
    save(text) {
      pending = text
      consumed = false
      try {
        storage.setItem(key, text)
      } catch {
        // 存储不可用时仍支持当前页面内的路由交接。
      }
    },
    take() {
      if (consumed) return ''
      consumed = true
      let text = pending
      try {
        text = pending || storage.getItem(key) || ''
        storage.removeItem(key)
      } catch {
        // 仅消费当前页面中的待交接文本。
      }
      pending = ''
      return text
    }
  }
}

export const entryDraftHandoff = createEntryDraftHandoff()

/**
 * 创建绑定当前输入框的草稿会话，负责草稿与线程的对应关系。
 *
 * 内部维护当前草稿归属的 key，保证输入内容始终写入切换前的线程，
 * 不受 Vue watcher 批量刷新时序影响。
 *
 * @param {ReturnType<typeof createThreadDraftStore>} store 草稿存储
 * @param {string} initialThreadId 初始化时所在的线程 ID，可为空
 */
export const createThreadDraftSession = (store, initialThreadId = '') => {
  let draftKey = initialThreadId || DRAFT_THREAD_ID
  const drafts = new Map()

  return {
    // 输入变化时实时保存当前线程的草稿
    saveInput(text) {
      drafts.set(draftKey, text)
      store.write(draftKey, text)
    },
    // 切换线程：先保存旧线程草稿，再返回新线程（或新建对话）的草稿
    switchThread(threadId, currentText) {
      drafts.set(draftKey, currentText)
      store.write(draftKey, currentText)
      draftKey = threadId || DRAFT_THREAD_ID
      // 同线程的其他视图可以更新持久草稿，但不能覆盖本视图切换前的编辑。
      if (!drafts.has(draftKey)) drafts.set(draftKey, store.read(draftKey))
      return drafts.get(draftKey)
    },
    // 由草稿发送创建新线程后，清理新建对话的临时草稿，避免已发送文本被再次还原
    clearDraftThread() {
      drafts.delete(DRAFT_THREAD_ID)
      store.remove(DRAFT_THREAD_ID)
    }
  }
}
