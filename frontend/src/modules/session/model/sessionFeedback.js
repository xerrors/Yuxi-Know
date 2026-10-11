import { reactive } from 'vue'
import { defineStore } from 'pinia'
import { agentApi } from '@/apis'

/** 评价只按服务端已提交状态展示；读取不能覆盖较新的用户操作。 */
export const useSessionFeedbackStore = defineStore('sessionFeedback', () => {
  const entries = reactive({})
  const reads = new Map()
  let generation = 0

  function getEntry(threadId, runId) {
    const key = `${threadId}:${runId}`
    entries[key] ||= { record: null, loaded: false, loading: false, pending: false, error: '', draft: '', revision: 0 }
    return entries[key]
  }

  async function load(threadId, runIds, force = false) {
    if (reads.has(threadId)) await reads.get(threadId)
    const ids = [...new Set(runIds)].filter((id) => id && (force || !getEntry(threadId, id).loaded))
    if (!ids.length) return
    const current = generation
    const request = (async () => {
      for (let offset = 0; offset < ids.length; offset += 100) {
        if (current !== generation) return
        const batch = ids.slice(offset, offset + 100).filter((id) => !getEntry(threadId, id).pending)
        if (!batch.length) continue
        const targets = batch.map((id) => {
          const entry = getEntry(threadId, id)
          entry.loading = true
          return { id, entry, revision: entry.revision }
        })
        try {
          const page = await agentApi.getSessionFeedback(threadId, batch)
          if (current !== generation) return
          const records = new Map(page.items.map((record) => [record.run_id, record]))
          for (const { id, entry, revision } of targets) {
            if (entry.revision !== revision || entry.pending) continue
            entry.record = records.get(id) || null
            entry.loaded = true
            entry.error = ''
          }
        } catch (error) {
          for (const { entry, revision } of targets) {
            if (entry.revision === revision) entry.error = error.message || '反馈读取失败，请重试'
          }
        } finally {
          for (const { entry } of targets) entry.loading = false
        }
      }
    })()
    reads.set(threadId, request)
    try {
      await request
    } finally {
      if (reads.get(threadId) === request) reads.delete(threadId)
    }
  }

  async function save(threadId, turnId, runId, rating, reason) {
    const entry = getEntry(threadId, runId)
    if (entry.pending || !entry.loaded) return
    entry.pending = true
    entry.revision++
    entry.error = ''
    try {
      if (rating === null) {
        await agentApi.deleteUserFeedback(threadId, turnId, runId)
        entry.record = null
      } else {
        entry.record = await agentApi.putUserFeedback(threadId, turnId, { run_id: runId, rating, reason })
      }
      entry.draft = ''
      return true
    } catch (error) {
      entry.error = error.message || '反馈未保存，请重试'
      return false
    } finally {
      entry.pending = false
    }
  }

  function rate(threadId, turnId, runId, rating) {
    const current = getEntry(threadId, runId).record?.rating
    return save(threadId, turnId, runId, current === rating ? null : rating, null)
  }

  function saveReason(threadId, turnId, runId, reason = getEntry(threadId, runId).draft) {
    const entry = getEntry(threadId, runId)
    if (!entry.record) return
    return save(threadId, turnId, runId, entry.record.rating, reason)
  }

  function reset() {
    generation++
    for (const key of Object.keys(entries)) delete entries[key]
    reads.clear()
  }

  return { getEntry, load, rate, saveReason, reset }
})
