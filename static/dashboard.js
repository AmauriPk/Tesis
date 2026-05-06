(() => {
  const byId = (id) => document.getElementById(id);
  let lastPtzWarning = "";

  const fetchJson = async (url, opts = {}) => {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", ...(opts.headers || {}) },
      ...opts,
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return await res.json();
  };

  const setText = (id, text) => {
    const el = byId(id);
    if (el) el.textContent = text;
  };

  const fmtPct = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "0%";
    return `${Math.round(n * 100)}%`;
  };

  const showFlash = (type, msg) => {
    const area = byId("flash-area");
    if (!area) return;
    const div = document.createElement("div");
    div.className = `alert alert-${type} py-2 mb-2`;
    div.textContent = String(msg || "");
    area.innerHTML = "";
    area.appendChild(div);
  };

  const updateStatus = async () => {
    const data = await fetchJson("/detection_status");
    const status = String(data.status || "Zona despejada");
    const detected = Boolean(data.detected);
    const count = Number(data.detection_count || 0);
    const conf = Number(data.avg_confidence || 0);
    const mode = String(data.camera_source_mode || "fixed");
    const last = data.last_update ? String(data.last_update) : "-";

    const pill = byId("pillStatus");
    if (pill) {
      pill.textContent = status;
      pill.classList.toggle("ok", !detected);
      pill.classList.toggle("bad", detected);
      pill.classList.toggle("alert-blink", detected);
    }

    setText("sMode", mode);
    setText("sCount", String(count));
    setText("sConf", fmtPct(conf));
    setText("sLast", last);

    const warn = data.ptz_warning ? String(data.ptz_warning) : "";
    if (warn && warn !== lastPtzWarning) {
      lastPtzWarning = warn;
      showFlash("warning", warn);
    } else if (!warn) {
      lastPtzWarning = "";
    }
  };

  let alertsViewMode = "events"; // events | raw

  const bindEvidenceButtons = (rootEl) => {
    (rootEl || document).querySelectorAll("button[data-img-url]").forEach((b) => {
      b.addEventListener("click", () => {
        const img = byId("evidenceImage");
        const meta = byId("evidenceMeta");
        const modalEl = byId("evidenceModal");
        if (!img || !modalEl) return;
        img.src = String(b.dataset.imgUrl || "").replaceAll("//", "/");
        if (meta) meta.textContent = `Confianza: ${fmtPct(b.dataset.conf)}`;
        if (window.bootstrap?.Modal) new window.bootstrap.Modal(modalEl).show();
      });
    });
  };

  const renderEventAlerts = (events) => {
    const body = byId("recentAlertsBody");
    if (!body) return;
    body.innerHTML = "";

    const items = events || [];
    if (!items.length) {
      body.innerHTML = `<tr><td colspan="7" class="text-secondary">Sin alertas.</td></tr>`;
      return;
    }

    for (const ev of items) {
      const tr = document.createElement("tr");
      const id = ev.id ?? "-";
      const started = ev.started_at || "-";
      const ended = ev.ended_at || "-";
      const conf = Number(ev.max_confidence || 0);
      const count = Number(ev.detection_count || 0);
      const bbox = ev.best_bbox || "-";

      const imgUrl = ev.best_evidence_url ? String(ev.best_evidence_url) : "";
      const thumb = imgUrl
        ? `<img src="${imgUrl}" alt="evidencia" style="max-width:80px;max-height:60px;object-fit:cover;border-radius:6px" />`
        : `<span class="text-secondary">-</span>`;
      const btn = imgUrl
        ? `<button class="btn btn-sm btn-outline-warning ms-2" data-img-url="${imgUrl}" data-conf="${conf}">Ver</button>`
        : ``;

      tr.innerHTML = `
        <td class="mono">${id}</td>
        <td class="mono">${started}</td>
        <td class="mono">${ended}</td>
        <td class="mono">${fmtPct(conf)}</td>
        <td class="mono">${count}</td>
        <td class="mono">${bbox}</td>
        <td>${thumb}${btn}</td>
      `;
      body.appendChild(tr);
    }

    bindEvidenceButtons(body);
  };

  const renderRawAlerts = (alerts) => {
    const body = byId("recentAlertsBody");
    if (!body) return;
    body.innerHTML = "";

    const items = alerts || [];
    if (!items.length) {
      body.innerHTML = `<tr><td colspan="7" class="text-secondary">Sin alertas.</td></tr>`;
      return;
    }

    for (const a of items) {
      const tr = document.createElement("tr");
      const id = a.id ?? "-";
      const started = a.timestamp || a.timestamp_iso || "-";
      const ended = "-";
      const conf = Number(a.confidence || 0);
      const count = "-";
      const bbox = a.bbox_text
        ? String(a.bbox_text)
        : Array.isArray(a.bbox) && a.bbox.every((x) => x !== undefined && x !== null)
          ? `${a.bbox[0]},${a.bbox[1]},${a.bbox[2]},${a.bbox[3]}`
          : "-";

      const imgUrl =
        a.evidence_url ||
        a.image_url ||
        (a.image_path ? `/${String(a.image_path).replaceAll("\\", "/")}` : "");
      const thumb = imgUrl
        ? `<img src="${imgUrl}" alt="evidencia" style="max-width:80px;max-height:60px;object-fit:cover;border-radius:6px" />`
        : `<span class="text-secondary">-</span>`;
      const btn = imgUrl
        ? `<button class="btn btn-sm btn-outline-warning ms-2" data-img-url="${imgUrl}" data-conf="${conf}">Ver</button>`
        : ``;

      tr.innerHTML = `
        <td class="mono">${id}</td>
        <td class="mono">${started}</td>
        <td class="mono">${ended}</td>
        <td class="mono">${fmtPct(conf)}</td>
        <td class="mono">${count}</td>
        <td class="mono">${bbox}</td>
        <td>${thumb}${btn}</td>
      `;
      body.appendChild(tr);
    }

    bindEvidenceButtons(body);
  };

  const updateAlerts = async () => {
    if (alertsViewMode === "raw") {
      const data = await fetchJson("/api/recent_alerts?limit=15");
      renderRawAlerts(data.alerts || []);
      return;
    }

    const ev = await fetchJson("/api/recent_detection_events?limit=15");
    const events = ev.events || [];
    if (events.length) {
      renderEventAlerts(events);
      return;
    }

    const data = await fetchJson("/api/recent_alerts?limit=15");
    renderRawAlerts(data.alerts || []);
  };

  const updateCameraUi = async () => {
    const data = await fetchJson("/api/camera_status");
    const mode = String(data.camera_type || "fixed");
    const isPtz = mode === "ptz";
    const hw = byId("hwBadge");
    if (hw) hw.textContent = `Cámara Detectada: ${mode}`;
    const panel = byId("ptzPanel");
    if (panel) panel.style.display = isPtz ? "" : "none";
  };

  const updateDetectionSummary = async () => {
    const data = await fetchJson("/api/detection_summary");
    const totalEvents = Number(data.total_events || 0);
    const openEvents = Number(data.open_events || 0);
    const withEv = Number(data.events_with_evidence || 0);
    const maxConf = Number(data.max_confidence || 0);

    const elEvents = byId("summaryEvents");
    if (elEvents) elEvents.textContent = `Eventos: ${totalEvents} (abiertos: ${openEvents})`;
    const elEv = byId("summaryEvidence");
    if (elEv) elEv.textContent = `Con evidencia: ${withEv}`;
    const elMax = byId("summaryMaxConf");
    if (elMax) elMax.textContent = `Conf máx: ${fmtPct(maxConf)}`;
  };

  const postJson = (url, payload) =>
    fetchJson(url, { method: "POST", body: JSON.stringify(payload || {}) }).catch(() => null);

  const bindPtz = () => {
    const bind = (id, fn) => {
      const el = byId(id);
      if (el) el.addEventListener("click", fn);
    };

    let activeStop = null;
    const stopAll = (ev) => {
      if (typeof activeStop === "function") activeStop(ev);
    };
    window.addEventListener("mouseup", stopAll);
    window.addEventListener("touchend", stopAll);
    window.addEventListener("touchcancel", stopAll);

    const bindHoldMove = (id, vec) => {
      const el = byId(id);
      if (!el) return;

      let ptzMoving = false;
      let stopSent = true;
      const send = () => postJson("/ptz_move", { ...vec, duration_s: 0.6 });

      const start = (ev) => {
        ev?.preventDefault?.();
        if (ptzMoving) return;
        if (typeof activeStop === "function") activeStop(ev);
        ptzMoving = true;
        stopSent = false;
        send();
        activeStop = stop;
      };

      const stop = (ev) => {
        ev?.preventDefault?.();
        ptzMoving = false;
        if (stopSent) return;
        stopSent = true;
        postJson("/api/ptz_stop", { source: "manual", disable_tracking: false });
        if (activeStop === stop) activeStop = null;
      };

      el.addEventListener("mousedown", start);
      el.addEventListener("touchstart", start, { passive: false });
      el.addEventListener("mouseleave", stop);
    };

    bindHoldMove("ptzUp", { x: 0.0, y: 1.0, zoom: 0.0 });
    bindHoldMove("ptzDown", { x: 0.0, y: -1.0, zoom: 0.0 });
    bindHoldMove("ptzLeft", { x: -1.0, y: 0.0, zoom: 0.0 });
    bindHoldMove("ptzRight", { x: 1.0, y: 0.0, zoom: 0.0 });
    const setAutoTrackingButtonState = (enabled) => {
      const t = byId("autoTrackingToggle");
      if (t) t.checked = Boolean(enabled);
    };

    let ptzStopRequestInFlight = false;
    bind("ptzStop", async () => {
      if (ptzStopRequestInFlight) return;
      ptzStopRequestInFlight = true;
      try {
        const res = await postJson("/api/ptz_stop", { source: "manual", disable_tracking: true });
        if (res && res.ok) setAutoTrackingButtonState(false);
      } finally {
        ptzStopRequestInFlight = false;
      }
    });

    const autoToggle = byId("autoTrackingToggle");
    if (autoToggle) {
      let autoTrackingRequestInFlight = false;
      autoToggle.addEventListener("change", async () => {
        if (autoTrackingRequestInFlight) return;
        autoTrackingRequestInFlight = true;
        try {
          await postJson("/api/auto_tracking", { enabled: autoToggle.checked });
        } finally {
          autoTrackingRequestInFlight = false;
        }
      });
      fetchJson("/api/auto_tracking")
        .then((d) => (autoToggle.checked = Boolean(d.enabled)))
        .catch(() => null);
    }

    const inspToggle = byId("inspectionToggle");
    if (inspToggle) {
      let inspectionRequestInFlight = false;
      inspToggle.addEventListener("change", async () => {
        if (inspectionRequestInFlight) return;
        inspectionRequestInFlight = true;
        try {
          await postJson("/api/inspection_mode", { enabled: inspToggle.checked });
        } finally {
          inspectionRequestInFlight = false;
        }
      });
      fetchJson("/api/inspection_mode")
        .then((d) => (inspToggle.checked = Boolean(d.enabled)))
        .catch(() => null);
    }
  };

  let activeJob = null;
  const setBusy = (busy, msg) => {
    const wrap = byId("globalProgressWrap");
    if (wrap) wrap.classList.toggle("d-none", !busy);
    const spin = byId("globalSpinner");
    if (spin) spin.style.display = busy ? "" : "none";
    const reset = byId("btnReset");
    if (reset) reset.disabled = busy;
    if (msg) setText("globalProgressStatus", String(msg));
  };

  const clearResultsUi = () => {
    activeJob = null;
    byId("resultImage")?.classList.add("d-none");
    byId("resultVideo")?.classList.add("d-none");
    byId("topDetectionsSection")?.classList.add("d-none");
    byId("btnDownload")?.classList.add("d-none");
    setText("mDet", "0");
    setText("mConf", "0%");
    setText("mFrames", "-");
    setText("globalProgressText", "0%");
    const bar = byId("globalProgressBar");
    if (bar) {
      bar.style.width = "0%";
      bar.textContent = "0%";
    }
    setText("globalProgressStatus", "En espera");
    const area = byId("flash-area");
    if (area) area.innerHTML = "";
  };

  const resetManualUi = () => {
    activeJob = null;
    const inp = byId("fileInput");
    if (inp) inp.value = "";
    setBusy(false);
    setText("globalProgressText", "0%");
    const bar = byId("globalProgressBar");
    if (bar) {
      bar.style.width = "0%";
      bar.textContent = "0%";
    }
    setText("globalProgressStatus", "En espera");
    byId("resultImage")?.classList.add("d-none");
    byId("resultVideo")?.classList.add("d-none");
    byId("topDetectionsSection")?.classList.add("d-none");
    byId("btnDownload")?.classList.add("d-none");
    setText("mDet", "0");
    setText("mConf", "0%");
    setText("mFrames", "-");
    const area = byId("flash-area");
    if (area) area.innerHTML = "";
  };

  const renderTopDetections = (items) => {
    const section = byId("topDetectionsSection");
    const grid = byId("topDetectionsGrid");
    if (!section || !grid) return;
    const list = items || [];
    if (!list.length) {
      section.classList.add("d-none");
      grid.innerHTML = "";
      return;
    }
    section.classList.remove("d-none");
    grid.innerHTML = "";

    for (const it of list) {
      const conf = Number(it.confidence || 0);
      const img = String(it.image_base64 || "");
      const col = document.createElement("div");
      col.className = "col-6 col-md-4 col-lg-3";
      col.innerHTML = `
        <div class="card h-100">
          <img class="img-fluid rounded" style="cursor:pointer; border:1px solid rgba(48,54,61,.6)" src="${img}" alt="Detección" />
          <div class="card-body py-2">
            <div class="small text-secondary">Confianza</div>
            <div class="mono">${fmtPct(conf)}</div>
          </div>
        </div>
      `;
      col.querySelector("img")?.addEventListener("click", () => {
        const modalEl = byId("imagenModal");
        const big = byId("imagenExpandida");
        const txt = byId("confianzaTexto");
        if (big) big.src = img;
        if (txt) txt.textContent = `Nivel de confianza: ${fmtPct(conf)}`;
        if (modalEl && window.bootstrap?.Modal) new window.bootstrap.Modal(modalEl).show();
      });
      grid.appendChild(col);
    }
  };

  const pollJob = async (jobId) => {
    activeJob = jobId;
    setBusy(true, "Procesando...");

    const tick = async () => {
      if (activeJob !== jobId) return;
      try {
        const data = await fetchJson(`/video_progress?job_id=${encodeURIComponent(jobId)}`);
        const p = Number(data.progress || 0);
        const done = Boolean(data.done);
        const status = String(data.status || "");

        const pct = `${Math.max(0, Math.min(100, Math.round(p)))}%`;
        setText("globalProgressText", pct);
        const bar = byId("globalProgressBar");
        if (bar) {
          bar.style.width = pct;
          bar.textContent = pct;
        }
        setText("globalProgressStatus", status || "Procesando");

          if (done) {
            setBusy(false);
            setText("globalProgressStatus", "Completado");
            showFlash("success", "Completado");
            if (!data.success) {
              showFlash("danger", data.error || "Error");
              return;
            }

          const url = String(data.result_url || "");
          const typ = String(data.result_type || "");
          const btn = byId("btnDownload");
          const dlVideo = byId("downloadResultVideo");
          const warning = data.video_output_warning ? String(data.video_output_warning) : "";
          if (warning) showFlash("warning", warning);

          if (typ === "image") {
            const img = byId("resultImage");
            if (img && url) {
              img.src = url;
              img.classList.remove("d-none");
            }
            byId("resultVideo")?.classList.add("d-none");
            if (btn) btn.classList.add("d-none");
            if (dlVideo) dlVideo.classList.add("d-none");
            setText("mDet", String(data.detections_count ?? 0));
            setText("mConf", fmtPct(data.avg_confidence ?? 0));
            setText("mFrames", "-");
            renderTopDetections([]);
          } else if (typ === "video") {
            console.log("[VIDEO_RESULT]", data);
            const vid = byId("resultVideo");
            const src = byId("resultVideoSource");
            const playable = Boolean(data.result_video_playable ?? true);
            const vurl = String(data.result_video_url || url || "");
            const rawUrl = String(data.result_video_raw_url || "");
            const mime = String(data.result_video_mime || "video/mp4");
            const openTab = byId("openResultVideoTab");
            const cacheBustUrl = vurl
              ? `${vurl}${vurl.includes("?") ? "&" : "?"}v=${encodeURIComponent(`${jobId}-${Date.now()}`)}`
              : "";

            const setDownload = (el, href) => {
              if (!el) return;
              if (href) {
                el.href = href;
                el.classList.remove("d-none");
              } else {
                el.classList.add("d-none");
              }
            };
            // Descargar siempre debe apuntar al raw si está disponible (útil aunque el browser mp4 exista).
            setDownload(btn, rawUrl || vurl);
            setDownload(dlVideo, rawUrl || vurl);
            setDownload(openTab, vurl || rawUrl);

            if (!cacheBustUrl) {
              vid?.classList.add("d-none");
              showFlash("warning", "El análisis terminó, pero no se recibió URL del video procesado.");
            } else if (playable && vid) {
              // Limpieza fuerte antes de asignar un nuevo video.
              try {
                vid.pause();
                vid.removeAttribute("src");
                if (src) src.removeAttribute("src");
                vid.load();
              } catch {}

              if (src) {
                // Evitar conflictos: usamos `video.src` como fuente de verdad.
                src.removeAttribute("src");
              }

              // Asignar solo una vez.
              vid.src = cacheBustUrl;

              // Debug útil (no fatal).
              vid.onloadstart = () => console.log("[VIDEO_PLAYER] loadstart", cacheBustUrl);
              vid.onloadedmetadata = () => console.log("[VIDEO_PLAYER] loadedmetadata", vid.duration);
              vid.oncanplay = () => console.log("[VIDEO_PLAYER] canplay");
              vid.onplaying = () => console.log("[VIDEO_PLAYER] playing");
              vid.onstalled = () => console.warn("[VIDEO_PLAYER] stalled; waiting for browser buffer", cacheBustUrl);
              vid.onerror = () => {
                console.error("[VIDEO_PLAYER] error", vid.error, cacheBustUrl);
                vid.classList.add("d-none");
                showFlash("warning", "No se pudo cargar el video procesado en el reproductor. Use Descargar.");
              };

              // tipo mime sugerido
              try {
                vid.type = mime || "video/mp4";
              } catch {}
              vid.load();
              vid.classList.remove("d-none");
            } else {
              vid?.classList.add("d-none");
              showFlash("warning", "El video procesado no es reproducible en el navegador. Use Descargar.");
            }
            byId("resultImage")?.classList.add("d-none");
            setText("mDet", String(data.total_detections ?? 0));
            setText("mConf", fmtPct(data.avg_confidence ?? 0));
            setText("mFrames", String(data.frames_processed ?? "-"));
            renderTopDetections(data.top_detections || []);
          }
          return;
        }
      } catch {
        // Mantener polling.
      }
      setTimeout(tick, 500);
    };
    tick();
  };

  const bindManual = () => {
    const input = byId("fileInput");
    const reset = byId("btnReset");
    if (!input || !reset) return;

    const startUpload = async () => {
      if (!input.files || !input.files[0]) return;

      clearResultsUi();

      const fd = new FormData();
      fd.append("file", input.files[0]);

      setBusy(true, "Procesando...");
      showFlash("secondary", "Encolado");
      try {
        const res = await fetch("/upload_detect", { method: "POST", credentials: "same-origin", body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.success) {
          setBusy(false);
          showFlash("danger", data.error || data.message || "Error");
          return;
        }
        showFlash("success", "En proceso");
        await pollJob(String(data.job_id));
      } catch {
        setBusy(false);
        showFlash("danger", "Error");
      }
    };

    input.addEventListener("change", () => {
      const has = input.files && input.files.length > 0;
      if (has) startUpload();
    });

    reset.addEventListener("click", () => resetManualUi());
  };

  const boot = async () => {
    byId("btnAlertsEvents")?.addEventListener("click", () => {
      alertsViewMode = "events";
      updateAlerts().catch(() => null);
    });
    byId("btnAlertsRaw")?.addEventListener("click", () => {
      alertsViewMode = "raw";
      updateAlerts().catch(() => null);
    });
    bindPtz();
    bindManual();

    await Promise.allSettled([updateStatus(), updateAlerts(), updateCameraUi(), updateDetectionSummary()]);
    setInterval(() => updateStatus().catch(() => null), 2000);
    setInterval(() => updateAlerts().catch(() => null), 4000);
    setInterval(() => updateCameraUi().catch(() => null), 5000);
    setInterval(() => updateDetectionSummary().catch(() => null), 7000);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => boot().catch(() => null));
  } else {
    boot().catch(() => null);
  }
})();
