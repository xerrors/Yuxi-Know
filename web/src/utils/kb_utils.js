
import { Database, Zap } from 'lucide-vue-next';
import { ThunderboltOutlined } from '@ant-design/icons-vue';

export const getKbTypeLabel = (type) => {
  const labels = {
    lightrag: 'LightRAG',
    chroma: 'Chroma',
    milvus: 'Milvus'
  };
  return labels[type] || type;
};

export const getKbTypeIcon = (type) => {
  const icons = {
    lightrag: Database,
    chroma: Zap,
    milvus: ThunderboltOutlined
  };
  return icons[type] || Database;
};

export const getKbTypeColor = (type) => {
  const colors = {
    lightrag: 'purple',
    chroma: 'orange',
    milvus: 'red'
  };
  return colors[type] || 'blue';
};
