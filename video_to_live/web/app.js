const DEFAULT_WINDOW = 1.0;
const MIN_SPAN = 0.05;
const SQUEEZE_AFTER = 1.05;

const fileInput = document.getElementById("file");
const drop = document.getElementById("drop");
const dropLabel = document.getElementById("drop-label");
const studio = document.getElementById("studio");
const preview = document.getElementById("preview");
const times = document.getElementById("times");
const meta = document.getElementById("meta");
const statusEl = document.getElementById("status");
const gerar = document.getElementById("gerar");
const timeline = document.getElementById("timeline");
const rangeEl = document.getElementById("range");
const handleIn = document.getElementById("handle-in");
const handleOut = document.getElementById("handle-out");

let file = null;
let duration = 1;
let inTime = 0;
let outTime = 1;
let objectUrl = null;
let dragging = null;

function fmt(seconds) {
  const value = Math.max(0, seconds);
  return value.toFixed(2).replace(".", ",") + "s";
}

function clampRange() {
  duration = Number.isFinite(preview.duration) && preview.duration > 0 ? preview.duration : duration;
  const maxOut = duration;
  if (outTime > maxOut) outTime = maxOut;
  if (inTime < 0) inTime = 0;
  if (outTime - inTime < MIN_SPAN) {
    if (dragging === "in") inTime = Math.max(0, outTime - MIN_SPAN);
    else outTime = Math.min(maxOut, inTime + MIN_SPAN);
  }
}

function render() {
  clampRange();
  const span = outTime - inTime;
  times.textContent = `${fmt(inTime)} → ${fmt(outTime)}`;
  meta.textContent = span > SQUEEZE_AFTER ? `${fmt(span)} · acelerado pra caber` : "";
  const left = duration > 0 ? (inTime / duration) * 100 : 0;
  const width = duration > 0 ? (span / duration) * 100 : 0;
  rangeEl.style.left = `${left}%`;
  rangeEl.style.width = `${width}%`;
  handleIn.style.left = `${left}%`;
  handleOut.style.left = `${left + width}%`;
}

function loopPreview() {
  if (preview.paused) return;
  if (preview.currentTime < inTime - 0.04 || preview.currentTime >= outTime) {
    preview.currentTime = inTime;
  }
}

function loadFile(next) {
  file = next;
  dropLabel.textContent = next.name;
  studio.hidden = false;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(next);
  preview.src = objectUrl;
  statusEl.textContent = "";
  statusEl.className = "status";
}

preview.addEventListener("loadedmetadata", () => {
  duration = preview.duration;
  inTime = 0;
  outTime = Math.min(DEFAULT_WINDOW, duration);
  render();
  preview.currentTime = inTime;
  preview.play().catch(() => {});
});

preview.addEventListener("timeupdate", loopPreview);
preview.addEventListener("ended", () => {
  preview.currentTime = inTime;
  preview.play().catch(() => {});
});

drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("dragover", (event) => {
  event.preventDefault();
  drop.classList.add("over");
});
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (event) => {
  event.preventDefault();
  drop.classList.remove("over");
  const next = event.dataTransfer.files[0];
  if (next) loadFile(next);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) loadFile(fileInput.files[0]);
});

function timeFromClientX(clientX) {
  const box = timeline.querySelector(".track").getBoundingClientRect();
  const ratio = Math.min(1, Math.max(0, (clientX - box.left) / box.width));
  return ratio * duration;
}

function startDrag(which, event) {
  event.preventDefault();
  dragging = which;
  event.currentTarget.setPointerCapture?.(event.pointerId);
}

handleIn.addEventListener("pointerdown", (event) => startDrag("in", event));
handleOut.addEventListener("pointerdown", (event) => startDrag("out", event));
window.addEventListener("pointermove", (event) => {
  if (!dragging) return;
  const t = timeFromClientX(event.clientX);
  if (dragging === "in") inTime = Math.min(t, outTime - MIN_SPAN);
  else outTime = Math.max(t, inTime + MIN_SPAN);
  render();
  preview.currentTime = dragging === "in" ? inTime : Math.max(inTime, outTime - 0.05);
});
window.addEventListener("pointerup", () => {
  dragging = null;
});

timeline.addEventListener("pointerdown", (event) => {
  if (event.target.classList.contains("handle")) return;
  const t = timeFromClientX(event.clientX);
  const mid = (inTime + outTime) / 2;
  dragging = t < mid ? "in" : "out";
  if (dragging === "in") inTime = Math.min(t, outTime - MIN_SPAN);
  else outTime = Math.max(t, inTime + MIN_SPAN);
  render();
});

gerar.addEventListener("click", async () => {
  if (!file) {
    statusEl.textContent = "Solta um vídeo primeiro.";
    statusEl.className = "status erro";
    return;
  }
  gerar.disabled = true;
  statusEl.className = "status";
  statusEl.textContent = "Gerando…";
  const body = new FormData();
  body.append("video", file, file.name);
  body.append("start", String(inTime));
  body.append("end", String(outTime));
  try {
    const response = await fetch("/gerar", { method: "POST", body });
    if (!response.ok) {
      let message = "Não rolou.";
      try {
        const payload = await response.json();
        if (payload.erro) message = payload.erro;
      } catch {
        /* keep default */
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    const saved = response.headers.get("X-Saved-To");
    const name = (file.name.replace(/\.[^.]+$/, "") || "live") + ".pvt.zip";
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
    statusEl.className = "status ok";
    statusEl.textContent = saved
      ? `Pronto. Salvo em ${saved}. AirDrop a pasta pro Fotos.`
      : "Pronto. Descompacta e AirDrop a pasta pro Fotos.";
  } catch (error) {
    statusEl.className = "status erro";
    statusEl.textContent = error.message || "Não rolou.";
  } finally {
    gerar.disabled = false;
  }
});
