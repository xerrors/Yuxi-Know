import {
  apiAdminGet,
  apiSuperAdminDelete,
  apiSuperAdminGet,
  apiSuperAdminPost,
  apiSuperAdminPut
} from './base'

const BASE_URL = '/api/system/skills'

export const listSkills = async () => {
  return apiAdminGet(BASE_URL)
}

export const importSkillZip = async (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return apiSuperAdminPost(`${BASE_URL}/import`, formData)
}

export const listRemoteSkills = async (source) => {
  return apiSuperAdminPost(`${BASE_URL}/remote/list`, { source })
}

export const installRemoteSkill = async (payload) => {
  return apiSuperAdminPost(`${BASE_URL}/remote/install`, payload)
}

export const getSkillDependencyOptions = async () => {
  return apiSuperAdminGet(`${BASE_URL}/dependency-options`)
}

export const listBuiltinSkills = async () => {
  return apiSuperAdminGet(`${BASE_URL}/builtin`)
}

export const installBuiltinSkill = async (slug) => {
  return apiSuperAdminPost(`${BASE_URL}/builtin/${encodeURIComponent(slug)}/install`)
}

export const updateBuiltinSkill = async (slug, force = false) => {
  return apiSuperAdminPost(`${BASE_URL}/builtin/${encodeURIComponent(slug)}/update`, { force })
}

export const getSkillTree = async (slug) => {
  return apiSuperAdminGet(`${BASE_URL}/${encodeURIComponent(slug)}/tree`)
}

export const getSkillFile = async (slug, path) => {
  return apiSuperAdminGet(
    `${BASE_URL}/${encodeURIComponent(slug)}/file?path=${encodeURIComponent(path)}`
  )
}

export const createSkillFile = async (slug, payload) => {
  return apiSuperAdminPost(`${BASE_URL}/${encodeURIComponent(slug)}/file`, payload)
}

export const updateSkillFile = async (slug, payload) => {
  return apiSuperAdminPut(`${BASE_URL}/${encodeURIComponent(slug)}/file`, payload)
}

export const updateSkillDependencies = async (slug, payload) => {
  return apiSuperAdminPut(`${BASE_URL}/${encodeURIComponent(slug)}/dependencies`, payload)
}

export const deleteSkillFile = async (slug, path) => {
  return apiSuperAdminDelete(
    `${BASE_URL}/${encodeURIComponent(slug)}/file?path=${encodeURIComponent(path)}`
  )
}

export const exportSkill = async (slug) => {
  return apiSuperAdminGet(`${BASE_URL}/${encodeURIComponent(slug)}/export`, {}, 'blob')
}

export const deleteSkill = async (slug) => {
  return apiSuperAdminDelete(`${BASE_URL}/${encodeURIComponent(slug)}`)
}

export const skillApi = {
  listSkills,
  importSkillZip,
  listRemoteSkills,
  installRemoteSkill,
  getSkillDependencyOptions,
  listBuiltinSkills,
  installBuiltinSkill,
  updateBuiltinSkill,
  getSkillTree,
  getSkillFile,
  createSkillFile,
  updateSkillFile,
  updateSkillDependencies,
  deleteSkillFile,
  exportSkill,
  deleteSkill
}

export default skillApi
