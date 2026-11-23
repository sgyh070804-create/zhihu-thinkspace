<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { advancePendulum, initialState, lengths, timeStep } from "../double-pendulum";

type Point = { x: number; y: number };

const canvas = ref<HTMLCanvasElement>();
const sceneSize = 264;
const pivot = { x: sceneSize / 2, y: sceneSize / 2 };
const firstLength = lengths[0] * 62;
const secondLength = lengths[1] * 62;
const stepsPerSample = 4;
const trailLimit = 120;
const trail: Point[] = [];
let current = initialState;
let previous = initialState;
let sampleStep = 0;
let context: CanvasRenderingContext2D | null = null;
let sizeObserver: ResizeObserver | undefined;
let viewObserver: IntersectionObserver | undefined;
let motionPreference: MediaQueryList | undefined;
let frame = 0;
let lastTime: number | undefined;
let accumulator = 0;
let inView = true;

function endOfRod(origin: Point, length: number, angle: number): Point {
  return { x: origin.x + length * Math.sin(angle), y: origin.y + length * Math.cos(angle) };
}

function step() {
  previous = current;
  current = advancePendulum(current);
  sampleStep += 1;
  if (sampleStep < stepsPerSample) return;

  sampleStep = 0;
  const joint = endOfRod(pivot, firstLength, current.angle1);
  trail.push(endOfRod(joint, secondLength, current.angle2));
  if (trail.length > trailLimit) trail.shift();
}

function drawTrail(ctx: CanvasRenderingContext2D, tip: Point) {
  ctx.lineWidth = 1.4;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  const chunkSize = 10;
  for (let start = 0; start < trail.length - 1; start += chunkSize) {
    const end = Math.min(start + chunkSize, trail.length - 1);
    const freshness = end / (trail.length - 1);
    ctx.strokeStyle = `rgba(66, 110, 153, ${0.025 + 0.44 * freshness ** 2})`;
    ctx.beginPath();
    ctx.moveTo(trail[start].x, trail[start].y);
    for (let index = start + 1; index <= end; index += 1) {
      ctx.lineTo(trail[index].x, trail[index].y);
    }
    if (end === trail.length - 1) ctx.lineTo(tip.x, tip.y);
    ctx.stroke();
  }
}

function drawWeight(ctx: CanvasRenderingContext2D, point: Point, radius: number, edge: string) {
  const { x, y } = point;
  const halo = ctx.createRadialGradient(x, y, radius * 0.65, x, y, radius * 1.75);
  halo.addColorStop(0, "#527eaa42");
  halo.addColorStop(1, "#527eaa00");
  ctx.fillStyle = halo;
  const haloSize = radius * 1.75;
  ctx.fillRect(x - haloSize, y - haloSize, haloSize * 2, haloSize * 2);

  const glass = ctx.createRadialGradient(x - radius * 0.34, y - radius * 0.38, 0, x, y, radius);
  glass.addColorStop(0, "#ffffff");
  glass.addColorStop(0.36, "#edf7ff");
  glass.addColorStop(0.84, edge);
  glass.addColorStop(1, "#d3e8f8");
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, 2 * Math.PI);
  ctx.fillStyle = glass;
  ctx.fill();
  ctx.lineWidth = 0.8;
  ctx.strokeStyle = "#f5fbffcd";
  ctx.stroke();
}

function render(blend = 1) {
  const ctx = context;
  if (!ctx) return;

  const { width, height } = ctx.canvas;
  const scale = Math.min(width, height) / sceneSize;
  ctx.resetTransform();
  ctx.clearRect(0, 0, width, height);
  ctx.setTransform(scale, 0, 0, scale, (width - sceneSize * scale) / 2, (height - sceneSize * scale) / 2);

  const angle1 = previous.angle1 + (current.angle1 - previous.angle1) * blend;
  const angle2 = previous.angle2 + (current.angle2 - previous.angle2) * blend;
  const joint = endOfRod(pivot, firstLength, angle1);
  const tip = endOfRod(joint, secondLength, angle2);
  drawTrail(ctx, tip);

  ctx.beginPath();
  ctx.moveTo(pivot.x, pivot.y);
  ctx.lineTo(joint.x, joint.y);
  ctx.lineTo(tip.x, tip.y);
  ctx.strokeStyle = "#527898d0";
  ctx.lineWidth = 3.1;
  ctx.stroke();
  ctx.strokeStyle = "#edf7ffd0";
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(pivot.x, pivot.y, 12, 0, 2 * Math.PI);
  ctx.fillStyle = "#eff7ff4d";
  ctx.fill();
  ctx.strokeStyle = "#648aaa63";
  ctx.stroke();
  drawWeight(ctx, pivot, 4, "#779abc");
  drawWeight(ctx, joint, 9, "#8aa9c6");
  drawWeight(ctx, tip, 14, "#6c96bf");
}

function animate(time: number) {
  // Cap catch-up so a stalled frame does not trigger a burst of integration.
  accumulator += Math.min((time - (lastTime ?? time)) / 1000, 0.05) * 0.88;
  lastTime = time;
  while (accumulator >= timeStep) {
    step();
    accumulator -= timeStep;
  }
  render(accumulator / timeStep);
  frame = requestAnimationFrame(animate);
}

function stop() {
  cancelAnimationFrame(frame);
  frame = 0;
  lastTime = undefined;
}

function syncPlayback() {
  if (inView && !document.hidden && !motionPreference?.matches) {
    if (!frame) frame = requestAnimationFrame(animate);
  } else {
    stop();
  }
}

function fit(element: HTMLCanvasElement, width: number, height: number) {
  const density = Math.min(window.devicePixelRatio || 1, 2);
  element.width = Math.max(1, Math.round(width * density));
  element.height = Math.max(1, Math.round(height * density));
  render(frame ? accumulator / timeStep : 1);
}

onMounted(() => {
  const element = canvas.value;
  if (!element) return;
  context = element.getContext("2d");
  if (!context) return;

  // Start with a short history from the same simulation as the live trail.
  for (let index = 0; index < 96 * stepsPerSample; index += 1) step();
  previous = current;
  fit(element, element.clientWidth, element.clientHeight);
  motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
  motionPreference.addEventListener("change", syncPlayback);
  document.addEventListener("visibilitychange", syncPlayback);
  sizeObserver = new ResizeObserver(([{ contentRect }]) => fit(element, contentRect.width, contentRect.height));
  sizeObserver.observe(element);
  viewObserver = new IntersectionObserver(([entry]) => {
    inView = entry.isIntersecting;
    syncPlayback();
  });
  viewObserver.observe(element);
  syncPlayback();
});

onBeforeUnmount(() => {
  stop();
  sizeObserver?.disconnect();
  viewObserver?.disconnect();
  motionPreference?.removeEventListener("change", syncPlayback);
  document.removeEventListener("visibilitychange", syncPlayback);
});
</script>

<template>
  <canvas ref="canvas" class="hub-welcome-art" aria-hidden="true"></canvas>
</template>
