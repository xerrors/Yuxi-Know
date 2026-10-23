export const canMutateKnowledgeFiles = ({ readonly, locked, filtered }) =>
  !readonly && !locked && !filtered

export const canDragKnowledgeFile = ({ enabled, record, breadcrumbs, files }) =>
  Boolean(
    enabled &&
    record &&
    (breadcrumbs.slice(0, -1).some((item) => !item.dropDisabled) ||
      files.some((file) => file.is_folder && file.file_id !== record.file_id))
  )

export const canDropKnowledgeFileIntoFolder = (record, target) =>
  Boolean(record && target?.is_folder && target.file_id !== record.file_id)
