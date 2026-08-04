export function observeHorizontalSwipe(root, onSwipe, threshold = 48) {
  let startX = 0;
  let startY = 0;

  root.addEventListener(
    "touchstart",
    (event) => {
      const touch = event.changedTouches[0];
      startX = touch.clientX;
      startY = touch.clientY;
    },
    { passive: true },
  );

  root.addEventListener(
    "touchend",
    (event) => {
      const touch = event.changedTouches[0];
      const deltaX = touch.clientX - startX;
      const deltaY = touch.clientY - startY;

      if (Math.abs(deltaX) <= threshold || Math.abs(deltaX) <= Math.abs(deltaY) * 1.2) {
        return;
      }

      onSwipe(deltaX < 0 ? 1 : -1);
    },
    { passive: true },
  );
}
