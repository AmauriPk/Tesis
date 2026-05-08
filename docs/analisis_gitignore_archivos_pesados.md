# Análisis de .gitignore y Archivos Pesados — SIRAN

Fecha: 2026-05-07

---

## Estado actual de .gitignore

| Patrón requerido | Presente | Estado |
|---|---|---|
| `.env` | ✅ | OK |
| `config_camara.json` | ✅ | OK |
| `*.db`, `*.db-shm`, `*.db-wal` | ✅ | OK |
| `*.pt`, `*.pth` | ✅ | OK |
| `*.onnx`, `*.tflite` | ✅ | OK |
| `venv_new/` | ✅ | OK |
| `env/`, `ENV/` | ✅ | OK |
| `venv/` (nombre alternativo común) | ❌ | **Faltante** — agregado en esta sesión |
| `__pycache__/` | ✅ | OK |
| `*.pyc`, `*.pyo`, `*.pyd` | ✅ | OK |
| `uploads/` | ✅ | OK |
| `static/results/` | ✅ | OK |
| `static/evidence/` | ✅ | OK |
| `static/evidencia/` | ✅ | OK (alias histórico) |
| `static/top_detections/` | ✅ | OK |
| `static/capturas/` | ✅ | OK |
| `dataset_entrenamiento/` | ✅ | OK |
| `dataset_recoleccion/` | ✅ | OK |
| `runs/` | ✅ | OK |
| `instance/` | ✅ | OK |
| `*.log` | ✅ | OK |
| `.vscode/`, `.idea/` | ✅ | OK |
| `.DS_Store`, `Thumbs.db` | ✅ | OK |
| `.claude/` | ✅ | OK |
| `Indicacion para git.txt` | ✅ | OK |
| `*.mp4`, `*.avi` en `static/results/` | ✅ | OK (patrón específico) |
| `*.mp4`, `*.avi` en raíz o uploads | ❌ | Solo protegidos en static/results. **Agregados globalmente** |
| `*.mov` en raíz/uploads | ❌ | Solo en static/results. **Agregado globalmente** |

---

## Cambios aplicados al .gitignore

1. Agregado `venv/` para cubrir el nombre de venv más común.
2. Agregados patrones globales para archivos de video grandes:
   - `*.mp4`
   - `*.avi`
   - `*.mov`
   (Complementan los existentes que solo cubrían `static/results/`)

---

## Archivos potencialmente grandes en el repositorio

Revisar con `git ls-files` si alguno de los siguientes fue rastreado accidentalmente antes de configurar .gitignore:

| Tipo | Patrón | Acción si está rastreado |
|---|---|---|
| Modelos YOLO | `*.pt` | `git rm --cached archivo.pt` |
| Bases de datos | `*.db` | `git rm --cached detections.db` |
| Videos de resultado | `*.mp4`, `*.avi` | `git rm --cached` |
| Entorno virtual | `venv_new/` | `git rm -r --cached venv_new/` si se coló |
| Dataset de imágenes | `dataset/`, `dataset_entrenamiento/` | Verificar |

**NOTA**: No ejecutar `git rm --cached` en esta sesión sin confirmación del usuario. Solo documentar.

---

## Advertencia sobre `config_camara.json`

El archivo `config_camara.json` contiene solo `{"is_ptz": bool}` — sin credenciales. Aunque está en .gitignore, si fue rastreado antes de agregar la regla, puede estar en el historial. Para verificar:

```bash
git log --all --full-history -- config_camara.json
```

Si aparece en el historial y contiene información sensible, considerar `git filter-repo` post-defensa.

---

## Dataset en el repositorio

El directorio `dataset/` contiene imágenes de entrenamiento y está en .gitignore. Sin embargo, se observa que hay un directorio `dataset/` con archivos `*.txt` de labels (formato YOLO). Verificar que este directorio no esté siendo rastreado:

```bash
git ls-files dataset/
```

Si aparece, ejecutar:
```bash
git rm -r --cached dataset/
```

(Pendiente de confirmación del usuario.)
