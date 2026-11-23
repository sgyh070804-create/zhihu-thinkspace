<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import SpaceIcon from "./SpaceIcon.vue";
import { wheelPixels } from "../workspace-navigation";
import "../library-shelf.css";

interface Book { id: string; title: string; subtitle: string }
const props = defineProps<{ books: Book[]; openId?: string; loading: boolean }>();
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
let panFrame = 0, panSpeed = 0, lastPanTime = 0;

function reconcileCursor() {
  const track = rail.value;
  if (!track) return;
  const current = track.children.item(cursor.value) as HTMLElement | null;
  const first = track.children.item(0) as HTMLElement | null;
  const second = track.children.item(1) as HTMLElement | null;
  if (!current || !first || !second) return;

  const left = track.scrollLeft;
  const right = left + track.clientWidth;
  const center = current.offsetLeft + current.offsetWidth / 2;
  if (center >= left && center <= right) return;
  const pitch = second.offsetLeft - first.offsetLeft;
  if (pitch <= 0) return;
  const nearest = Math.round((left + track.clientWidth / 2 - first.offsetLeft - first.offsetWidth / 2) / pitch);
  select(nearest, false);
}

function stopPan() {
  cancelAnimationFrame(panFrame);
  panFrame = 0;
  panSpeed = 0;
  lastPanTime = 0;
  reconcileCursor();
}

function panShelf(time: number) {
  const track = rail.value;
  if (!track) { stopPan(); return; }
  const seconds = Math.min(32, lastPanTime ? time - lastPanTime : 16) / 1000;
  lastPanTime = time;
  track.scrollLeft += panSpeed * seconds;
  if (panSpeed < 0 ? track.scrollLeft <= 0 : track.scrollLeft >= track.scrollWidth - track.clientWidth - 1) {
    stopPan();
    return;
  }
  panFrame = requestAnimationFrame(panShelf);
}

function onPointerMove(event: PointerEvent) {
  if (event.pointerType !== "mouse" || event.buttons !== 0) return;
  const track = rail.value;
  if (!track || track.scrollWidth <= track.clientWidth) return;
  const bounds = track.getBoundingClientRect();
  const edge = Math.min(96, bounds.width * 0.18);
  const left = event.clientX - bounds.left;
  const right = bounds.right - event.clientX;
  const direction = left < edge ? -1 : right < edge ? 1 : 0;
  if (!direction || (direction < 0 ? track.scrollLeft <= 0 : track.scrollLeft >= track.scrollWidth - track.clientWidth - 1)) {
    if (panFrame) stopPan();
    return;
  }
  cancelAnimationFrame(scrollFrame);
  const depth = 1 - Math.max(0, Math.min(left, right)) / edge;
  panSpeed = direction * (130 + 530 * depth ** 2);
  if (!panFrame) panFrame = requestAnimationFrame(panShelf);
}

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
  if (panFrame) stopPan();
  if (event.ctrlKey || event.metaKey || event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
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
  if (event.target === rail.value && (event.key === "Home" || event.key === "End")) {
    event.preventDefault();
    stopPan();
    select(event.key === "Home" ? 0 : slots.value.length - 1);
    return;
  }
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    stopPan();
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
onBeforeUnmount(() => {
  cancelAnimationFrame(scrollFrame);
  cancelAnimationFrame(panFrame);
});
</script>

<template>
  <section class="library-shelf" data-workspace-wheel="local" aria-label="资料书架">
    <div class="shelf-top">
      <p v-if="loading" role="status">正在读取资料…</p>
      <div class="shelf-controls">
        <button type="button" aria-label="上一本" :disabled="cursor === 0"
          @click="select(cursor - 1)"><SpaceIcon name="left" /></button>
        <button type="button" aria-label="下一本" :disabled="cursor >= slots.length - 1"
          @click="select(cursor + 1)"><SpaceIcon name="right" /></button>
      </div>
    </div>
    <div ref="rail" class="shelf-track" tabindex="0" aria-label="书架，左右键选书，回车打开"
      @wheel="onWheel" @keydown="onKey" @pointermove="onPointerMove"
      @pointerleave="stopPan" @pointerdown="stopPan" @scrollend="reconcileCursor">
      <div v-for="(book, index) in slots" :key="book.id" class="shelf-slot"
        :class="{ 'is-current': cursor === index, 'is-empty': !book.title }">
        <button v-if="book.title" type="button" class="shelf-book" :aria-label="`打开${book.title}`" :title="book.title"
          :aria-expanded="openId === book.id" @focus="select(index, false)" @click="open(book, index)">
          <span class="shelf-spine-title">{{ book.title }}</span>
          <span class="shelf-spine-band" aria-hidden="true"></span>
        </button>
        <span v-else class="shelf-book shelf-placeholder" aria-hidden="true"></span>
      </div>
    </div>
    <div class="shelf-ledge" aria-hidden="true"></div>
    <p v-if="books.length" class="shelf-caption" aria-live="polite">
      <template v-if="books[cursor]"><strong>{{ books[cursor].title }}</strong><span>{{ books[cursor].subtitle }}</span></template>
    </p>
  </section>
</template>
