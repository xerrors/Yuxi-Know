import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { databaseApi } from '@/apis/knowledge_api'

export const useDatabaseStore = defineStore('database', () => {
  const db = ref({})
  function setDatabase(newDatabase) {
    db.value = newDatabase
  }

  async function refreshDatabase() {
    const res = await databaseApi.getDatabases()
    console.log("database", res)
    setDatabase(res.databases)
  }

  return { db, setDatabase, refreshDatabase }
})