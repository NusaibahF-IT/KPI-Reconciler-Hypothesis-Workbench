<template>
  <section class="card-bento p-6 md:p-7">
    <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-5">
      <div>
        <span class="sticker mb-2">{{ t.step1Badge }}</span>
        <h2 class="text-xl md:text-2xl font-extrabold text-tx">{{ t.step1Title }}</h2>
        <p class="text-xs md:text-sm text-tx/75 mt-1">{{ t.step1Desc }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2.5">
        <button
          v-if="uploadLocked && ownerUnlocked"
          type="button"
          class="btn btn-outline text-xs py-1.5 px-3"
          @click="$emit('lock-owner')"
        >
          {{ t.ownerUnlockedLock }}
        </button>
        <span v-if="loading" class="text-xs font-mono font-bold text-act animate-pulse">
          {{ t.runningScan }}
        </span>
      </div>
    </div>

    <div v-if="samples.length > 0" class="mb-5 pb-5 border-b border-line">
      <span class="text-xs font-extrabold uppercase tracking-wider text-tx/70 block mb-2.5">
        {{ t.quickLoad }}
      </span>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <button
          v-for="s in samples"
          :key="s.id"
          type="button"
          :disabled="loading"
          class="text-left p-4 rounded-xl border transition-all"
          :class="activeSampleId === s.id ? 'border-ink bg-field/20 shadow-sticker' : 'border-line bg-canvas/60 hover:border-tx/40'"
          @click="$emit('load-sample', s.id)"
        >
          <div class="font-bold text-sm text-tx">{{ s.label }}</div>
          <div class="text-xs text-tx/70 mt-1">{{ s.description }}</div>
        </button>
      </div>
    </div>

    <!-- Custom Upload Form (Unlocked) OR Public Demo Lock -->
    <form v-if="canUpload" class="grid grid-cols-1 md:grid-cols-3 gap-4 items-end" @submit.prevent="submitUpload">
      <label class="block text-xs">
        <span class="font-bold text-tx block mb-1">{{ t.quantLabel }}</span>
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          class="block w-full text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded-full file:border file:border-ink file:text-xs file:font-bold file:bg-field file:text-ink cursor-pointer"
          @change="quantFile = $event.target.files?.[0] || null"
        />
      </label>

      <label class="block text-xs">
        <span class="font-bold text-tx block mb-1">{{ t.sentimentLabel }}</span>
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          class="block w-full text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded-full file:border file:border-line file:text-xs file:font-bold file:bg-canvas file:text-tx cursor-pointer"
          @change="sentimentFile = $event.target.files?.[0] || null"
        />
      </label>

      <label class="block text-xs">
        <span class="font-bold text-tx block mb-1">{{ t.snapshotLabel }}</span>
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          class="block w-full text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded-full file:border file:border-line file:text-xs file:font-bold file:bg-canvas file:text-tx cursor-pointer"
          @change="snapshotFile = $event.target.files?.[0] || null"
        />
      </label>

      <div class="md:col-span-3 flex justify-end">
        <button
          type="submit"
          :disabled="!quantFile || loading"
          class="btn btn-primary text-xs py-2 px-5 disabled:opacity-40"
        >
          {{ t.analyzeBtn }}
        </button>
      </div>
    </form>

    <div
      v-else
      class="border-2 border-dashed border-line rounded-bento p-5 bg-canvas/60 flex flex-col md:flex-row md:items-center justify-between gap-4"
    >
      <div class="space-y-1">
        <span class="inline-block px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-sun/25 text-tx border border-sun/60">
          {{ t.demoBadge }}
        </span>
        <p class="text-xs md:text-sm font-semibold text-tx">{{ t.demoDesc }}</p>
        <p v-if="unlockError" class="text-xs font-semibold text-mag">{{ unlockError }}</p>
      </div>

      <form class="flex items-center gap-2 shrink-0" @submit.prevent="submitUnlock">
        <input
          v-model="codeInput"
          type="password"
          :placeholder="t.unlockPlaceholder"
          class="px-3.5 py-2 rounded-full border border-line bg-card text-xs font-mono text-tx w-44 focus:outline-none focus:border-ink"
        />
        <button type="submit" :disabled="unlocking || !codeInput.trim()" class="btn btn-primary text-xs py-2 px-4 disabled:opacity-40">
          {{ unlocking ? t.verifyingBtn : t.unlockBtn }}
        </button>
      </form>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  samples: { type: Array, default: () => [] },
  activeSampleId: { type: String, default: null },
  loading: { type: Boolean, default: false },
  t: { type: Object, required: true },
  uploadLocked: { type: Boolean, default: false },
  ownerUnlocked: { type: Boolean, default: false },
  unlocking: { type: Boolean, default: false },
  unlockError: { type: String, default: '' }
})

const emit = defineEmits(['load-sample', 'upload-files', 'unlock-owner', 'lock-owner'])

const quantFile = ref(null)
const sentimentFile = ref(null)
const snapshotFile = ref(null)
const codeInput = ref('')

const canUpload = computed(() => !props.uploadLocked || props.ownerUnlocked)

function submitUpload() {
  if (!quantFile.value || !canUpload.value) return
  emit('upload-files', {
    quantFile: quantFile.value,
    sentimentFile: sentimentFile.value,
    snapshotFile: snapshotFile.value
  })
}

function submitUnlock() {
  if (!codeInput.value.trim()) return
  emit('unlock-owner', codeInput.value.trim())
  codeInput.value = ''
}
</script>
