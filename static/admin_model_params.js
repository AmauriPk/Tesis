(() => {
  const byId = (id) => document.getElementById(id);

  const fetchJson = async (url, opts = {}) => {
    const res = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw Object.assign(new Error(`${res.status}`), { data });
    return data;
  };

  const show = (id, showIt) => {
    const el = byId(id);
    if (!el) return;
    el.classList.toggle("d-none", !showIt);
  };

  const setText = (id, text) => {
    const el = byId(id);
    if (el) el.textContent = String(text);
  };

  const boot = () => {
    const conf = byId("confSlider");
    const pers = byId("persSlider");
    const iou = byId("iouSlider");
    const btn = byId("btnSaveParams");

    const sync = () => {
      if (conf) setText("confValue", Number(conf.value).toFixed(2));
      if (pers) setText("persValue", String(pers.value));
      if (iou) setText("iouValue", Number(iou.value).toFixed(2));
    };

    [conf, pers, iou].forEach((el) => el && el.addEventListener("input", sync));
    sync();

    if (!btn) return;
    btn.addEventListener("click", async () => {
      show("paramsOk", false);
      show("paramsErr", false);
      show("paramsSpinner", true);
      btn.disabled = true;
      try {
        const payload = {
          confidence_threshold: Number(conf?.value ?? 0.6),
          persistence_frames: Number(pers?.value ?? 3),
          iou_threshold: Number(iou?.value ?? 0.45),
        };
        await fetchJson("/api/update_model_params", { method: "POST", body: JSON.stringify(payload) });
        show("paramsOk", true);
      } catch (e) {
        const msg = e?.data?.message || e?.data?.error || "Error";
        const el = byId("paramsErr");
        if (el) el.textContent = String(msg);
        show("paramsErr", true);
      } finally {
        show("paramsSpinner", false);
        btn.disabled = false;
      }
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

