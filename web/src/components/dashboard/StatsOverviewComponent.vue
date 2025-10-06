<template>
  <div class="stats-overview-container">
    <div class="stats-grid">
      <div class="stat-card primary">
        <div class="stat-icon">
          <MessageCircle class="icon" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ basicStats?.total_conversations || 0 }}</div>
          <div class="stat-label">总对话数</div>
          <div class="stat-trend" v-if="basicStats?.conversation_trend">
            <TrendingUp v-if="basicStats.conversation_trend > 0" class="trend-icon up" />
            <TrendingDown v-else-if="basicStats.conversation_trend < 0" class="trend-icon down" />
            <span class="trend-text">{{ Math.abs(basicStats.conversation_trend) }}%</span>
          </div>
        </div>
      </div>

      <div class="stat-card success">
        <div class="stat-icon">
          <Activity class="icon" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ basicStats?.active_conversations || 0 }}</div>
          <div class="stat-label">活跃对话</div>
        </div>
      </div>

      <div class="stat-card info">
        <div class="stat-icon">
          <Mail class="icon" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ basicStats?.total_messages || 0 }}</div>
          <div class="stat-label">总消息数</div>
        </div>
      </div>

      <div class="stat-card warning">
        <div class="stat-icon">
          <Users class="icon" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ basicStats?.total_users || 0 }}</div>
          <div class="stat-label">用户数</div>
        </div>
      </div>

      <div class="stat-card secondary">
        <div class="stat-icon">
          <BarChart3 class="icon" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ basicStats?.feedback_stats?.total_feedbacks || 0 }}</div>
          <div class="stat-label">总反馈数</div>
        </div>
      </div>

      <div class="stat-card" :class="getSatisfactionClass()">
        <div class="stat-icon">
          <Heart class="icon" />
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ basicStats?.feedback_stats?.satisfaction_rate || 0 }}%</div>
          <div class="stat-label">满意度</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { MessageCircle, Activity, Mail, Users, BarChart3, Heart, TrendingUp, TrendingDown } from 'lucide-vue-next'

// Props
const props = defineProps({
  basicStats: {
    type: Object,
    default: () => ({})
  }
})

// Methods
const getSatisfactionClass = () => {
  const rate = props.basicStats?.feedback_stats?.satisfaction_rate || 0
  if (rate >= 80) return 'satisfaction-high'
  if (rate >= 60) return 'satisfaction-medium'
  return 'satisfaction-low'
}
</script>

<style lang="less" scoped>
// 使用 dashboard.css 中定义的样式，这里只需要导入
@import '@/assets/css/dashboard.css';
</style>
