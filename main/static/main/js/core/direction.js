export function logicalScrollDelta(direction, isRtl, step) {
  return direction * step * (isRtl ? -1 : 1);
}
