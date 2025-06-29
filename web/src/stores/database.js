import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { knowledgeBaseApi } from '@/apis/admin_api'

export const useDatabaseStore = defineStore('database', () => {
  const db = ref({})
  function setDatabase(newDatabase) {
    db.value = newDatabase
  }

  async function refreshDatabase() {
    const res = await knowledgeBaseApi.getDatabases()
    console.log("database", res)
    setDatabase(res.databases)
  }

  return { db, setDatabase, refreshDatabase }
})