(() => {
  const byId = (id) => document.getElementById(id);

  const fetchJson = async (url, opts = {}) => {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
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
  };

  const renderAlerts = (alerts) => {
    const body = byId("recentAlertsBody");
    if (!body) return;
    body.innerHTML = "";

    const items = alerts || [];
    if (!items.length) {
      body.innerHTML = `<tr><td colspan="5" class="text-secondary">Sin alertas.</td></tr>`;
      return;
    }

    for (const a of items) {
      const tr = document.createElement("tr");
      const id = a.id ?? "-";
      const ts = a.timestamp || a.timestamp_iso || "-";
      const conf = Number(a.confidence || 0);
      const bbox = [a.x1, a.y1, a.x2, a.y2].every((x) => x !== undefined && x !== null)
        ? `${a.x1},${a.y1},${a.x2},${a.y2}`
        : "-";

      const imgPath = a.image_path ? String(a.image_path) : "";
      const btn = imgPath
        ? `<button class="btn btn-sm btn-outline-warning" data-img="${imgPath}" data-conf="${conf}">Ver</button>`
        : `<span class="text-secondary">-</span>`;

      tr.innerHTML = `
        <td class="mono">${id}</td>
        <td class="mono">${ts}</td>
        <td class="mono">${fmtPct(conf)}</td>
        <td class="mono">${bbox}</td>
        <td>${btn}</td>
      `;
      body.appendChild(tr);
    }

    body.querySelectorAll("button[data-img]").forEach((b) => {
      b.addEventListener("click", () => {
        const img = byId("evidenceImage");
        const meta = byId("evidenceMeta");
        const modalEl = byId("evidenceModal");
        if (!img || !modalEl) return;
        img.src = `/${b.dataset.img}`.replaceAll("//", "/");
        if (meta) meta.textContent = `Confianza: ${fmtPct(b.dataset.conf)}`;
        if (window.bootstrap?.Modal) new window.bootstrap.Modal(modalEl).show();
      });
    });
  };

  const updateAlerts = async () => {
    const data = await fetchJson("/api/recent_alerts?limit=15");
    renderAlerts(data.alerts || []);
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

  const postJson = (url, payload) =>
    fetchJson(url, { method: "POST", body: JSON.stringify(payload || {}) }).catch(() => null);

  const bindPtz = () => {
    const bind = (id, fn) => {
      const el = byId(id);
      if (el) el.addEventListener("click", fn);
    };

    bind("ptzUp", () => postJson("/ptz_move", { direction: "up" }));
    bind("ptzDown", () => postJson("/ptz_move", { direction: "down" }));
    bind("ptzLeft", () => postJson("/ptz_move", { direction: "left" }));
    bind("ptzRight", () => postJson("/ptz_move", { direction: "right" }));
    bind("ptzStop", () => postJson("/ptz_stop", {}));

    const autoToggle = byId("autoTrackingToggle");
    if (autoToggle) {
      autoToggle.addEventListener("change", () => postJson("/api/auto_tracking", { enabled: autoToggle.checked }));
      fetchJson("/api/auto_tracking")
        .then((d) => (autoToggle.checked = Boolean(d.enabled)))
        .catch(() => null);
    }

    const inspToggle = byId("inspectionToggle");
    if (inspToggle) {
      inspToggle.addEventListener("change", () => postJson("/api/inspection_mode", { enabled: inspToggle.checked }));
      fetchJson("/api/inspection_mode")
        .then((d) => (inspToggle.checked = Boolean(d.enabled)))
        .catch(() => null);
    }
  };

  let activeJob = null;
  const setBusy = (busy, msg) => {
    byId("spinnerBox")?.classList.toggle("d-none", !busy);
    byId("progressWrap")?.classList.toggle("d-none", !busy);
    const upload = byId("btnUpload");
    const reset = byId("btnReset");
    if (upload) upload.disabled = busy;
    if (reset) reset.disabled = busy;
    const sm = byId("spinnerMsg");
    if (sm && msg) sm.textContent = String(msg);
  };

  const resetManualUi = () => {
    activeJob = null;
    const inp = byId("fileInput");
    if (inp) inp.value = "";
    byId("btnUpload")?.classList.add("d-none");
    setBusy(false);
    setText("progressText", "0%");
    const bar = byId("progressBar");
    if (bar) {
      bar.style.width = "0%";
      bar.textContent = "0%";
    }
    setText("progressStatus", "En espera");
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
        setText("progressText", pct);
        const bar = byId("progressBar");
        if (bar) {
          bar.style.width = pct;
          bar.textContent = pct;
        }
        setText("progressStatus", status || "Procesando");

        if (done) {
          setBusy(false);
          if (!data.success) {
            showFlash("danger", data.error || "Error");
            return;
          }

          const url = String(data.result_url || "");
          const typ = String(data.result_type || "");
          const btn = byId("btnDownload");
          if (btn && url) {
            btn.href = url;
            btn.classList.remove("d-none");
          }

          if (typ === "image") {
            const img = byId("resultImage");
            if (img && url) {
              img.src = url;
              img.classList.remove("d-none");
            }
            byId("resultVideo")?.classList.add("d-none");
            setText("mDet", String(data.detections_count ?? 0));
            setText("mConf", fmtPct(data.avg_confidence ?? 0));
            setText("mFrames", "-");
            renderTopDetections([]);
          } else if (typ === "video") {
            const vid = byId("resultVideo");
            const src = byId("resultVideoSource");
            if (vid && src && url) {
              src.src = url;
              vid.load();
              vid.classList.remove("d-none");
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
    const upload = byId("btnUpload");
    const reset = byId("btnReset");
    if (!input || !upload || !reset) return;

    input.addEventListener("change", () => {
      const has = input.files && input.files.length > 0;
      upload.classList.toggle("d-none", !has);
    });

    reset.addEventListener("click", () => resetManualUi());

    upload.addEventListener("click", async () => {
      if (!input.files || !input.files[0]) return;
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
    });
  };

  const boot = async () => {
    bindPtz();
    bindManual();

    byId("btnRefresh")?.addEventListener("click", async () => {
      await Promise.allSettled([updateStatus(), updateAlerts(), updateCameraUi()]);
    });

    await Promise.allSettled([updateStatus(), updateAlerts(), updateCameraUi()]);
    setInterval(() => updateStatus().catch(() => null), 1000);
    setInterval(() => updateAlerts().catch(() => null), 2000);
    setInterval(() => updateCameraUi().catch(() => null), 3000);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => boot().catch(() => null));
  } else {
    boot().catch(() => null);
  }
})();

