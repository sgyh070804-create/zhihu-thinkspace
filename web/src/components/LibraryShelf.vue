<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import SpaceIcon from "./SpaceIcon.vue";
import { wheelPixels } from "../workspace-navigation";
import "../library-shelf.css";

interface Book { id: string; title: string; subtitle: string }
const props = defineProps<{ books: Book[]; openId?: string; loading: boolean; emptyLabel: string }>();
const emit = defineEmits<{ open: [id: string] }>();
const rail = ref<HTMLElement>();
const slots = computed(() => [
  ...props.books,
  ...Array.from({ length: Math.max(0, 8 - props.books.length) }, (_, index) => ({
    id: `blank-${index}`, title: "", subtitle: "",
  })),
]);
const cursor = ref(0);
let wheelOffset = 0, lastWheel = -Infinity, nextWheel = 0, scrollFrame = 0;

function centerBook() {
  const track = rail.value;
  const item = track?.children.item(cursor.value) as HTMLElement | null;
  if (!track || !item) return;
  const left = item.offsetLeft + item.offsetWidth / 2 - track.clientWidth / 2;
  track.scrollTo({ left, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
}

function select(index: number, center = true) {
  cursor.value = Math.min(slots.value.length - 1, Math.max(0, index));
  if (!center) return;
  cancelAnimationFrame(scrollFrame);
  scrollFrame = requestAnimationFrame(centerBook);
}

function onWheel(event: WheelEvent) {
  if (event.ctrlKey || event.metaKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
  const delta = wheelPixels(event, rail.value?.clientWidth || 1);
  if (!delta) return;
  const atEnd = delta > 0 ? cursor.value >= slots.value.length - 1 : cursor.value === 0;
  if (atEnd) return;
  event.preventDefault();
  const now = performance.now();
  if (now - lastWheel > 155 || Math.sign(wheelOffset) !== Math.sign(delta)) wheelOffset = 0;
  lastWheel = now;
  if (now < nextWheel) return;
  wheelOffset += delta;
  if (Math.abs(wheelOffset) < 34) return;
  select(cursor.value + Math.sign(wheelOffset));
  wheelOffset = 0; nextWheel = now + 145;
}

function open(book: Book, index: number) {
  select(index);
  emit("open", book.id);
}

function onKey(event: KeyboardEvent) {
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    select(cursor.value + (event.key === "ArrowRight" ? 1 : -1));
    // Keep keyboard focus on the shelf so Enter opens the current selection.
    rail.value?.focus({ preventScroll: true });
  } else if (event.key === "Enter" && event.target === rail.value) {
    const book = props.books[cursor.value];
    if (book) open(book, cursor.value);
  }
}

watch(() => props.openId, async id => {
  if (!id) return;
  const index = props.books.findIndex(book => book.id === id);
  if (index < 0) return;
  await nextTick();
  select(index);
}, { immediate: true });
watch(() => slots.value.length, length => {
  if (cursor.value >= length) select(length - 1);
});
onBeforeUnmount(() => cancelAnimationFrame(scrollFrame));
</script>

<template>
  <section class="library-shelf" data-workspace-wheel="local" aria-label="资料书架">
    <div class="shelf-top">
      <p v-if="loading" role="status">正在读取资料…</p>
      <p v-else-if="!books.length">{{ emptyLabel }}</p>
      <p v-else>将鼠标移到书架上，滚动选择，点击打开。</p>
      <div class="shelf-controls">
        <button type="button" aria-label="上一本" :disabled="cursor === 0"
          @click="select(cursor - 1)"><SpaceIcon name="left" /></button>
        <button type="button" aria-label="下一本" :disabled="cursor >= slots.length - 1"
          @click="select(cursor + 1)"><SpaceIcon name="right" /></button>
      </div>
    </div>
    <div ref="rail" class="shelf-track" tabindex="0" aria-label="书架，左右键选书，回车打开"
      @wheel="onWheel" @keydown="onKey">
      <div v-for="(book, index) in slots" :key="book.id" class="shelf-slot"
        :class="{ 'is-current': cursor === index, 'is-empty': !book.title }">
        <button v-if="book.title" type="button" class="shelf-book" :aria-label="`打开${book.title}`"
          :aria-expanded="openId === book.id" @focus="select(index, false)" @click="open(book, index)">
          <span class="shelf-spine-title">{{ book.title }}</span>
          <span class="shelf-spine-band" aria-hidden="true"></span>
        </button>
        <span v-else class="shelf-book shelf-placeholder" aria-hidden="true"></span>
      </div>
    </div>
    <div class="shelf-ledge" aria-hidden="true"></div>
    <p class="shelf-caption" aria-live="polite">
      <template v-if="books[cursor]"><strong>{{ books[cursor].title }}</strong><span>{{ books[cursor].subtitle }}</span></template>
      <template v-else>空白书位</template>
    </p>
  </section>
</template>
