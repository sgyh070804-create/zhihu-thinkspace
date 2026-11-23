export const workspacePages = [
  { path: "/", label: "首页" },
  { path: "/library", label: "资料库" },
  { path: "/space", label: "思考空间" },
];

export function workspaceIndex(path: string): number {
  return workspacePages.findIndex(page => page.path === path);
}

export function wheelPixels(event: Pick<WheelEvent, "deltaY" | "deltaMode">, pageHeight: number): number {
  return event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? pageHeight : 1);
}

// Consume at most one step per gesture, including its trackpad momentum.
export function createWheelStep(threshold = 72, idleMs = 170) {
  let last = -Infinity, amount = 0, consumed = false;
  return (delta: number, now: number) => {
    if (now - last > idleMs) { amount = 0; consumed = false; }
    last = now;
    if (consumed) return 0;
    if (Math.sign(amount) !== Math.sign(delta)) amount = 0;
    amount += delta;
    if (Math.abs(amount) < threshold) return 0;
    consumed = true;
    return Math.sign(amount);
  };
}
