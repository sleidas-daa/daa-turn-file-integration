const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const queueList = document.getElementById("queue-list");
const queueCount = document.getElementById("queue-count");
const parserSelect = document.getElementById("parser-select");
const previewBtn = document.getElementById("preview-btn");
const convertBtn = document.getElementById("convert-btn");
const clearAllBtn = document.getElementById("clear-all-btn");
const previewMeta = document.getElementById("preview-meta");
const previewError = document.getElementById("preview-error");
const previewTable = document.getElementById("preview-table");
const previewHead = document.getElementById("preview-head");
const previewBody = document.getElementById("preview-body");
const itemTemplate = document.getElementById("queue-item-template");

let selectedId = null;
let queueItems = [];

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function pendingCount() {
  return queueItems.filter((i) => i.status !== "completed").length;
}

function updateButtons() {
  const pending = pendingCount();
  queueCount.textContent = String(queueItems.length);
  convertBtn.textContent = `Convert ${pending} file${pending === 1 ? "" : "s"}`;
  convertBtn.disabled = pending === 0;
  clearAllBtn.disabled = queueItems.length === 0;
  previewBtn.disabled = !selectedId;
}

async function refreshQueue() {
  const res = await fetch("/api/queue");
  const data = await res.json();
  queueItems = data.items || [];
  renderQueue();
  updateButtons();
}

function renderQueue() {
  queueList.innerHTML = "";
  if (queueItems.length === 0) {
    queueList.classList.add("empty");
    const empty = document.createElement("li");
    empty.className = "queue-empty";
    empty.textContent = "No files queued yet.";
    queueList.appendChild(empty);
    selectedId = null;
    return;
  }

  queueList.classList.remove("empty");

  for (const item of queueItems) {
    const node = itemTemplate.content.cloneNode(true);
    const li = node.querySelector(".queue-item");
    li.dataset.id = item.id;
    if (item.id === selectedId) li.classList.add("selected");

    const name = node.querySelector(".queue-name");
    name.textContent = item.file_name;

    const meta = node.querySelector(".queue-meta");
    const parts = [formatSize(item.file_size)];
    if (item.status === "completed") {
      parts.push(`Done · ${item.record_count} rows`);
      if (item.detected_template) parts.push(item.detected_template);
    } else if (item.status === "failed") {
      parts.push("Failed");
    }
    meta.textContent = parts.join(" · ");

    node.querySelector(".queue-select").addEventListener("click", () => {
      selectedId = item.id;
      renderQueue();
      updateButtons();
    });

    node.querySelector(".delete-btn").addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/queue/${item.id}`, { method: "DELETE" });
      if (selectedId === item.id) selectedId = null;
      await refreshQueue();
    });

    queueList.appendChild(node);
  }

  if (selectedId && !queueItems.find((i) => i.id === selectedId)) {
    selectedId = queueItems[0]?.id ?? null;
  }
}

async function uploadFiles(fileList) {
  if (!fileList.length) return;
  const form = new FormData();
  for (const file of fileList) form.append("files", file);

  const res = await fetch("/api/queue/upload", { method: "POST", body: form });
  const data = await res.json();

  if (data.errors?.length) {
    alert(data.errors.map((e) => `${e.file}: ${e.error}`).join("\n"));
  }
  if (data.added?.length && !selectedId) {
    selectedId = data.added[0].id;
  }
  await refreshQueue();
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    fileInput.click();
  }
});

fileInput.addEventListener("change", () => {
  uploadFiles([...fileInput.files]);
  fileInput.value = "";
});

dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));

dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  uploadFiles([...e.dataTransfer.files]);
});

clearAllBtn.addEventListener("click", async () => {
  if (!confirm("Remove all files from the queue?")) return;
  await fetch("/api/queue", { method: "DELETE" });
  selectedId = null;
  clearPreview();
  await refreshQueue();
});

previewBtn.addEventListener("click", async () => {
  if (!selectedId) return;
  previewBtn.disabled = true;
  previewBtn.textContent = "Loading…";
  try {
    const template = parserSelect.value;
    const res = await fetch(`/api/preview/${selectedId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template }),
    });
    const data = await res.json();
    showPreview(data);
  } finally {
    previewBtn.textContent = "Preview selected";
    updateButtons();
  }
});

convertBtn.addEventListener("click", async () => {
  const pending = pendingCount();
  if (!pending) return;
  convertBtn.disabled = true;
  convertBtn.textContent = "Converting…";
  try {
    const res = await fetch("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template: parserSelect.value }),
    });
    if (!res.ok) {
      const err = await res.json();
      alert(err.detail || "Conversion failed");
      return;
    }
    const data = await res.json();
    await refreshQueue();
    const failed = data.results.filter((r) => r.status === "failed");
    if (failed.length) {
      alert(
        failed.map((r) => `${r.file_name}: ${r.error || "Unknown error"}`).join("\n")
      );
    }
    for (const r of data.results.filter((x) => x.status === "completed")) {
      window.open(`/api/download/${r.id}`, "_blank");
    }
  } finally {
    updateButtons();
  }
});

function clearPreview() {
  previewMeta.textContent = "Select a file and click Preview.";
  previewError.classList.add("hidden");
  previewTable.classList.add("hidden");
  previewHead.innerHTML = "";
  previewBody.innerHTML = "";
}

function showPreview(data) {
  previewError.classList.add("hidden");
  previewTable.classList.add("hidden");

  if (!data.ok) {
    previewMeta.textContent = `${data.file_name} — preview failed`;
    previewError.textContent = data.error || "Could not parse file";
    previewError.classList.remove("hidden");
    return;
  }

  const conf = Math.round((data.confidence || 0) * 100);
  let meta = `${data.file_name} · ${data.template} · ${data.record_count} turn rows`;
  if (data.template && conf) meta += ` · ${conf}% confidence`;
  if (data.truncated) meta += ` (showing first ${data.rows.length})`;
  previewMeta.textContent = meta;

  previewHead.innerHTML =
    "<tr>" + data.columns.map((c) => `<th>${c}</th>`).join("") + "</tr>";
  previewBody.innerHTML = data.rows
    .map((row) => "<tr>" + row.map((c) => `<td>${c}</td>`).join("") + "</tr>")
    .join("");
  previewTable.classList.remove("hidden");

  if (data.parse_errors?.length) {
    previewError.textContent = data.parse_errors
      .map((e) => e.reason || e.message || JSON.stringify(e))
      .join("; ");
    previewError.classList.remove("hidden");
  }
}

refreshQueue();
