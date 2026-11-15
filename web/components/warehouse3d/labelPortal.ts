import { createRef, type RefObject } from "react";

/**
 * DOM layer for drei <Html> labels (set by WarehouseView). Passing a stable `portal` stops drei from
 * re-creating every label root when R3F connects its event source after mount.
 */
export const labelPortal = createRef<HTMLDivElement>() as RefObject<HTMLDivElement>;
