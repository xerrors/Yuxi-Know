<template>
  <div class="not-found">
    <h1>404 - 页面不存在</h1>
    <p>链接可能已失效，请检查地址或返回首页。</p>
    <router-link to="/" class="return-home">返回首页</router-link>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--gray-0);
  color: var(--color-text);
  text-align: center;
}

.not-found h1 {
  font-size: 2rem;
  margin-bottom: 1rem;
}

.not-found p {
  font-size: 1rem;
  color: var(--color-text-secondary);
  margin-bottom: 2rem;
}

.return-home {
  color: var(--main-color);
}
</style>
