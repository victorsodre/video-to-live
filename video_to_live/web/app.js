const DEFAULT_WINDOW = 1.0;
const MIN_SPAN = 0.05;
const SQUEEZE_AFTER = 1.05;
const LANGUAGE_KEY = "video-to-live.locale";

const messages = {
  en: {
    kicker: "lock screen", languageLabel: "Language", title: "Live Photo for your Lock Screen",
    lede: "Drop a video, choose a clip, and create it.", dropLabel: "Drop a video here, or click to choose one.",
    clipRange: "Clip range", start: "Start", end: "End",
    hint: "The Lock Screen uses about one second. Longer clips are sped up to fit.",
    generate: "Create Live Photo", speedingUp: "sped up to fit", chooseVideo: "Choose a video first.",
    generating: "Creating Live Photo…", failed: "The Live Photo could not be created.",
    saved: "Ready. Saved to {path}. AirDrop the folder to Photos.",
    ready: "Ready. Unzip the download, then AirDrop the folder to Photos.",
    originNotAllowed: "This request is not allowed from this origin.",
    notFound: "The requested resource was not found.",
    alreadyProcessing: "Another video is being processed. Try again shortly.",
    uploadTimedOut: "The upload exceeded the time limit.",
    conversionFailed: "The video could not be converted. Check its format and clip range.",
    conversionIncomplete: "The conversion could not be completed.",
    invalidLength: "Send a valid Content-Length header.", missingVideo: "No video was received.",
    uploadLimit: "The upload limit is 128 MiB. Use the local CLI for larger files.",
    formRequired: "Send the video through the form.", incompleteUpload: "The file upload was incomplete.",
    nonFiniteRange: "The range must contain finite numbers.",
  },
  "pt-BR": {
    kicker: "tela de bloqueio", languageLabel: "Idioma", title: "Live Photo para a tela de bloqueio",
    lede: "Solte um vídeo, escolha um trecho e gere.", dropLabel: "Solte o vídeo aqui ou clique para escolher.",
    clipRange: "Trecho", start: "Início", end: "Fim",
    hint: "A tela de bloqueio usa cerca de um segundo. Trechos maiores são acelerados para caber.",
    generate: "Gerar Live Photo", speedingUp: "acelerado para caber", chooseVideo: "Escolha um vídeo primeiro.",
    generating: "Gerando Live Photo…", failed: "Não foi possível gerar a Live Photo.",
    saved: "Pronto. Salvo em {path}. Envie a pasta por AirDrop para o Fotos.",
    ready: "Pronto. Descompacte o download e envie a pasta por AirDrop para o Fotos.",
    originNotAllowed: "Esta solicitação não é permitida a partir desta origem.",
    notFound: "O recurso solicitado não foi encontrado.",
    alreadyProcessing: "Outro vídeo está sendo processado. Tente novamente em instantes.",
    uploadTimedOut: "O envio excedeu o limite de tempo.",
    conversionFailed: "Não foi possível converter o vídeo. Verifique o formato e o trecho escolhido.",
    conversionIncomplete: "Não foi possível concluir a conversão.",
    invalidLength: "Envie um cabeçalho Content-Length válido.", missingVideo: "Nenhum vídeo foi recebido.",
    uploadLimit: "O limite de upload é 128 MiB. Para arquivos maiores, use a CLI local.",
    formRequired: "Envie o vídeo pelo formulário.", incompleteUpload: "O envio do arquivo ficou incompleto.",
    nonFiniteRange: "O trecho precisa conter números finitos.",
  },
};

const byId = (id) => document.getElementById(id);
const fileInput = byId("file");
const drop = byId("drop");
const dropLabel = byId("drop-label");
const studio = byId("studio");
const preview = byId("preview");
const times = byId("times");
const meta = byId("meta");
const statusEl = byId("status");
const generate = byId("generate");
const timeline = byId("timeline");
const rangeEl = byId("range");
const handleIn = byId("handle-in");
const handleOut = byId("handle-out");
const languageSelect = byId("language");

let locale = safeLocale();
let file = null;
let duration = 1;
let inTime = 0;
let outTime = 1;
let objectUrl = null;
let dragging = null;

function safeLocale() {
  try { return localStorage.getItem(LANGUAGE_KEY) === "pt-BR" ? "pt-BR" : "en"; } catch { return "en"; }
}
function t(key, values = {}) {
  return messages[locale][key].replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
}
function applyLocale() {
  document.documentElement.lang = locale;
  document.title = t("title");
  languageSelect.value = locale;
  document.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
  document.querySelectorAll("[data-i18n-aria]").forEach((element) => { element.setAttribute("aria-label", t(element.dataset.i18nAria)); });
  if (!file) dropLabel.textContent = t("dropLabel");
  render();
}
function fmt(seconds) {
  return `${Math.max(0, seconds).toLocaleString(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}s`;
}
function clampRange() {
  duration = Number.isFinite(preview.duration) && preview.duration > 0 ? preview.duration : duration;
  if (outTime > duration) outTime = duration;
  if (inTime < 0) inTime = 0;
  if (outTime - inTime < MIN_SPAN) {
    if (dragging === "in") inTime = Math.max(0, outTime - MIN_SPAN);
    else outTime = Math.min(duration, inTime + MIN_SPAN);
  }
}
function render() {
  clampRange();
  const span = outTime - inTime;
  times.textContent = `${fmt(inTime)} → ${fmt(outTime)}`;
  meta.textContent = span > SQUEEZE_AFTER ? `${fmt(span)} · ${t("speedingUp")}` : "";
  const left = duration > 0 ? (inTime / duration) * 100 : 0;
  const width = duration > 0 ? (span / duration) * 100 : 0;
  rangeEl.style.left = `${left}%`;
  rangeEl.style.width = `${width}%`;
  handleIn.style.left = `${left}%`;
  handleOut.style.left = `${left + width}%`;
}
function loopPreview() {
  if (!preview.paused && (preview.currentTime < inTime - 0.04 || preview.currentTime >= outTime)) preview.currentTime = inTime;
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
preview.addEventListener("ended", () => { preview.currentTime = inTime; preview.play().catch(() => {}); });
drop.addEventListener("click", () => fileInput.click());
drop.addEventListener("dragover", (event) => { event.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (event) => {
  event.preventDefault();
  drop.classList.remove("over");
  if (event.dataTransfer.files[0]) loadFile(event.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files[0]) loadFile(fileInput.files[0]); });
languageSelect.addEventListener("change", () => {
  locale = languageSelect.value === "pt-BR" ? "pt-BR" : "en";
  try { localStorage.setItem(LANGUAGE_KEY, locale); } catch { /* Browsing still works without storage. */ }
  applyLocale();
});
function timeFromClientX(clientX) {
  const box = timeline.querySelector(".track").getBoundingClientRect();
  return Math.min(1, Math.max(0, (clientX - box.left) / box.width)) * duration;
}
function startDrag(which, event) { event.preventDefault(); dragging = which; event.currentTarget.setPointerCapture?.(event.pointerId); }
handleIn.addEventListener("pointerdown", (event) => startDrag("in", event));
handleOut.addEventListener("pointerdown", (event) => startDrag("out", event));
window.addEventListener("pointermove", (event) => {
  if (!dragging) return;
  const time = timeFromClientX(event.clientX);
  if (dragging === "in") inTime = Math.min(time, outTime - MIN_SPAN);
  else outTime = Math.max(time, inTime + MIN_SPAN);
  render();
  preview.currentTime = dragging === "in" ? inTime : Math.max(inTime, outTime - 0.05);
});
window.addEventListener("pointerup", () => { dragging = null; });
timeline.addEventListener("pointerdown", (event) => {
  if (event.target.classList.contains("handle")) return;
  const time = timeFromClientX(event.clientX);
  dragging = time < (inTime + outTime) / 2 ? "in" : "out";
  if (dragging === "in") inTime = Math.min(time, outTime - MIN_SPAN);
  else outTime = Math.max(time, inTime + MIN_SPAN);
  render();
});
function responseMessage(payload) {
  return payload?.error && messages[locale][payload.error] ? t(payload.error) : t("failed");
}
generate.addEventListener("click", async () => {
  if (!file) {
    statusEl.textContent = t("chooseVideo");
    statusEl.className = "status error";
    return;
  }
  generate.disabled = true;
  statusEl.className = "status";
  statusEl.textContent = t("generating");
  const body = new FormData();
  body.append("video", file, file.name);
  body.append("start", String(inTime));
  body.append("end", String(outTime));
  try {
    const response = await fetch("/generate", { method: "POST", body });
    if (!response.ok) {
      let payload;
      try { payload = await response.json(); } catch { /* Use the safe local fallback. */ }
      throw new Error(responseMessage(payload));
    }
    const blob = await response.blob();
    const saved = response.headers.get("X-Saved-To");
    const name = `${file.name.replace(/\.[^.]+$/, "") || "live"}.pvt.zip`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    URL.revokeObjectURL(url);
    statusEl.className = "status ok";
    statusEl.textContent = saved ? t("saved", { path: saved }) : t("ready");
  } catch (error) {
    statusEl.className = "status error";
    statusEl.textContent = error.message || t("failed");
  } finally {
    generate.disabled = false;
  }
});
applyLocale();
