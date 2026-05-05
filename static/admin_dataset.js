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
    ["datasetErr", "datasetOk", "historyErr", "historyOk"].forEach((id) => {
      const el = byId(id);
      if (el) {
        el.textContent = "";
        el.classList.add("d-none");
      }
    });
  };

  const renderGrid = (gridId, images) => {
    const grid = byId(gridId);
    if (!grid) return;
    grid.innerHTML = "";
    const items = images || [];
    if (!items.length) {
      grid.innerHTML = `<div class="text-secondary">Sin elementos.</div>`;
      return;
    }

    for (const it of items) {
      const src = `/api/dataset_image?path=${encodeURIComponent(it.path || it)}`;
      const col = document.createElement("div");
      col.className = "col-6 col-md-4 col-lg-3";
      col.innerHTML = `
        <div class="card h-100">
          <img class="img-fluid rounded" style="border:1px solid rgba(48,54,61,.6)" src="${src}" alt="Imagen" />
          <div class="card-body py-2">
            <div class="d-flex gap-2">
              <button class="btn btn-sm btn-outline-success w-100" data-action="ok">Aprobada</button>
              <button class="btn btn-sm btn-outline-danger w-100" data-action="bad">Rechazada</button>
            </div>
          </div>
        </div>
      `;
      col.querySelectorAll("button[data-action]").forEach((b) => {
        b.addEventListener("click", async () => {
          clearAlerts();
          try {
            await fetchJson("/api/classify_image", {
              method: "POST",
              body: JSON.stringify({ path: it.path || it, label: b.dataset.action }),
            });
            setAlert("datasetOk", "Actualizado.");
          } catch (e) {
            setAlert("datasetErr", e?.data?.message || e?.data?.error || "Error");
          }
        });
      });
      grid.appendChild(col);
    }
  };

  const loadPending = async () => {
    clearAlerts();
    try {
      const data = await fetchJson("/api/get_dataset_images");
      renderGrid("datasetGrid", data.images || []);
    } catch (e) {
      setAlert("datasetErr", e?.data?.message || e?.data?.error || "Error");
    }
  };

  const loadHistory = async () => {
    clearAlerts();
    try {
      const data = await fetchJson("/api/get_classified_images");
      const grid = byId("historyGrid");
      if (!grid) return;
      grid.innerHTML = "";
      const items = data.images || [];
      if (!items.length) {
        grid.innerHTML = `<div class="text-secondary">Sin elementos.</div>`;
        return;
      }
      for (const it of items) {
        const src = `/api/classified_image?path=${encodeURIComponent(it.path || it)}`;
        const col = document.createElement("div");
        col.className = "col-6 col-md-4 col-lg-3";
        col.innerHTML = `
          <div class="card h-100">
            <img class="img-fluid rounded" style="border:1px solid rgba(48,54,61,.6)" src="${src}" alt="Imagen" />
            <div class="card-body py-2">
              <button class="btn btn-sm btn-outline-warning w-100" data-action="revert">Revertir</button>
            </div>
          </div>
        `;
        col.querySelector("button[data-action='revert']")?.addEventListener("click", async () => {
          clearAlerts();
          try {
            await fetchJson("/api/revert_classification", { method: "POST", body: JSON.stringify({ path: it.path || it }) });
            setAlert("historyOk", "Revertido.");
          } catch (e) {
            setAlert("historyErr", e?.data?.message || e?.data?.error || "Error");
          }
        });
        grid.appendChild(col);
      }
    } catch (e) {
      setAlert("historyErr", e?.data?.message || e?.data?.error || "Error");
    }
  };

  const boot = () => {
    byId("btnRefreshDataset")?.addEventListener("click", () => loadPending().catch(() => null));
    byId("btnRefreshHistory")?.addEventListener("click", () => loadHistory().catch(() => null));
    loadPending().catch(() => null);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

