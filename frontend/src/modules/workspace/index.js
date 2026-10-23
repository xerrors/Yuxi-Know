// 模块公开模型与用例入口；UI 组件见 ./ui/**/*.vue。
export {
  WORKSPACE_UPLOAD_MAX_FILES,
  buildFolderUploadBatches,
  collectFolderUploadEntries,
  validateFolderUploadEntries
} from './model/workspaceFolderUpload'
