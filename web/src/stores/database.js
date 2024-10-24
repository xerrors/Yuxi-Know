import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useDatabaseStore = defineStore('database', () => {
  const db = ref({})
  function setDatabase(newDatabase) {
    db.value = newDatabase
  }

  function refreshDatabase() {
    fetch('/api/data').then(res => res.json()).then(data => {
      console.log("database", data)
      setDatabase(data.databases)
    })
  }

  return { db, setDatabase, refreshDatabase }
})