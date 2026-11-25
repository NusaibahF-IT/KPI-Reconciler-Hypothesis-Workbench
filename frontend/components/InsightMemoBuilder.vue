<template>
  <div class="card-bento p-6 space-y-5">
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h3 class="text-lg font-extrabold text-tx">Gate 3 · Analyst Decision &amp; 1-Page Insight Memo</h3>
        <p class="text-xs text-tx/70 mt-0.5">
          Only analyst-approved (or pending) hypotheses are exported — rejected hypotheses are excluded automatically.
        </p>
      </div>
      <button type="button" :disabled="exporting" class="btn btn-mint text-xs py-2 px-4" @click="exportMemo">
        {{ exporting ? 'Generating Memo...' : 'Export Insight Memo (.md) ↓' }}
      </button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <label class="block text-xs">
        <span class="font-bold text-tx block mb-1">Analyst Name</span>
        <input
          v-model="analystName"
          type="text"
          class="w-full px-3.5 py-2 rounded-xl border border-line bg-canvas text-xs text-tx"
        />
      </label>

      <label class="block text-xs">
        <span class="font-bold text-tx block mb-1">Proposed Actions (comma-separated)</span>
        <input
          v-model="actionsText"
          type="text"
          placeholder="e.g. Audit Fast Food prep SLA, Reconcile Marketplace filter"
          class="w-full px-3.5 py-2 rounded-xl border border-line bg-canvas text-xs text-tx"
        />
      </label>
    </div>

    <label class="block text-xs">
      <span class="font-bold text-tx block mb-1">Analyst Decision &amp; Executive Summary</span>
      <textarea
        v-model="decisionSummary"
        rows="4"
        placeholder="Write your evidence-based business conclusion and trade-offs here..."
        class="w-full px-3.5 py-2.5 rounded-xl border border-line bg-canvas text-xs text-tx"
      />
    </label>

    <div v-if="previewMd" class="p-4 rounded-xl bg-canvas border border-line">
      <div class="text-[11px] font-mono font-bold text-tx/65 mb-2">Generated Memo Preview</div>
      <pre class="whitespace-pre-wrap font-mono text-xs text-tx/90 leading-relaxed">{{ previewMd }}</pre>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  datasetName: { type: String, default: 'Dataset' },
  reconciliation: { type: Object, default: () => ({}) },
  hypotheses: { type: Array, default: () => [] },
  apiBase: { type: String, required: true }
})

const analystName = ref('Nusaibah Fathul Jannah')
const actionsText = ref('')
const decisionSummary = ref('')
const previewMd = ref('')
const exporting = ref(false)

async function exportMemo() {
  exporting.value = true
  try {
    const actions = actionsText.value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    const resp = await fetch(`${props.apiBase}/api/memo/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataset_name: props.datasetName,
        analyst_name: analystName.value,
        reconciliation: props.reconciliation,
        hypotheses: props.hypotheses,
        analyst_decision_summary: decisionSummary.value,
        recommended_actions: actions
      })
    })
    if (!resp.ok) throw new Error('Failed to generate Insight Memo.')
    const text = await resp.text()
    previewMd.value = text

    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'insight_memo.md'
    a.click()
    URL.revokeObjectURL(url)
  } finally {
    exporting.value = false
  }
}
</script>
