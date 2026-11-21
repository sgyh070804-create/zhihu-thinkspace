import "../../packages/thought-bubbles/dist/bubble-physics.js";
import "../../packages/thought-bubbles/dist/thought-bubbles.js";
import "../../packages/thought-bubbles/dist/thought-bubbles.css";
import type * as Engine from "../../packages/thought-bubbles/dist/thought-bubbles";

export const bubbleEngine = (window as unknown as { ThoughtBubbles: typeof Engine }).ThoughtBubbles;
export type { Instance as BubbleScene, Thought } from "../../packages/thought-bubbles/dist/thought-bubbles";
