<script setup lang="ts">
defineProps<{ name: string }>();
</script>
<template>
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="name === 'bubbles'"><circle cx="9" cy="10" r="6"/><circle cx="17" cy="17" r="4"/><path d="M6 9a3 3 0 0 1 3-3"/></template>
    <template v-else-if="name === 'search'"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></template>
    <template v-else-if="name === 'pause'"><path d="M9 6v12M15 6v12"/></template>
    <template v-else-if="name === 'play'"><path d="m9 5 10 7-10 7z"/></template>
    <template v-else-if="name === 'close'"><path d="m6 6 12 12M18 6 6 18"/></template>
    <template v-else-if="name === 'link'"><path d="m10 13 4-4M9 16l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m0 10a4 4 0 0 0 6 0l4-4a4 4 0 0 0-6-6l-1 1" transform="translate(1 1) scale(.9)"/></template>
    <template v-else-if="name === 'refresh'"><path d="M20 11a8 8 0 1 0-2 6M20 5v6h-6"/></template>
    <template v-else-if="name === 'undo'"><path d="m8 4-5 5 5 5M4 9h10a6 6 0 0 1 0 12"/></template>
    <template v-else-if="name === 'download'"><path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4"/></template>
    <template v-else-if="name === 'left'"><path d="m14 6-6 6 6 6"/></template>
    <template v-else-if="name === 'right'"><path d="m10 6 6 6-6 6"/></template>
    <template v-else-if="name === 'spark'"><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4z"/></template>
  </svg>
</template>
