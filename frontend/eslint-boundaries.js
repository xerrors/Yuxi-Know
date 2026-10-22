import path from 'node:path'

/** 按实际目标路径检查前端分层，覆盖别名、相对路径和动态导入。 */
export const frontendBoundaries = {
  meta: {
    type: 'problem',
    schema: [],
    messages: {
      upward: '{{source}} 不能依赖 {{target}}；把装配保留在 app/pages，把通用能力保留在 shared。',
      obsolete: '旧入口 {{target}} 已移除，请引用所属领域或 shared。',
      moduleEntry:
        '{{source}} 不能直达 {{target}}；请从 @/modules/{{module}} 或 @/modules/{{module}}/ui/**.vue 的公开入口导入。'
    }
  },
  create(context) {
    const filename = context.filename.replaceAll('\\', '/')
    const root = filename.lastIndexOf('/src/')
    const bareSource = root < 0 && filename.startsWith('src/')
    if (root < 0 && !bareSource) return {}
    const source = root >= 0 ? filename.slice(root + 5) : filename.slice(4)
    const sourcePath = path.posix.resolve('/src', source)

    /** 把别名、绝对路径和相对路径统一解析成 /src 下的虚拟路径。 */
    function resolveTarget(value) {
      if (value.startsWith('@/')) return path.posix.normalize('/src/' + value.slice(2))
      if (value.startsWith('/')) return path.posix.normalize(value)
      if (value.startsWith('.')) return path.posix.resolve(path.posix.dirname(sourcePath), value)
      return null
    }

    /** 拒绝跨越前端职责边界的导入。 */
    function check(node, value) {
      if (typeof value !== 'string') return
      const targetPath = resolveTarget(value)
      if (!targetPath || !targetPath.startsWith('/src/')) return
      const target = targetPath.slice(5).replace(/\/+$/, '')
      if (/^(components|composables|stores|utils|views|layouts|router)(\/|$)/.test(target)) {
        context.report({ node, messageId: 'obsolete', data: { target } })
        return
      }
      const upward =
        (source.startsWith('modules/') && /^(app|pages)(\/|$)/.test(target)) ||
        (source.startsWith('shared/') && /^(app|pages|modules|apis)(\/|$)/.test(target)) ||
        (source.startsWith('apis/') && /^(app|pages)(\/|$)/.test(target))
      if (upward) {
        context.report({ node, messageId: 'upward', data: { source, target } })
        return
      }
      const sourceModule = source.startsWith('modules/') ? source.split('/')[1] : null
      const targetModule = target.match(/^modules\/([^/]+)(?:\/|$)/)?.[1]
      const publicUi = target.startsWith(`modules/${targetModule}/ui/`) && target.endsWith('.vue')
      const allowedEntry =
        target === `modules/${targetModule}` ||
        target === `modules/${targetModule}/index` ||
        target === `modules/${targetModule}/index.js` ||
        publicUi
      if (sourceModule && targetModule && sourceModule !== targetModule && !allowedEntry) {
        context.report({
          node,
          messageId: 'moduleEntry',
          data: { source, target, module: targetModule }
        })
      }
    }
    return {
      ImportDeclaration: (node) => check(node.source, node.source.value),
      ExportNamedDeclaration: (node) => node.source && check(node.source, node.source.value),
      ExportAllDeclaration: (node) => check(node.source, node.source.value),
      ImportExpression: (node) => {
        const source = node.source
        const value =
          source.type === 'TemplateLiteral' && source.expressions.length === 0
            ? source.quasis[0].value.cooked
            : source.value
        check(source, value)
      }
    }
  }
}
