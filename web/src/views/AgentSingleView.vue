<template>
  <div class="agent-single-view">
    <AgentChatComponent :agent-id="agentId" />
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import AgentChatComponent from '@/components/AgentChatComponent.vue';

const route = useRoute();
const agentId = computed(() => route.params.agent_id);
</script>

<style lang="less" scoped>
.agent-single-view {
  width: 100%;
  height: 100vh;
  overflow: hidden;
}
</style>


