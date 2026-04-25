/*
 * RPAS Micro | Dashboard Frontend
 *
 * Reglas INTRANSFERIBLES (tesis) que este archivo preserva:
 * 1) UI dinámica: ocultar/mostrar panel Joystick PTZ según Auto-Discovery ONVIF.
 * 2) Control PTZ: llamadas a `/ptz_move` y `/ptz_stop` (backend bloquea si la cámara es fija).
 * 3) Tracking automático: toggle que llama a `/api/auto_tracking`.
 *
 * Optimización aplicada:
 * - La UI de estado (AJAX `/detection_status`) solo se consulta cuando el tab "Live" está activo
 *   y la pestaña del navegador está visible. Esto reduce requests innecesarios y mejora FPS.
 */

(() => {
  'use strict';

  const ALERT_UPDATE_INTERVAL_MS = 1000;
  const PROGRESS_POLL_INTERVAL_MS = 500;
  const PTZ_HOLD_REPEAT_MS = 250;

  let progressTimer = null;
  let statusTimer = null;
  let activeJobId = null;
  let ptzPanelInitialized = false;
  let hardwareInitialized = false;

  function byId(id) {
    return document.getElementById(id);
  }

  function isLiveTabActive() {
    // Bootstrap marca el botón como `.active` cuando el tab está seleccionado.
    const liveTabBtn = byId('live-tab');
    return !!liveTabBtn && liveTabBtn.classList.contains('active');
  }

  function showFlash(type, msg) {
    const box = byId('flash-area');
    if (!box) return;
    box.innerHTML = `
      <div class="alert alert-${type} alert-dismissible fade show" role="alert">
        ${msg}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
      </div>
    `;
  }

  function setSpinner(visible) {
    const spinner = byId('spinnerBox');
    if (!spinner) return;
    spinner.classList.toggle('d-none', !visible);
  }

  function updateProgressUI(pct, status) {
    const bar = byId('progressBar');
    const txt = byId('progressText');
    const st = byId('progressStatus');
    if (!bar || !txt || !st) return;

    const v = Math.max(0, Math.min(100, parseInt(pct || 0, 10)));
    bar.style.width = `${v}%`;
    bar.textContent = `${v}%`;
    txt.textContent = `${v}%`;
    st.textContent = status || '';
  }

  function renderResult(payload) {
    const img = byId('resultImage');
    const vid = byId('resultVideo');
    const src = byId('resultVideoSource');
    const dl = byId('btnDownload');
    if (!img || !vid || !src || !dl) return;

    img.classList.add('d-none');
    vid.classList.add('d-none');
    dl.classList.add('d-none');

    if (payload.result_type === 'image') {
      img.src = `${payload.result_url}?t=${Date.now()}`;
      img.classList.remove('d-none');
      const mDet = byId('mDet');
      const mConf = byId('mConf');
      const mFrames = byId('mFrames');
      if (mDet) mDet.textContent = payload.detections_count ?? 0;
      if (mConf) mConf.textContent = `${((payload.avg_confidence ?? 0) * 100).toFixed(1)}%`;
      if (mFrames) mFrames.textContent = '-';
      dl.href = payload.result_url;
      dl.classList.remove('d-none');
      return;
    }

    if (payload.result_type === 'video') {
      src.src = `${payload.result_url}?t=${Date.now()}`;
      vid.load();
      vid.classList.remove('d-none');
      const mDet = byId('mDet');
      const mConf = byId('mConf');
      const mFrames = byId('mFrames');
      if (mDet) mDet.textContent = payload.total_detections ?? 0;
      if (mConf) mConf.textContent = `${((payload.avg_confidence ?? 0) * 100).toFixed(1)}%`;
      if (mFrames) mFrames.textContent = payload.frames_processed ?? '-';
      dl.href = payload.result_url;
      dl.classList.remove('d-none');
    }
  }

  function stopProgressPolling() {
    if (!progressTimer) return;
    clearInterval(progressTimer);
    progressTimer = null;
  }

  function startProgressPolling(jobId) {
    stopProgressPolling();

    progressTimer = setInterval(async () => {
      try {
        const r = await fetch(`/video_progress?job_id=${encodeURIComponent(jobId)}&_=${Date.now()}`);
        const d = await r.json();
        if (d.success === false) throw new Error(d.error || 'Error de progreso');

        updateProgressUI(d.progress ?? 0, d.status || '');

        if (d.done) {
          stopProgressPolling();
          setSpinner(false);

          if (d.result_type && d.result_url) {
            renderResult(d);
            showFlash('success', 'Inferencia completada. Resultado listo.');
          } else if (d.error) {
            showFlash('danger', d.error);
          }
        }
      } catch (e) {
        stopProgressPolling();
        setSpinner(false);
        showFlash('danger', e.message);
      }
    }, PROGRESS_POLL_INTERVAL_MS);
  }

  async function uploadDetect(event) {
    event?.preventDefault?.();

    const input = byId('fileInput');
    const file = input?.files?.[0];
    if (!file) {
      showFlash('warning', 'Selecciona un archivo primero.');
      return;
    }

    setSpinner(true);
    byId('progressWrap')?.classList.remove('d-none');
    updateProgressUI(0, 'subiendo...');
    const uploadBtn = byId('btnUpload');
    if (uploadBtn) uploadBtn.disabled = true;

    try {
      const form = new FormData();
      form.append('file', file);
      const res = await fetch('/upload_detect', { method: 'POST', body: form });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Error en detección');
      if (!data.job_id) throw new Error('Respuesta inválida: falta job_id');

      activeJobId = data.job_id;
      startProgressPolling(activeJobId);
      showFlash('info', 'Procesamiento iniciado. Mostrando progreso…');
    } catch (e) {
      setSpinner(false);
      byId('progressWrap')?.classList.add('d-none');
      showFlash('danger', e.message);
    } finally {
      if (uploadBtn) uploadBtn.disabled = false;
    }
  }

  function resetManual() {
    const input = byId('fileInput');
    if (input) input.value = '';

    const flash = byId('flash-area');
    if (flash) flash.innerHTML = '';

    byId('resultImage')?.classList.add('d-none');

    const video = byId('resultVideo');
    if (video) video.classList.add('d-none');

    const source = byId('resultVideoSource');
    if (source) source.removeAttribute('src');
    video?.load();

    byId('btnDownload')?.classList.add('d-none');
    const mDet = byId('mDet');
    const mConf = byId('mConf');
    const mFrames = byId('mFrames');
    if (mDet) mDet.textContent = '0';
    if (mConf) mConf.textContent = '0%';
    if (mFrames) mFrames.textContent = '-';

    byId('progressWrap')?.classList.add('d-none');
    updateProgressUI(0, 'En espera');
    setSpinner(false);

    stopProgressPolling();
    activeJobId = null;
  }

  async function refreshStatus() {
    // Endpoint liviano: solo estado agregado (no frames).
    const pill = byId('pillStatus');
    if (!pill) return;

    try {
      const r = await fetch('/detection_status', { cache: 'no-store' });
      const d = await r.json();

      const detected = !!d.detected;
      pill.textContent = d.status || (detected ? 'Alerta' : 'Zona despejada');
      pill.classList.toggle('bad', detected);
      pill.classList.toggle('ok', !detected);

      const sMode = byId('sMode');
      const sCount = byId('sCount');
      const sConf = byId('sConf');
      const sLast = byId('sLast');
      if (sMode) sMode.textContent = d.camera_source_mode || 'fixed';
      if (sCount) sCount.textContent = d.detection_count ?? 0;
      if (sConf) sConf.textContent = `${((d.avg_confidence ?? 0) * 100).toFixed(1)}%`;
      if (sLast) sLast.textContent = d.last_update ? new Date(d.last_update).toLocaleTimeString() : '-';
    } catch (_) {
      // Silencioso: el live puede fallar momentáneamente sin romper la UI.
    }
  }

  function stopStatusPolling() {
    if (!statusTimer) return;
    clearInterval(statusTimer);
    statusTimer = null;
  }

  function startStatusPolling() {
    if (statusTimer) return;
    statusTimer = setInterval(() => {
      // Evita requests innecesarios si el usuario está en otro tab o la pestaña está oculta.
      if (document.hidden || !isLiveTabActive()) return;
      refreshStatus();
    }, ALERT_UPDATE_INTERVAL_MS);
  }

  async function ptzMove(x, y) {
    try {
      // Nota: el backend aborta 403 si la cámara NO es PTZ (bloqueo de rutas).
      await fetch('/ptz_move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x, y, zoom: 0.0, duration_s: 0.18 }),
      });
    } catch (_) {}
  }

  async function ptzStop() {
    try {
      await fetch('/ptz_stop', { method: 'POST' });
    } catch (_) {}
  }

  function bindHoldMove(btn, x, y) {
    if (!btn) return;

    // Mantener presionado => repetir movimientos (pan/tilt) a intervalos.
    // Esto emula un joystick sin saturar el backend.
    let timer = null;

    const start = () => {
      if (timer) return;
      ptzMove(x, y);
      timer = setInterval(() => ptzMove(x, y), PTZ_HOLD_REPEAT_MS);
    };

    const stop = () => {
      if (!timer) return;
      clearInterval(timer);
      timer = null;
      ptzStop();
    };

    btn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      start();
    });
    btn.addEventListener('pointerup', (e) => {
      e.preventDefault();
      stop();
    });
    btn.addEventListener('pointercancel', (e) => {
      e.preventDefault();
      stop();
    });
    btn.addEventListener('pointerleave', (e) => {
      e.preventDefault();
      stop();
    });
  }

  function setupPTZPanel() {
    if (ptzPanelInitialized) return;
    ptzPanelInitialized = true;

    const toggle = byId('autoTrackingToggle');
    const btnUp = byId('ptzUp');
    const btnDown = byId('ptzDown');
    const btnLeft = byId('ptzLeft');
    const btnRight = byId('ptzRight');
    const btnStop = byId('ptzStop');

    // Tracking Automático (backend lo fuerza a false si la cámara es fija).
    if (toggle) {
      fetch(`/api/auto_tracking?_=${Date.now()}`)
        .then((r) => r.json())
        .then((d) => {
          toggle.checked = !!d.enabled;
        })
        .catch(() => {});

      toggle.addEventListener('change', async () => {
        try {
          await fetch('/api/auto_tracking', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: !!toggle.checked }),
          });
        } catch (_) {}
      });
    }

    bindHoldMove(btnUp, 0.0, 0.55);
    bindHoldMove(btnDown, 0.0, -0.55);
    bindHoldMove(btnLeft, -0.55, 0.0);
    bindHoldMove(btnRight, 0.55, 0.0);

    btnStop?.addEventListener('click', ptzStop);
  }

  async function initHardwareUI() {
    if (hardwareInitialized) return;
    hardwareInitialized = true;

    const badge = byId('hwBadge');
    const panel = byId('ptzPanel');
    if (!badge || !panel) return;

    // Nunca dejar el placeholder "--": arrancamos en modo seguro (panel oculto)
    // y actualizamos cuando la promesa de Auto-Discovery responda.
    badge.textContent = 'Detectando cámara...';
    badge.classList.remove('text-bg-success');
    badge.classList.add('text-bg-secondary');
    panel.style.display = 'none';

    // -------- Auto-Discovery (Regla de tesis) --------
    // Esta llamada determina si existe hardware PTZ vía ONVIF.
    // La UI reacciona:
    // - PTZ => muestra panel/joystick y permite tracking.
    // - Fija => destruye el panel para evitar intentos de control.
    fetch(`/api/camera_status?_=${Date.now()}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        // Fail-safe: si el backend reporta error, forzar modo seguro.
        const isPTZ = !!d?.is_ptz_capable;
        const status = (d?.status || 'ok').toLowerCase();

        if (status === 'error') {
          badge.textContent = 'Cámara Detectada: Fija (Modo Seguro)';
          badge.classList.remove('text-bg-success');
          badge.classList.add('text-bg-secondary');
          panel.style.display = 'none';
          return;
        }

        if (isPTZ) {
          badge.textContent = 'Cámara Detectada: PTZ';
          badge.classList.remove('text-bg-secondary');
          badge.classList.add('text-bg-success');
          panel.style.display = '';
          setupPTZPanel();
          return;
        }

        badge.textContent = 'Cámara Detectada: Fija';
        badge.classList.remove('text-bg-success');
        badge.classList.add('text-bg-secondary');
        panel.style.display = 'none';
      })
      .catch((error) => {
        // Fail-safe obligatorio:
        // Si el fetch falla por red o el backend no responde, asumir cámara fija.
        // Bajo ninguna circunstancia se deja el placeholder "--".
        badge.textContent = 'Cámara Detectada: Fija (Modo Seguro)';
        badge.classList.remove('text-bg-success');
        badge.classList.add('text-bg-secondary');
        panel.style.display = 'none';

        // Log en consola para debugging sin romper la UI.
        // eslint-disable-next-line no-console
        console.warn('[Auto-Discovery] /api/camera_status falló:', error);
      });
  }

  function initLiveTab() {
    const liveImg = byId('liveImg');
    if (liveImg) {
      // Cache-bust del feed al activar el tab para evitar quedarse con un stream viejo.
      liveImg.src = `/video_feed?_=${Date.now()}`;
    }

    byId('btnRefresh')?.addEventListener('click', refreshStatus);
    refreshStatus();
    startStatusPolling();
    initHardwareUI();
  }

  function initManualTab() {
    byId('btnUpload')?.addEventListener('click', uploadDetect);
    byId('btnReset')?.addEventListener('click', resetManual);
  }

  function init() {
    initManualTab();

    // Inicializa "Live" solo si está activo al cargar (reduce requests cuando el tab inicial es manual).
    if (isLiveTabActive()) {
      initLiveTab();
    }

    // Escucha cambios de tabs (Bootstrap).
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach((btn) => {
      btn.addEventListener('shown.bs.tab', (e) => {
        const targetId = e.target?.id;
        if (targetId === 'live-tab') {
          initLiveTab();
        } else {
          stopStatusPolling();
        }
      });
    });

    // Si el usuario cambia de pestaña del navegador, pausar polling para no gastar red/CPU.
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        stopStatusPolling();
        return;
      }
      if (isLiveTabActive()) {
        startStatusPolling();
        refreshStatus();
      }
    });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
