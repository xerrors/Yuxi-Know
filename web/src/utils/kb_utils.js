
export const getKbTypeLabel = (type) => {
  const labels = {
    lightrag: 'LightRAG',
    milvus: 'Milvus'
  };
  return labels[type] || type;
};

export const getKbTypeColor = (type) => {
  const colors = {
    lightrag: 'purple',
    milvus: 'red'
  };
  return colors[type] || 'blue';
};
