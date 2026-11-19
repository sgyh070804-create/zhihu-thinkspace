<script setup lang="ts">
defineProps<{ name: string }>();
const paths: Record<string, string> = {
  branch: "M6 3v12a4 4 0 0 0 4 4h8M6 9h8a4 4 0 0 0 4-4V3M3 3h6M15 3h6M18 16v6",
  plus: "M12 5v14M5 12h14", minus: "M5 12h14", close: "m6 6 12 12M6 18 18 6",
  file: "M14 3H5v18h14V8l-5-5v5h5M8 13h8M8 17h6", check: "m5 12 4 4L19 6",
  compare: "M8 3v18M16 3v18M3 7h10M11 17h10", down: "m7 10 5 5 5-5",
  fit: "M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5", home: "m3 10 9-7 9 7v11H3ZM9 21v-8h6v8",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5", thought: "M7 16H4V4h16v12h-8l-5 5ZM8 8h8M8 12h5",
};
</script>
<template><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.branch" /></svg></template>
