(function () {
  "use strict";

  const root = document.querySelector("[data-story-root]");
  if (!root || typeof HTMLDialogElement === "undefined") return;

  const dialog = root.querySelector("[data-story-viewer]");
  const shell = dialog && dialog.querySelector(".zad-story-viewer__shell");
  const payload = root.querySelector("[data-story-payload]");
  const triggers = Array.from(root.querySelectorAll("[data-story-trigger]"));
  if (!dialog || !shell || !payload || !triggers.length) return;

  const groups = Array.from(payload.querySelectorAll("[data-story-group]"))
    .map(function (groupElement) {
      return {
        id: groupElement.dataset.storyId,
        version: groupElement.dataset.storyVersion,
        title: groupElement.dataset.storyTitle,
        cover: groupElement.dataset.storyCover,
        clips: Array.from(groupElement.querySelectorAll("[data-story-clip]")).map(
          function (clipElement) {
            return {
              id: clipElement.dataset.clipId,
              title: clipElement.dataset.clipTitle || "",
              caption: clipElement.dataset.clipCaption || "",
              video: clipElement.dataset.clipVideo,
              poster: clipElement.dataset.clipPoster,
              duration: Number(clipElement.dataset.clipDuration || 0),
              ctaText: clipElement.dataset.clipCtaText || "",
              ctaUrl: clipElement.dataset.clipCtaUrl || "",
            };
          }
        ),
      };
    })
    .filter(function (group) {
      return group.clips.length > 0;
    });

  if (!groups.length) return;

  const stage = dialog.querySelector("[data-story-stage]");
  const video = dialog.querySelector("[data-story-video]");
  const progress = dialog.querySelector("[data-story-progress]");
  const avatar = dialog.querySelector("[data-story-avatar]");
  const storyName = dialog.querySelector("[data-story-name]");
  const counter = dialog.querySelector("[data-story-counter]");
  const clipTitle = dialog.querySelector("[data-story-clip-title]");
  const caption = dialog.querySelector("[data-story-caption]");
  const cta = dialog.querySelector("[data-story-cta]");
  const ctaLabel = cta.querySelector("span");
  const loading = dialog.querySelector("[data-story-loading]");
  const error = dialog.querySelector("[data-story-error]");
  const retryButton = dialog.querySelector("[data-story-retry]");
  const playButton = dialog.querySelector("[data-story-play]");
  const playIcon = playButton.querySelector("i");
  const muteButton = dialog.querySelector("[data-story-mute]");
  const muteIcon = muteButton.querySelector("i");
  const closeButton = dialog.querySelector("[data-story-close]");
  const previousZone = dialog.querySelector("[data-story-previous]");
  const nextZone = dialog.querySelector("[data-story-next]");
  const previousVisible = dialog.querySelector("[data-story-previous-visible]");
  const nextVisible = dialog.querySelector("[data-story-next-visible]");
  const hint = dialog.querySelector("[data-story-hint]");
  const announcer = dialog.querySelector("[data-story-announcer]");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const SEEN_STORAGE_KEY = "zad-story-seen-v1";
  const HINT_STORAGE_KEY = "zad-story-hold-hint-v1";
  let storyIndex = 0;
  let clipIndex = 0;
  let progressElements = [];
  let animationFrame = 0;
  let closeTimer = 0;
  let hintTimer = 0;
  let preloadVideo = null;
  let preloadCleanupTimer = 0;
  let lastTrigger = null;
  let isClosing = false;
  let isMuted = true;
  let isHolding = false;
  let manualPaused = false;
  let pausedByVisibility = false;
  let gesture = null;
  let holdTimer = 0;

  previousZone.tabIndex = -1;
  nextZone.tabIndex = -1;

  function readStorage(storage, key, fallback) {
    try {
      const value = storage.getItem(key);
      return value === null ? fallback : value;
    } catch (storageError) {
      return fallback;
    }
  }

  function writeStorage(storage, key, value) {
    try {
      storage.setItem(key, value);
    } catch (storageError) {
      // Playback must remain available in private browsing or blocked storage.
    }
  }

  function readSeenStories() {
    try {
      const value = JSON.parse(
        readStorage(window.localStorage, SEEN_STORAGE_KEY, "{}")
      );
      return value && typeof value === "object" ? value : {};
    } catch (parseError) {
      return {};
    }
  }

  function updateSeenRings() {
    const seenStories = readSeenStories();
    triggers.forEach(function (trigger) {
      const isSeen =
        String(seenStories[trigger.dataset.storyId] || "") ===
        String(trigger.dataset.storyVersion || "");
      trigger.classList.toggle("is-seen", isSeen);
    });
  }

  function markStorySeen(group) {
    const seenStories = readSeenStories();
    seenStories[group.id] = group.version;
    writeStorage(
      window.localStorage,
      SEEN_STORAGE_KEY,
      JSON.stringify(seenStories)
    );
    updateSeenRings();
  }

  function currentGroup() {
    return groups[storyIndex];
  }

  function currentClip() {
    return currentGroup().clips[clipIndex];
  }

  function renderProgress() {
    progress.replaceChildren();
    progressElements = currentGroup().clips.map(function (_, index) {
      const element = document.createElement("progress");
      element.max = 1;
      element.value = index < clipIndex ? 1 : 0;
      element.setAttribute(
        "aria-label",
        "کلیپ " + String(index + 1) + " از " + String(currentGroup().clips.length)
      );
      progress.appendChild(element);
      return element;
    });
  }

  function updateProgress() {
    if (!dialog.open || !progressElements.length) return;
    const duration = Number.isFinite(video.duration) && video.duration > 0
      ? video.duration
      : currentClip().duration / 1000;
    const ratio = duration > 0
      ? Math.min(1, Math.max(0, video.currentTime / duration))
      : 0;

    progressElements.forEach(function (element, index) {
      if (index < clipIndex) element.value = 1;
      else if (index > clipIndex) element.value = 0;
      else element.value = ratio;
    });
  }

  function stopProgressLoop() {
    if (animationFrame) {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = 0;
    }
  }

  function progressLoop() {
    updateProgress();
    if (!video.paused && !video.ended && dialog.open) {
      animationFrame = window.requestAnimationFrame(progressLoop);
    } else {
      animationFrame = 0;
    }
  }

  function startProgressLoop() {
    stopProgressLoop();
    animationFrame = window.requestAnimationFrame(progressLoop);
  }

  function showLoading(show) {
    loading.classList.toggle("is-hidden", !show);
  }

  function showError(show) {
    error.hidden = !show;
    if (show) showLoading(false);
  }

  function updatePlayControl() {
    const paused = video.paused;
    playIcon.className = paused ? "bi bi-play-fill" : "bi bi-pause-fill";
    playButton.setAttribute(
      "aria-label",
      paused ? "ادامه پخش ویدئو" : "توقف ویدئو"
    );
    playButton.setAttribute("aria-pressed", String(paused));
  }

  function updateMuteControl() {
    video.muted = isMuted;
    video.defaultMuted = isMuted;
    muteIcon.className = isMuted
      ? "bi bi-volume-mute-fill"
      : "bi bi-volume-up-fill";
    muteButton.setAttribute(
      "aria-label",
      isMuted ? "فعال‌کردن صدا" : "بی‌صداکردن ویدئو"
    );
    muteButton.setAttribute("aria-pressed", String(!isMuted));
  }

  function cleanupPreload() {
    window.clearTimeout(preloadCleanupTimer);
    if (preloadVideo) {
      preloadVideo.removeAttribute("src");
      preloadVideo.load();
      preloadVideo = null;
    }
  }

  function nextClipForPreload() {
    const group = currentGroup();
    if (clipIndex + 1 < group.clips.length) return group.clips[clipIndex + 1];
    if (storyIndex + 1 < groups.length) return groups[storyIndex + 1].clips[0];
    return null;
  }

  function preloadNextClip() {
    cleanupPreload();
    const nextClip = nextClipForPreload();
    if (!nextClip) return;
    const poster = new Image();
    poster.decoding = "async";
    poster.src = nextClip.poster;

    preloadVideo = document.createElement("video");
    preloadVideo.preload = "metadata";
    preloadVideo.muted = true;
    preloadVideo.src = nextClip.video;
    preloadCleanupTimer = window.setTimeout(cleanupPreload, 15000);
  }

  function setClipContent(clip) {
    clipTitle.textContent = clip.title;
    caption.textContent = clip.caption;
    if (clip.ctaText && clip.ctaUrl) {
      ctaLabel.textContent = clip.ctaText;
      cta.href = clip.ctaUrl;
      cta.hidden = false;
    } else {
      ctaLabel.textContent = "";
      cta.removeAttribute("href");
      cta.hidden = true;
    }
  }

  function announceClip() {
    announcer.textContent =
      currentGroup().title +
      "، کلیپ " +
      String(clipIndex + 1) +
      " از " +
      String(currentGroup().clips.length);
  }

  function loadClip() {
    const group = currentGroup();
    const clip = currentClip();
    stopProgressLoop();
    manualPaused = false;
    pausedByVisibility = false;
    showError(false);
    showLoading(true);
    renderProgress();
    setClipContent(clip);

    avatar.src = group.cover;
    storyName.textContent = group.title;
    counter.textContent =
      String(clipIndex + 1) + " / " + String(group.clips.length);
    video.poster = clip.poster;
    video.src = clip.video;
    updateMuteControl();
    video.load();
    updatePlayControl();
    announceClip();
    preloadNextClip();

    const playAttempt = video.play();
    if (playAttempt && typeof playAttempt.catch === "function") {
      playAttempt.catch(function (playError) {
        if (playError && playError.name === "AbortError") return;
        manualPaused = true;
        showLoading(false);
        updatePlayControl();
      });
    }
  }

  function setStory(nextStoryIndex, nextClipIndex) {
    if (nextStoryIndex < 0 || nextStoryIndex >= groups.length) return false;
    storyIndex = nextStoryIndex;
    clipIndex = Math.min(
      Math.max(nextClipIndex || 0, 0),
      currentGroup().clips.length - 1
    );
    loadClip();
    return true;
  }

  function showNext() {
    const group = currentGroup();
    if (clipIndex + 1 < group.clips.length) {
      clipIndex += 1;
      loadClip();
      return;
    }

    markStorySeen(group);
    if (!setStory(storyIndex + 1, 0)) closeViewer();
  }

  function showPrevious() {
    if (clipIndex > 0) {
      clipIndex -= 1;
      loadClip();
      return;
    }
    if (storyIndex > 0) {
      setStory(storyIndex - 1, groups[storyIndex - 1].clips.length - 1);
      return;
    }
    video.currentTime = 0;
    updateProgress();
  }

  function switchStory(delta) {
    const nextIndex = storyIndex + delta;
    if (nextIndex < 0) {
      video.currentTime = 0;
      return;
    }
    if (nextIndex >= groups.length) {
      markStorySeen(currentGroup());
      closeViewer();
      return;
    }
    setStory(nextIndex, 0);
  }

  function togglePlayback() {
    if (video.paused) {
      manualPaused = false;
      const playAttempt = video.play();
      if (playAttempt && typeof playAttempt.catch === "function") {
        playAttempt.catch(function () {
          manualPaused = true;
          updatePlayControl();
        });
      }
    } else {
      manualPaused = true;
      video.pause();
    }
    updatePlayControl();
  }

  function toggleMute() {
    isMuted = !isMuted;
    updateMuteControl();
    if (video.paused && !manualPaused) video.play().catch(function () {});
  }

  function showHoldHintOnce() {
    if (readStorage(window.sessionStorage, HINT_STORAGE_KEY, "") === "shown") {
      return;
    }
    writeStorage(window.sessionStorage, HINT_STORAGE_KEY, "shown");
    hint.classList.add("is-visible");
    window.clearTimeout(hintTimer);
    hintTimer = window.setTimeout(function () {
      hint.classList.remove("is-visible");
    }, 2500);
  }

  function finishClose() {
    window.clearTimeout(closeTimer);
    window.clearTimeout(hintTimer);
    window.clearTimeout(holdTimer);
    stopProgressLoop();
    cleanupPreload();
    video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    video.load();
    if (dialog.open) dialog.close();
    dialog.classList.remove("is-closing");
    document.body.classList.remove("has-story-viewer");
    isClosing = false;
    isHolding = false;
    gesture = null;
    if (lastTrigger && document.contains(lastTrigger)) {
      lastTrigger.focus({ preventScroll: true });
    }
  }

  function closeViewer(options) {
    options = options || {};
    if (!dialog.open || isClosing) return;
    isClosing = true;
    video.pause();
    dialog.classList.add("is-closing");
    if (options.immediate || reducedMotion.matches) finishClose();
    else closeTimer = window.setTimeout(finishClose, 175);
  }

  function openViewer(index, trigger) {
    if (isClosing) return;
    storyIndex = Math.min(Math.max(index, 0), groups.length - 1);
    clipIndex = 0;
    lastTrigger = trigger;
    if (!dialog.open) dialog.showModal();
    document.body.classList.add("has-story-viewer");
    setStory(storyIndex, 0);
    closeButton.focus({ preventScroll: true });
    showHoldHintOnce();
  }

  function startGesture(event, direction) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    gesture = {
      pointerId: event.pointerId,
      direction: direction,
      startX: event.clientX,
      startY: event.clientY,
      startedAt: performance.now(),
      wasPlaying: !video.paused,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    window.clearTimeout(holdTimer);
    holdTimer = window.setTimeout(function () {
      if (!gesture) return;
      isHolding = true;
      video.pause();
      updatePlayControl();
    }, 150);
  }

  function moveGesture(event) {
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    const deltaX = event.clientX - gesture.startX;
    const deltaY = event.clientY - gesture.startY;
    if (!isHolding && Math.hypot(deltaX, deltaY) > 12) {
      window.clearTimeout(holdTimer);
    }
  }

  function endGesture(event) {
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    window.clearTimeout(holdTimer);
    const completedGesture = gesture;
    gesture = null;
    const deltaX = event.clientX - completedGesture.startX;
    const deltaY = event.clientY - completedGesture.startY;
    const elapsed = performance.now() - completedGesture.startedAt;

    if (isHolding) {
      isHolding = false;
      if (completedGesture.wasPlaying && !manualPaused && !document.hidden) {
        video.play().catch(function () {});
      }
      updatePlayControl();
      return;
    }

    if (deltaY > 72 && Math.abs(deltaY) > Math.abs(deltaX) * 1.15) {
      closeViewer();
      return;
    }

    if (Math.abs(deltaX) > 54 && Math.abs(deltaX) > Math.abs(deltaY) * 1.15) {
      switchStory(deltaX < 0 ? 1 : -1);
      return;
    }

    if (elapsed < 500 && Math.hypot(deltaX, deltaY) < 18) {
      if (completedGesture.direction === "previous") showPrevious();
      else showNext();
    }
  }

  function cancelGesture() {
    window.clearTimeout(holdTimer);
    if (isHolding && gesture && gesture.wasPlaying && !manualPaused) {
      video.play().catch(function () {});
    }
    isHolding = false;
    gesture = null;
  }

  function bindGestureZone(zone, direction) {
    zone.addEventListener("pointerdown", function (event) {
      startGesture(event, direction);
    });
    zone.addEventListener("pointermove", moveGesture);
    zone.addEventListener("pointerup", endGesture);
    zone.addEventListener("pointercancel", cancelGesture);
    zone.addEventListener("click", function (event) {
      event.preventDefault();
      if (event.detail === 0) {
        if (direction === "previous") showPrevious();
        else showNext();
      }
    });
  }

  triggers.forEach(function (trigger, index) {
    trigger.addEventListener("click", function () {
      openViewer(index, trigger);
    });
  });

  bindGestureZone(previousZone, "previous");
  bindGestureZone(nextZone, "next");
  previousVisible.addEventListener("click", function () {
    switchStory(-1);
  });
  nextVisible.addEventListener("click", function () {
    switchStory(1);
  });
  closeButton.addEventListener("click", function () {
    closeViewer();
  });
  playButton.addEventListener("click", togglePlayback);
  muteButton.addEventListener("click", toggleMute);
  retryButton.addEventListener("click", loadClip);

  video.addEventListener("loadedmetadata", updateProgress);
  video.addEventListener("canplay", function () {
    showLoading(false);
    showError(false);
  });
  video.addEventListener("playing", function () {
    showLoading(false);
    showError(false);
    updatePlayControl();
    startProgressLoop();
  });
  video.addEventListener("pause", function () {
    stopProgressLoop();
    updateProgress();
    updatePlayControl();
  });
  video.addEventListener("waiting", function () {
    if (!video.paused) showLoading(true);
  });
  video.addEventListener("ended", showNext);
  video.addEventListener("error", function () {
    showError(true);
    stopProgressLoop();
  });

  dialog.addEventListener("cancel", function (event) {
    event.preventDefault();
    closeViewer();
  });

  dialog.addEventListener("click", function (event) {
    if (event.target === dialog || event.target === shell) closeViewer();
  });

  document.addEventListener("keydown", function (event) {
    if (!dialog.open || isClosing) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPrevious();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      showNext();
    } else if (event.key === " " || event.key === "k") {
      event.preventDefault();
      togglePlayback();
    } else if (event.key.toLowerCase() === "m") {
      event.preventDefault();
      toggleMute();
    }
  });

  document.addEventListener("visibilitychange", function () {
    if (!dialog.open) return;
    if (document.hidden && !video.paused) {
      pausedByVisibility = true;
      video.pause();
    } else if (
      !document.hidden &&
      pausedByVisibility &&
      !manualPaused &&
      !isHolding
    ) {
      pausedByVisibility = false;
      video.play().catch(function () {});
    }
  });

  stage.addEventListener("contextmenu", function (event) {
    event.preventDefault();
  });

  updateSeenRings();
  updateMuteControl();
  updatePlayControl();
})();
