<script setup lang="ts">
// 四类统计卡片：PASS / FAIL / ERROR / BLOCKED。
import { computed } from 'vue'
import type { RunDetail } from '@/api/types'
import { OUTCOME_ORDER, OUTCOME_META } from '../outcomes'

const props = defineProps<{ detail: RunDetail }>()

const items = computed(() =>
  OUTCOME_ORDER.map((key) => ({
    key,
    count: props.detail.counts[key] ?? 0,
    meta: OUTCOME_META[key]
  }))
)

const total = computed(() => props.detail.results.length)
</script>

<template>
  <div class="outcome-stats">
    <div v-for="it in items" :key="it.key" class="stat" :style="{ borderColor: it.meta.color }">
      <div class="stat-count" :style="{ color: it.meta.color }">{{ it.count }}</div>
      <div class="stat-label" :style="{ color: it.meta.color }">{{ it.key }}</div>
    </div>
    <div class="stat total">
      <div class="stat-count">/ {{ total }}</div>
      <div class="stat-label">用例总数</div>
    </div>
  </div>
</template>

<style scoped>
.outcome-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.stat {
  min-width: 92px;
  padding: 14px 16px;
  border: 1px solid #e5e6eb;
  border-left: 4px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
}
.stat.total {
  border-left-color: #94a3b8;
}
.stat-count {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.1;
}
.stat-label {
  margin-top: 4px;
  font-size: 12px;
  letter-spacing: 0.04em;
}
</style>
