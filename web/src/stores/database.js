import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export const useDatabaseStore = defineStore('database', () => {
  const db = ref({})
  function setDatabase(newDatabase) {
    db.value = newDatabase
  }

  return { db, setDatabase }
})