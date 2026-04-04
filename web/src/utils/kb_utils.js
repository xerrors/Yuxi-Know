import { Database, Waypoints, DatabaseZap } from 'lucide-vue-next'

export const getKbTypeLabel = (type) => {
  const labels = {
    lightrag: 'LightRAG',
    milvus: 'CommonRAG',
    dify: 'Dify',
    test_pre: 'TestPre'
  }
  return labels[type] || type
}

export const getKbTypeIcon = (type) => {
  const icons = {
    lightrag: Waypoints,
    milvus: DatabaseZap,
    dify: Database,
    test_pre: Database
  }
  return icons[type] || Database
}

export const getKbTypeColor = (type) => {
  const colors = {
    lightrag: 'purple',
    milvus: 'red',
    dify: 'gold',
    test_pre: 'blue'
  }
  return colors[type] || 'blue'
}
