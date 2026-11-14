export interface Thought { id: string; text: string; source?: string; radius?: number; x?: number; y?: number; generated?: boolean; parents?: string[] }
export interface Options { items?: Thought[]; maxDpr?: number; speed?: number; motionRate?: number; onMerge?: (a: Thought,b: Thought)=>Thought|Promise<Thought>; onSelect?: (item: Thought)=>void; onChange?: (items: Thought[])=>void; onError?: (error: unknown)=>void }
export interface Instance { focus(id:string):boolean; closeFocus():void; setMotionRate(rate:number):void; seekMerge(progress:number):boolean; merge(a:string,b:string):Promise<void>; setItems(items:Thought[]):void; getItems():Thought[]; pause():void; resume():void; undo():boolean; getStats():{renderer:string;count:number;reducedMotion:boolean;mergeProgress:number|null;averageFps:number;busy:boolean;focusedId:string|null}; destroy():void }
export function create(host:HTMLElement|string, options?:Options):Instance;
export as namespace ThoughtBubbles;

