<template>
  <div class="space-y-6">
    <!-- Guardrails Strip -->
    <section class="card-bento p-5 flex flex-wrap items-center justify-between gap-4 bg-sun/15 border-sun/50">
      <div class="space-y-1">
        <span class="text-xs font-extrabold uppercase tracking-wider text-tx">
          Gate 2 · Candidate Business Hypotheses (Human-in-the-Loop)
        </span>
        <p class="text-xs text-tx/80">
          Hypotheses are generated strictly as <strong>candidates to investigate</strong> — business conclusions and recommendations stay with the Data Analyst.
        </p>
      </div>

      <div class="flex flex-wrap gap-2 text-[11px] font-mono">
        <span v-if="report.date_coverage?.has_date_col" class="chip bg-card">
          Period: {{ report.date_coverage.min_date }} → {{ report.date_coverage.max_date }} ({{ report.date_coverage.active_days }} active days)
        </span>
        <span class="chip bg-card">
          Target KPI: {{ report.target_metric || 'N/A' }}
        </span>
        <span v-if="report.active_flag_col" class="chip bg-card">
          Outcome Flag: {{ report.active_flag_col }}
        </span>
      </div>
    </section>

    <!-- Domain-Agnostic Column Role Selector -->
    <section class="card-bento p-4 flex flex-wrap items-end gap-4 text-xs">
      <label class="block">
        <span class="font-bold text-tx/75 block mb-1">Target Numeric Metric</span>
        <select
          v-model="localTargetMetric"
          class="px-3 py-1.5 rounded-lg border border-line bg-canvas text-tx font-mono text-xs"
        >
          <option v-for="col in numericCols" :key="col" :value="col">{{ col }}</option>
        </select>
      </label>

      <label class="block">
        <span class="font-bold text-tx/75 block mb-1">Binary Outcome / Flag Column</span>
        <select
          v-model="localFlagCol"
          class="px-3 py-1.5 rounded-lg border border-line bg-canvas text-tx font-mono text-xs"
        >
          <option value="__none__">(None)</option>
          <option v-for="col in binaryFlagCols" :key="col" :value="col">{{ col }}</option>
        </select>
      </label>

      <button
        type="button"
        :disabled="reanalyzing"
        class="btn btn-mint text-xs py-1.5 px-4"
        @click="$emit('change-columns', { targetMetric: localTargetMetric, flagCol: localFlagCol })"
      >
        {{ reanalyzing ? 'Re-analyzing...' : 'Re-Analyze Metric ↻' }}
      </button>
    </section>

    <!-- Category Filters -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap gap-2">
        <button
          v-for="cat in categories"
          :key="cat"
          type="button"
          class="btn text-xs py-1.5 px-3.5"
          :class="selectedCategory === cat ? 'btn-primary' : 'btn-outline'"
          @click="selectedCategory = cat"
        >
          {{ cat }}
        </button>
      </div>
      <span class="text-xs font-mono text-tx/70">
        Approved: <strong>{{ acceptedCount }}</strong> / {{ hypotheses.length }}
      </span>
    </div>

    <!-- Hypothesis Cards -->
    <div v-if="filteredHypotheses.length === 0" class="card-bento p-8 text-center text-sm text-tx/70">
      No candidate hypotheses matched this filter.
    </div>

    <div v-else class="grid grid-cols-1 gap-4">
      <article
        v-for="h in filteredHypotheses"
        :key="h.hypothesis_id"
        class="card-bento p-6 space-y-4 border-l-4"
        :class="cardBorderClass(h.analyst_status)"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-mono text-xs font-extrabold text-tx/70">{{ h.hypothesis_id }}</span>
              <span class="chip bg-field/20 border-field/50 text-tx">{{ h.category }}</span>
              <span class="chip font-mono">{{ h.dimension }} = {{ h.segment }}</span>
              <span
                class="px-2 py-0.5 rounded-full text-[10px] font-extrabold"
                :class="h.signal_strength === 'Strong' ? 'bg-mag/15 text-mag' : 'bg-sun/30 text-ink'"
              >
                {{ h.signal_strength }} Signal
              </span>
              <span
                v-if="h.sample_size_flag === 'LOW_SAMPLE_WARNING'"
                class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-mag text-white"
              >
                Low Sample (n={{ h.sample_size }})
              </span>
              <span v-else class="text-[11px] font-mono text-tx/60">n={{ h.sample_size }}</span>
            </div>
          </div>

          <!-- Analyst Review Buttons -->
          <div class="flex flex-wrap gap-1.5">
            <button
              type="button"
              class="btn text-[11px] py-1 px-3"
              :class="h.analyst_status === 'accepted' ? 'btn-mint' : 'btn-outline'"
              @click="setStatus(h, 'accepted')"
            >
              ✓ Accept
            </button>
            <button
              type="button"
              class="btn text-[11px] py-1 px-3"
              :class="h.analyst_status === 'needs_more_data' ? 'bg-sun text-ink border-ink' : 'btn-outline'"
              @click="setStatus(h, 'needs_more_data')"
            >
              ? Verify More
            </button>
            <button
              type="button"
              class="btn text-[11px] py-1 px-3"
              :class="h.analyst_status === 'rejected' ? 'bg-mag text-white border-ink' : 'btn-outline'"
              @click="setStatus(h, 'rejected')"
            >
              ✕ Reject
            </button>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div class="p-3.5 rounded-xl bg-canvas border border-line">
            <strong class="block uppercase text-[10px] tracking-wider text-tx/65 mb-1">1. Observed Signal (Fact)</strong>
            <p class="text-tx leading-relaxed">{{ h.observed_signal }}</p>
          </div>

          <div class="p-3.5 rounded-xl bg-field/10 border border-field/40">
            <strong class="block uppercase text-[10px] tracking-wider text-tx/65 mb-1">2. Candidate Hypothesis</strong>
            <p class="text-tx leading-relaxed font-medium">{{ h.candidate_hypothesis }}</p>
          </div>

          <div class="p-3.5 rounded-xl bg-canvas border border-line">
            <strong class="block uppercase text-[10px] tracking-wider text-tx/65 mb-1">3. Alternative / Confounding Factors</strong>
            <ul class="list-disc pl-4 space-y-1 text-tx/85">
              <li v-for="(alt, i) in h.alternative_explanations" :key="i">{{ alt }}</li>
            </ul>
          </div>

          <div class="p-3.5 rounded-xl bg-canvas border border-line">
            <strong class="block uppercase text-[10px] tracking-wider text-tx/65 mb-1">4. Next Verification Checks Needed</strong>
            <ul class="list-disc pl-4 space-y-1 text-tx/85">
              <li v-for="(chk, i) in h.verification_checks_needed" :key="i">{{ chk }}</li>
            </ul>
          </div>
        </div>

        <div>
          <input
            v-model="h.analyst_note"
            type="text"
            placeholder="Add analyst verification note or business context (included in Insight Memo)..."
            class="w-full px-3.5 py-2 rounded-xl border border-line bg-canvas text-xs text-tx focus:outline-none focus:border-ink"
          />
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  report: { type: Object, required: true },
  hypotheses: { type: Array, default: () => [] },
  numericCols: { type: Array, default: () => [] },
  binaryFlagCols: { type: Array, default: () => [] },
  reanalyzing: { type: Boolean, default: false }
})

defineEmits(['change-columns'])

const localTargetMetric = ref('')
const localFlagCol = ref('__none__')
const selectedCategory = ref('ALL')

watch(
  () => props.report,
  (rep) => {
    localTargetMetric.value = rep?.target_metric || props.numericCols?.[0] || ''
    localFlagCol.value = rep?.active_flag_col || '__none__'
  },
  { immediate: true }
)

const categories = computed(() => {
  const set = new Set((props.hypotheses || []).map((h) => h.category))
  return ['ALL', ...Array.from(set)]
})

const filteredHypotheses = computed(() => {
  if (selectedCategory.value === 'ALL') return props.hypotheses
  return props.hypotheses.filter((h) => h.category === selectedCategory.value)
})

const acceptedCount = computed(() => props.hypotheses.filter((h) => h.analyst_status === 'accepted').length)

function setStatus(h, status) {
  h.analyst_status = h.analyst_status === status ? 'pending_review' : status
}

function cardBorderClass(status) {
  if (status === 'accepted') return 'border-l-act'
  if (status === 'needs_more_data') return 'border-l-sun'
  if (status === 'rejected') return 'border-l-mag opacity-65'
  return 'border-l-line'
}
</script>
