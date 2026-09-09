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
              type: clipElement.dataset.clipType || "video",
              title: clipElement.dataset.clipTitle || "",
              caption: clipElement.dataset.clipCaption || "",
              video: clipElement.dataset.clipVideo || "",
              image: clipElement.dataset.clipImage || "",
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
  const storyImage = dialog.querySelector("[data-story-image]");
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
  const mobileViewport = window.matchMedia("(max-width: 760px)");

  const SEEN_STORAGE_KEY = "zad-story-seen-v1";
  const HINT_STORAGE_KEY = "zad-story-hold-hint-v1";
  const CUBE_DURATION_MS = 600;
  const CUBE_CANCEL_DURATION_MS = 250;
  let storyIndex = 0;
  let clipIndex = 0;
  let progressElements = [];
  let animationFrame = 0;
  let closeTimer = 0;
  let hintTimer = 0;
  let preloadImage = null;
  let preloadVideo = null;
  let preloadCleanupTimer = 0;
  let cubeTransition = null;
  let cubeTransitionTimer = 0;
  let lastTrigger = null;
  let isClosing = false;
  let isMuted = true;
  let isHolding = false;
  let manualPaused = false;
  let pausedByVisibility = false;
  let gesture = null;
  let holdTimer = 0;
  let imageAdvanceTimer = 0;
  let imageStartedAt = 0;
  let imageElapsedMs = 0;
  let imagePaused = true;

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
        "محتوا " +
          String(index + 1) +
          " از " +
          String(currentGroup().clips.length)
      );
      progress.appendChild(element);
      return element;
    });
  }
  function updateProgress() {
    if (!dialog.open || !progressElements.length) return;
    const clip = currentClip();
    let ratio = 0;
    if (clip.type === "image") {
      const elapsed = imagePaused
        ? imageElapsedMs
        : performance.now() - imageStartedAt;
      ratio = clip.duration > 0
        ? Math.min(1, Math.max(0, elapsed / clip.duration))
        : 0;
    } else {
      const duration = Number.isFinite(video.duration) && video.duration > 0
        ? video.duration
        : clip.duration / 1000;
      ratio = duration > 0
        ? Math.min(1, Math.max(0, video.currentTime / duration))
        : 0;
    }

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
    const clip = currentClip();
    const isPlaying = clip.type === "image"
      ? !imagePaused
      : !video.paused && !video.ended;
    if (isPlaying && dialog.open) {
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

  function clearImagePlayback() {
    window.clearTimeout(imageAdvanceTimer);
    imageAdvanceTimer = 0;
    imageStartedAt = 0;
    imageElapsedMs = 0;
    imagePaused = true;
  }

  function pauseImagePlayback() {
    if (imagePaused) return;
    imageElapsedMs = Math.min(
      currentClip().duration,
      performance.now() - imageStartedAt
    );
    imagePaused = true;
    window.clearTimeout(imageAdvanceTimer);
    imageAdvanceTimer = 0;
    stopProgressLoop();
    updateProgress();
  }

  function startImagePlayback() {
    const duration = Math.max(2000, currentClip().duration || 5000);
    if (imageElapsedMs >= duration) imageElapsedMs = 0;
    imagePaused = false;
    imageStartedAt = performance.now() - imageElapsedMs;
    window.clearTimeout(imageAdvanceTimer);
    imageAdvanceTimer = window.setTimeout(showNext, duration - imageElapsedMs);
    startProgressLoop();
  }

  function isCurrentMediaPaused() {
    return currentClip().type === "image" ? imagePaused : video.paused;
  }

  function updatePlayControl() {
    const paused = isCurrentMediaPaused();
    playIcon.className = paused ? "bi bi-play-fill" : "bi bi-pause-fill";
    playButton.setAttribute(
      "aria-label",
      paused ? "ادامه نمایش" : "توقف نمایش"
    );
    playButton.setAttribute("aria-pressed", String(paused));
  }

  function updateMuteControl() {
    const isImage = currentClip().type === "image";
    muteButton.hidden = isImage;
    if (isImage) return;
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
    if (preloadImage) {
      preloadImage.onload = null;
      preloadImage.onerror = null;
      preloadImage = null;
    }
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
    preloadImage = new Image();
    preloadImage.decoding = "async";
    preloadImage.src = nextClip.type === "image"
      ? nextClip.image
      : nextClip.poster;

    if (nextClip.type === "image") return;
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
      "، محتوا " +
      String(clipIndex + 1) +
      " از " +
      String(currentGroup().clips.length);
  }

  function loadClip() {
    const group = currentGroup();
    const clip = currentClip();
    stopProgressLoop();
    clearImagePlayback();
    video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    video.load();
    storyImage.hidden = true;
    storyImage.onload = null;
    storyImage.onerror = null;
    storyImage.removeAttribute("src");
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
    announceClip();
    preloadNextClip();

    if (clip.type === "image") {
      video.hidden = true;
      storyImage.hidden = false;
      updateMuteControl();
      updatePlayControl();
      let imageHasStarted = false;
      const imageReady = function () {
        if (imageHasStarted) return;
        imageHasStarted = true;
        showLoading(false);
        showError(false);
        if (!manualPaused && !document.hidden) startImagePlayback();
        updatePlayControl();
      };
      storyImage.onload = imageReady;
      storyImage.onerror = function () {
        showError(true);
        stopProgressLoop();
      };
      storyImage.src = clip.image;
      if (storyImage.complete && storyImage.naturalWidth > 0) imageReady();
      return;
    }

    storyImage.onload = null;
    storyImage.onerror = null;
    video.hidden = false;
    video.poster = clip.poster;
    video.src = clip.video;
    updateMuteControl();
    video.load();
    updatePlayControl();

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

  function currentMediaSnapshotSource() {
    const clip = currentClip();
    if (clip.type === "image") {
      return storyImage.currentSrc || storyImage.src || clip.image || clip.poster;
    }

    if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
      try {
        const canvas = document.createElement("canvas");
        const scale = Math.min(1, 540 / video.videoWidth);
        canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
        canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
        const context = canvas.getContext("2d", { alpha: false });
        if (context) {
          context.drawImage(video, 0, 0, canvas.width, canvas.height);
          return canvas.toDataURL("image/jpeg", 0.82);
        }
      } catch (snapshotError) {
        // A poster remains a safe fallback if a browser blocks video capture.
      }
    }

    return video.poster || clip.poster || currentGroup().cover;
  }

  function makeCubeFace(className, mediaSource) {
    const face = stage.cloneNode(true);
    face.classList.remove("zad-story-viewer__stage");
    face.classList.add("zad-story-viewer__cube-face", className);
    face.removeAttribute("data-story-stage");
    face.setAttribute("aria-hidden", "true");
    face.setAttribute("inert", "");

    face.querySelectorAll("[id]").forEach(function (element) {
      element.removeAttribute("id");
    });
    face.querySelectorAll("button, a").forEach(function (element) {
      element.tabIndex = -1;
    });

    const faceVideo = face.querySelector("[data-story-video]");
    if (faceVideo) faceVideo.remove();
    const faceImage = face.querySelector("[data-story-image]");
    if (faceImage) {
      faceImage.loading = "eager";
      faceImage.decoding = "sync";
      faceImage.hidden = !mediaSource;
      if (mediaSource) faceImage.src = mediaSource;
      else faceImage.removeAttribute("src");
    }

    const faceLoading = face.querySelector("[data-story-loading]");
    if (faceLoading) faceLoading.classList.add("is-hidden");
    const faceError = face.querySelector("[data-story-error]");
    if (faceError) faceError.hidden = true;
    const faceHint = face.querySelector("[data-story-hint]");
    if (faceHint) faceHint.classList.remove("is-visible");
    const faceAnnouncer = face.querySelector("[data-story-announcer]");
    if (faceAnnouncer) faceAnnouncer.textContent = "";

    const shade = document.createElement("span");
    shade.className = "zad-story-viewer__cube-shade";
    face.appendChild(shade);
    return { face: face, shade: shade };
  }

  function populateIncomingFace(face, group, clip, targetClipIndex) {
    const faceAvatar = face.querySelector("[data-story-avatar]");
    const faceName = face.querySelector("[data-story-name]");
    const faceCounter = face.querySelector("[data-story-counter]");
    if (faceAvatar) faceAvatar.src = group.cover;
    if (faceName) faceName.textContent = group.title;
    if (faceCounter) {
      faceCounter.textContent =
        String(targetClipIndex + 1) + " / " + String(group.clips.length);
    }

    const faceProgress = face.querySelector("[data-story-progress]");
    if (faceProgress) {
      faceProgress.replaceChildren();
      group.clips.forEach(function (_, index) {
        const element = document.createElement("progress");
        element.max = 1;
        element.value = index < targetClipIndex ? 1 : 0;
        faceProgress.appendChild(element);
      });
    }

    const faceTitle = face.querySelector("[data-story-clip-title]");
    const faceCaption = face.querySelector("[data-story-caption]");
    const faceCta = face.querySelector("[data-story-cta]");
    if (faceTitle) faceTitle.textContent = clip.title;
    if (faceCaption) faceCaption.textContent = clip.caption;
    if (faceCta) {
      const faceCtaLabel = faceCta.querySelector("span");
      if (clip.ctaText && clip.ctaUrl) {
        if (faceCtaLabel) faceCtaLabel.textContent = clip.ctaText;
        faceCta.href = clip.ctaUrl;
        faceCta.hidden = false;
      } else {
        if (faceCtaLabel) faceCtaLabel.textContent = "";
        faceCta.removeAttribute("href");
        faceCta.hidden = true;
      }
    }

    const faceMute = face.querySelector("[data-story-mute]");
    if (faceMute) faceMute.hidden = clip.type === "image";
  }

  function setCubeProgress(state, progressValue) {
    const progressValueSafe = Math.min(1, Math.max(0, progressValue));
    const angle = state.direction * -90 * progressValueSafe;
    state.progress = progressValueSafe;
    state.cube.style.transform =
      "translateZ(-" + String(state.depth) + "px) rotateY(" +
      String(angle) + "deg)";
    state.currentShade.style.opacity = String(progressValueSafe * 0.2);
    state.incomingShade.style.opacity = String((1 - progressValueSafe) * 0.16);
  }

  function createCubeTransition(targetStoryIndex, targetClipIndex, direction) {
    if (cubeTransition || reducedMotion.matches || !mobileViewport.matches) {
      return null;
    }
    const targetGroup = groups[targetStoryIndex];
    if (!targetGroup) return null;
    const safeClipIndex = Math.min(
      Math.max(targetClipIndex || 0, 0),
      targetGroup.clips.length - 1
    );
    const targetClip = targetGroup.clips[safeClipIndex];
    const stageWidth = stage.getBoundingClientRect().width;
    if (!targetClip || stageWidth < 1) return null;

    const currentFace = makeCubeFace(
      "zad-story-viewer__cube-face--current",
      currentMediaSnapshotSource()
    );
    const incomingSource = targetClip.type === "image"
      ? targetClip.image
      : targetClip.poster;
    const incomingFace = makeCubeFace(
      "zad-story-viewer__cube-face--incoming",
      incomingSource || targetGroup.cover
    );
    populateIncomingFace(
      incomingFace.face,
      targetGroup,
      targetClip,
      safeClipIndex
    );

    const layer = document.createElement("div");
    const cube = document.createElement("div");
    const normalizedDirection = direction < 0 ? -1 : 1;
    const depth = Math.max(1, Math.round(stageWidth / 2));
    layer.className =
      "zad-story-viewer__cube-layer " +
      (normalizedDirection > 0 ? "is-forward" : "is-backward");
    layer.setAttribute("aria-hidden", "true");
    layer.style.setProperty("--zad-story-cube-depth", String(depth) + "px");
    cube.className = "zad-story-viewer__cube";
    cube.append(currentFace.face, incomingFace.face);
    layer.appendChild(cube);
    stage.appendChild(layer);
    stage.classList.add("is-cube-transitioning");

    cubeTransition = {
      layer: layer,
      cube: cube,
      currentShade: currentFace.shade,
      incomingShade: incomingFace.shade,
      depth: depth,
      direction: normalizedDirection,
      progress: 0,
      targetStoryIndex: targetStoryIndex,
      targetClipIndex: safeClipIndex,
      wasPlaying: !isCurrentMediaPaused(),
    };
    setCubeProgress(cubeTransition, 0);
    return cubeTransition;
  }

  function pauseForCubeTransition() {
    if (currentClip().type === "image") pauseImagePlayback();
    else video.pause();
    updatePlayControl();
  }

  function resumeAfterCubeTransition(state) {
    if (!state.wasPlaying || manualPaused || document.hidden || isClosing) return;
    if (currentClip().type === "image") startImagePlayback();
    else video.play().catch(function () {});
    updatePlayControl();
  }

  function clearCubeTransition(resumePlayback) {
    const state = cubeTransition;
    window.clearTimeout(cubeTransitionTimer);
    cubeTransitionTimer = 0;
    if (!state) return;
    state.layer.remove();
    stage.classList.remove("is-cube-transitioning");
    cubeTransition = null;
    if (resumePlayback) resumeAfterCubeTransition(state);
  }

  function settleCubeTransition(state, commit) {
    if (!state || cubeTransition !== state) return;
    const targetProgress = commit ? 1 : 0;
    const remaining = Math.abs(targetProgress - state.progress);
    if (commit) {
      setStory(state.targetStoryIndex, state.targetClipIndex);
    }
    if (remaining <= 0.001) {
      clearCubeTransition(!commit);
      return;
    }

    const baseDuration = commit ? CUBE_DURATION_MS : CUBE_CANCEL_DURATION_MS;
    const duration = Math.max(110, Math.round(baseDuration * remaining));
    let hasFinished = false;

    const finish = function (event) {
      if (hasFinished || cubeTransition !== state) return;
      if (event) {
        const isCubeTransform =
          event.target === state.cube &&
          (event.propertyName === "transform" ||
            event.propertyName === "-webkit-transform");
        if (!isCubeTransform) return;
      }
      hasFinished = true;
      clearCubeTransition(!commit);
    };

    state.cube.style.transition =
      "transform " + String(duration) +
      "ms cubic-bezier(0.22, 0.78, 0.2, 1)";
    state.currentShade.style.transition = "opacity " + String(duration) + "ms ease";
    state.incomingShade.style.transition = "opacity " + String(duration) + "ms ease";
    state.cube.addEventListener("transitionend", finish);
    cubeTransitionTimer = window.setTimeout(finish, duration + 80);
    void state.cube.offsetWidth;
    window.requestAnimationFrame(function () {
      if (cubeTransition === state) setCubeProgress(state, targetProgress);
    });
  }

  function transitionToStory(nextStoryIndex, nextClipIndex, direction) {
    if (cubeTransition) return false;
    if (nextStoryIndex < 0 || nextStoryIndex >= groups.length) return false;
    if (reducedMotion.matches) return setStory(nextStoryIndex, nextClipIndex);

    const state = createCubeTransition(
      nextStoryIndex,
      nextClipIndex,
      direction
    );
    if (!state) return setStory(nextStoryIndex, nextClipIndex);
    pauseForCubeTransition();
    settleCubeTransition(state, true);
    return true;
  }

  function showNext() {
    if (cubeTransition) return;
    const group = currentGroup();
    if (clipIndex + 1 < group.clips.length) {
      clipIndex += 1;
      loadClip();
      return;
    }

    markStorySeen(group);
    if (!transitionToStory(storyIndex + 1, 0, 1)) closeViewer();
  }

  function showPrevious() {
    if (cubeTransition) return;
    if (clipIndex > 0) {
      clipIndex -= 1;
      loadClip();
      return;
    }
    if (storyIndex > 0) {
      transitionToStory(
        storyIndex - 1,
        groups[storyIndex - 1].clips.length - 1,
        -1
      );
      return;
    }
    if (currentClip().type === "image") {
      clearImagePlayback();
      if (!manualPaused) startImagePlayback();
    } else {
      video.currentTime = 0;
    }
    updateProgress();
  }

  function switchStory(delta) {
    if (cubeTransition) return;
    const nextIndex = storyIndex + delta;
    if (nextIndex < 0) {
      if (currentClip().type === "image") {
        clearImagePlayback();
        if (!manualPaused) startImagePlayback();
      } else {
        video.currentTime = 0;
      }
      return;
    }
    if (nextIndex >= groups.length) {
      markStorySeen(currentGroup());
      closeViewer();
      return;
    }
    transitionToStory(nextIndex, 0, delta);
  }

  function togglePlayback() {
    if (cubeTransition) return;
    if (currentClip().type === "image") {
      if (imagePaused) {
        manualPaused = false;
        startImagePlayback();
      } else {
        manualPaused = true;
        pauseImagePlayback();
      }
      updatePlayControl();
      return;
    }
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
    if (cubeTransition) return;
    if (currentClip().type === "image") return;
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
    clearCubeTransition(false);
    stopProgressLoop();
    clearImagePlayback();
    cleanupPreload();
    video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    video.load();
    storyImage.onload = null;
    storyImage.onerror = null;
    storyImage.removeAttribute("src");
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
    clearCubeTransition(false);
    if (currentClip().type === "image") pauseImagePlayback();
    else video.pause();
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
    if (cubeTransition || isClosing) return;
    if (event.pointerType === "mouse" && event.button !== 0) return;
    gesture = {
      pointerId: event.pointerId,
      direction: direction,
      startX: event.clientX,
      startY: event.clientY,
      startedAt: performance.now(),
      wasPlaying: !isCurrentMediaPaused(),
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    window.clearTimeout(holdTimer);
    holdTimer = window.setTimeout(function () {
      if (!gesture || gesture.cube) return;
      isHolding = true;
      if (currentClip().type === "image") pauseImagePlayback();
      else video.pause();
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
    if (isHolding) return;
    if (Math.abs(deltaX) <= 12) {
      if (gesture.cube) setCubeProgress(gesture.cube, 0);
      return;
    }
    if (Math.abs(deltaX) <= Math.abs(deltaY) * 1.08) {
      return;
    }

    const direction = deltaX < 0 ? 1 : -1;
    if (gesture.cube && gesture.cube.direction !== direction) {
      clearCubeTransition(false);
      gesture.cube = null;
    }

    const nextIndex = storyIndex + direction;
    if (nextIndex < 0 || nextIndex >= groups.length) return;
    if (!gesture.cube) {
      gesture.cube = createCubeTransition(nextIndex, 0, direction);
      if (!gesture.cube) return;
      gesture.cube.wasPlaying = gesture.wasPlaying;
      pauseForCubeTransition();
    }

    event.preventDefault();
    setCubeProgress(
      gesture.cube,
      Math.min(1, Math.abs(deltaX) / Math.max(stage.clientWidth, 1))
    );
  }

  function endGesture(event) {
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    window.clearTimeout(holdTimer);
    const completedGesture = gesture;
    gesture = null;
    const deltaX = event.clientX - completedGesture.startX;
    const deltaY = event.clientY - completedGesture.startY;
    const elapsed = performance.now() - completedGesture.startedAt;

    if (completedGesture.cube) {
      const speed = Math.abs(deltaX) / Math.max(elapsed, 1);
      const shouldCommit =
        completedGesture.cube.progress >= 0.24 ||
        (completedGesture.cube.progress >= 0.08 && speed >= 0.45);
      settleCubeTransition(completedGesture.cube, shouldCommit);
      return;
    }

    if (isHolding) {
      isHolding = false;
      if (completedGesture.wasPlaying && !manualPaused && !document.hidden) {
        if (currentClip().type === "image") startImagePlayback();
        else video.play().catch(function () {});
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
    const gestureCube = gesture && gesture.cube;
    if (gestureCube) {
      gesture = null;
      isHolding = false;
      settleCubeTransition(gestureCube, false);
      return;
    }
    if (isHolding && gesture && gesture.wasPlaying && !manualPaused) {
      if (currentClip().type === "image") startImagePlayback();
      else video.play().catch(function () {});
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
    if (document.hidden && !isCurrentMediaPaused()) {
      pausedByVisibility = true;
      if (currentClip().type === "image") pauseImagePlayback();
      else video.pause();
    } else if (
      !document.hidden &&
      pausedByVisibility &&
      !manualPaused &&
      !isHolding
    ) {
      pausedByVisibility = false;
      if (currentClip().type === "image") startImagePlayback();
      else video.play().catch(function () {});
    }
  });

  stage.addEventListener("contextmenu", function (event) {
    event.preventDefault();
  });

  updateSeenRings();
  updateMuteControl();
  updatePlayControl();
})();
