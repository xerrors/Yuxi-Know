<script setup>
const selected = defineModel({ default: 'container' })
</script>

<template>
  <div class="sandbox-setup">
    <fieldset aria-label="沙盒运行方式" class="choices">
      <label v-for="backend in ['container', 'cube']" :key="backend">
        <input
          v-model="selected"
          type="radio"
          name="sandbox-setup"
          :value="backend"
          :aria-controls="`setup-${backend}`"
        />
        <span>{{ backend === 'container' ? 'Container' : 'Cube' }}</span>
      </label>
    </fieldset>
    <section id="setup-container" v-show="selected === 'container'" aria-label="Container 初始化">
      <slot name="container" />
    </section>
    <section id="setup-cube" v-show="selected === 'cube'" aria-label="Cube 初始化">
      <slot name="cube" />
    </section>
  </div>
</template>

<style scoped>
.choices {
  display: flex;
  gap: 8px;
  min-width: 0;
  margin: 24px 0 16px;
  padding: 0;
  border: 0;
  border-bottom: 1px solid var(--vp-c-divider);
}

label {
  position: relative;
  cursor: pointer;
}

input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
}

span {
  display: block;
  padding: 12px 20px;
  border-bottom: 3px solid transparent;
  color: var(--vp-c-text-2);
  font-weight: 600;
}

input:checked + span {
  border-color: var(--vp-c-brand-1);
  color: var(--vp-c-brand-1);
}

input:focus-visible + span {
  outline: 2px solid var(--vp-c-brand-1);
  outline-offset: -2px;
}
</style>
