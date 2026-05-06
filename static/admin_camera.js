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

  const setAlert = (id, msg) => {
    const el = byId(id);
    if (!el) return;
    el.textContent = String(msg || "");
    el.classList.remove("d-none");
  };

  const clearAlerts = () => {
    ["testError", "testSuccess", "testWarning"].forEach((id) => {
      const el = byId(id);
      if (el) {
        el.textContent = "";
        el.classList.add("d-none");
      }
    });
  };

  const boot = () => {
    document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sel = btn.getAttribute("data-toggle-password");
        if (!sel) return;
        const input = document.querySelector(sel);
        if (!input) return;
        const isPwd = input.getAttribute("type") === "password";
        input.setAttribute("type", isPwd ? "text" : "password");
        const icon = btn.querySelector("i");
        if (icon) {
          icon.classList.toggle("fa-eye", !isPwd);
          icon.classList.toggle("fa-eye-slash", isPwd);
        }
      });
    });

    const sameCreds = byId("sameCreds");
    const onvifRow = byId("onvifCredsRow");
    if (sameCreds && onvifRow) {
      const apply = () => {
        const checked = Boolean(sameCreds.checked);
        onvifRow.classList.toggle("d-none", checked);
        if (checked) {
          const ru = byId("rtsp_username")?.value ?? "";
          const rp = byId("rtsp_password")?.value ?? "";
          const ou = byId("onvif_username");
          const op = byId("onvif_password");
          if (ou && !ou.value) ou.value = ru;
          if (op && !op.value) op.value = rp;
        }
      };
      sameCreds.addEventListener("change", apply);
      apply();
    }

    const btn = byId("btnLinkTest");
    const spinner = byId("btnSpinner");
    if (btn) {
      btn.addEventListener("click", async () => {
        clearAlerts();
        show("snapshotWrap", false);
        if (spinner) spinner.classList.remove("d-none");
        btn.disabled = true;

        const payload = {
          onvif_host: byId("onvif_host")?.value ?? "",
          onvif_port: byId("onvif_port")?.value ?? "",
          onvif_username: byId("onvif_username")?.value ?? "",
          onvif_password: byId("onvif_password")?.value ?? "",
          rtsp_url: byId("rtsp_url")?.value ?? "",
          rtsp_username: byId("rtsp_username")?.value ?? "",
          rtsp_password: byId("rtsp_password")?.value ?? "",
        };

        try {
          const data = await fetchJson("/api/test_connection", {
            method: "POST",
            body: JSON.stringify(payload),
          });

          const isPtz = Boolean(data.is_ptz);
          const badge = byId("cameraModeBadge");
          if (badge) {
            badge.textContent = isPtz ? "PTZ detectado" : "Cámara fija";
            badge.classList.remove("d-none");
          }

          const cameraType = byId("camera_type");
          if (cameraType) cameraType.value = isPtz ? "ptz" : "fixed";

          setAlert("testSuccess", "Conexión verificada.");
          if (data.warning) setAlert("testWarning", String(data.warning));

          const snapUrl = data.snapshot_url ? String(data.snapshot_url) : "";
          if (snapUrl) {
            const img = byId("snapshotImg");
            const cap = byId("snapshotCaption");
            if (img) img.src = `${snapUrl}?t=${Date.now()}`;
            if (cap) cap.textContent = "Vista previa";
            show("snapshotWrap", true);
          } else if (data.snapshot_b64) {
            const img = byId("snapshotImg");
            const cap = byId("snapshotCaption");
            if (img) img.src = `data:image/jpeg;base64,${String(data.snapshot_b64)}`;
            if (cap) cap.textContent = "Vista previa";
            show("snapshotWrap", true);
          }
        } catch (e) {
          setAlert("testError", e?.data?.message || e?.data?.error || "Error");
        } finally {
          if (spinner) spinner.classList.add("d-none");
          btn.disabled = false;
        }
      });
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
