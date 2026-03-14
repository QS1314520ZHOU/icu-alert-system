<template>
  <div class="bed-grid">
    <div
      v-for="patient in patients"
      :key="patient._id"
      :class="['bed-card', `bed-${patient.alertLevel || 'none'}`, { flash: patient.alertFlash }]"
    >
      <div class="bed-head">
        <div class="bed-no">{{ patient.hisBed || '--' }}床</div>
        <span :class="['lamp', `lamp-${patient.alertLevel || 'none'}`]"></span>
      </div>
      <div class="bed-name">{{ patient.name || '—' }}</div>
      <div class="bed-vitals">
        <div>HR <b>{{ patient.vitals?.hr ?? '—' }}</b></div>
        <div>SpO₂ <b>{{ patient.vitals?.spo2 ?? '—' }}</b></div>
        <div>RR <b>{{ patient.vitals?.rr ?? '—' }}</b></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  patients: any[]
}>()
</script>

<style scoped>
.bed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.bed-card {
  background: #0a111d;
  border: 1px solid #14243b;
  border-radius: 12px;
  padding: 10px;
}
.bed-card.flash { animation: flash-border 1.2s ease-in-out infinite; }
.bed-critical { border-color: #ef444433; }
.bed-warning { border-color: #f59e0b28; }
.bed-high { border-color: #f9731628; }
.bed-normal { border-color: #22c55e18; }
.bed-head { display: flex; justify-content: space-between; align-items: center; }
.bed-no { font-size: 20px; font-weight: 700; color: #60a5fa; }
.bed-name { font-size: 14px; margin: 6px 0; }
.bed-vitals {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  font-size: 11px;
  color: #94a3b8;
}
.bed-vitals b { color: #e2e8f0; }
.lamp { width: 8px; height: 8px; border-radius: 50%; }
.lamp-critical { background: #ef4444; box-shadow: 0 0 6px #ef4444; }
.lamp-warning { background: #f59e0b; box-shadow: 0 0 6px #f59e0b; }
.lamp-high { background: #f97316; box-shadow: 0 0 6px #f97316; }
.lamp-normal { background: #22c55e; }
.lamp-none { background: #334155; }

@keyframes flash-border {
  0%, 100% { box-shadow: 0 0 0 rgba(239, 68, 68, 0); }
  50% { box-shadow: 0 0 18px rgba(239, 68, 68, 0.35); }
}
</style>
