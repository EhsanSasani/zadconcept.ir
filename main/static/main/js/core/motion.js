const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

export function prefersReducedMotion() {
  return window.matchMedia?.(REDUCED_MOTION_QUERY).matches ?? false;
}

export function preferredScrollBehavior() {
  return prefersReducedMotion() ? "auto" : "smooth";
}

export function observeMotionPreference(callback) {
  const media = window.matchMedia?.(REDUCED_MOTION_QUERY);
  if (!media) return () => {};

  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}
