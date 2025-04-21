---
name: 提交一个BUG或者报错
about: 无法启动、无法回答、后端报错等等
title: 'Error: '
labels: bug
assignees: xerrors
body:
- type: textarea
  id: repro
  attributes:
    label: Reproduction steps
    description: "描述一下问题"
    value: |
---

1️⃣ 描述一下问题
> 简单描述一下




2️⃣ 报错日志

请运行以下命令，并提供部分相关日志：

```sh
docker logs --tail=100 api-dev
```

3️⃣ 相关截图




#️⃣ 其他相关信息


✅ 如果问题与模型调用相关，请尝试切换到其他在线模型
