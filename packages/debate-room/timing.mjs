// Hidden tabs reset the timestamp in scene.js. Preserve elapsed time for visible
// low-FPS frames; Spring.step internally substeps at 8ms for stability.
// Discard the excess only after a genuine stall (>1 second), avoiding huge jumps.
export function frameDelta(raw){return Number.isFinite(raw)?Math.max(0,Math.min(raw,1.05)):0;}
