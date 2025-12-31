const form = document.getElementById("upload-form");
const fileInput = document.getElementById("file-input");
const fileMeta = document.getElementById("file-meta");
const dropzone = document.getElementById("dropzone");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const confidenceInput = document.getElementById("confidence");
const confidenceValue = document.getElementById("confidence-value");
const submitBtn = document.getElementById("submit-btn");
const scrollToLab = document.getElementById("scroll-to-lab");

confidenceInput.addEventListener("input", (event) => {
  confidenceValue.textContent = Number(event.target.value).toFixed(2);
});

scrollToLab.addEventListener("click", () => {
  document.getElementById("lab").scrollIntoView({ behavior: "smooth" });
});

const setStatus = (message, type) => {
  statusEl.textContent = message;
  statusEl.className = "status";
  if (type) {
    statusEl.classList.add(type);
  }
};

const updateFileMeta = () => {
  const file = fileInput.files[0];
  if (!file) {
    fileMeta.textContent = "No file selected";
    return;
  }
  const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
  fileMeta.textContent = `${file.name} - ${sizeMb} MB`;
};

fileInput.addEventListener("change", updateFileMeta);

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});

dropzone.addEventListener("dragleave", () => {
  dropzone.classList.remove("dragover");
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  if (event.dataTransfer.files.length > 0) {
    fileInput.files = event.dataTransfer.files;
    updateFileMeta();
  }
});

const renderResult = (payload) => {
  const report = payload.report || {};
  const documentInfo = payload.document || {};
  const outputFiles = payload.output_files || {};
  const riskSignals = report.risk_signals || {};
  const confidence = report.confidence || {};

  resultEl.classList.remove("empty");
  const summary = report.summary || {};
  const confidenceLabel = confidence.label ? ` (${confidence.label})` : "";

  resultEl.innerHTML = `
    <div class="result-grid">
      <div class="pill">
        <span>Status</span>
        <strong>${report.validation_status || "N/A"}</strong>
      </div>
      <div class="pill">
        <span>Confidence Score</span>
        <strong>${(summary.overall_confidence || 0).toFixed(2)}${confidenceLabel}</strong>
      </div>
      <div class="pill">
        <span>Rows</span>
        <strong>${documentInfo.total_rows ?? 0}</strong>
      </div>
      <div class="pill">
        <span>Risk Signals</span>
        <strong>${riskSignals.total_signals ?? 0}</strong>
      </div>
    </div>
    <div class="result-grid">
      <div class="pill">
        <span>Failed Checks</span>
        <strong>${summary.failed_checks ?? 0}</strong>
      </div>
      <div class="pill">
        <span>Warnings</span>
        <strong>${summary.warnings ?? 0}</strong>
      </div>
      <div class="pill">
        <span>Rule Pass Rate</span>
        <strong>${(summary.rule_pass_rate || 0).toFixed(2)}</strong>
      </div>
    </div>
    <div class="pill">
      <span>Document ID</span>
      <strong>${documentInfo.document_id || "N/A"}</strong>
    </div>
    <div class="output-links">
      ${outputFiles.csv ? `<a href="/api/outputs/${encodeURIComponent(outputFiles.csv)}" target="_blank">Download CSV</a>` : ""}
      ${outputFiles.risk_report ? `<a href="/api/outputs/${encodeURIComponent(outputFiles.risk_report)}" target="_blank">Download Risk Report</a>` : ""}
      ${outputFiles.review_rows ? `<a href="/api/outputs/${encodeURIComponent(outputFiles.review_rows)}" target="_blank">Download Review Rows</a>` : ""}
      ${outputFiles.business_summary ? `<a href="/api/outputs/${encodeURIComponent(outputFiles.business_summary)}" target="_blank">Download Business Summary</a>` : ""}
    </div>
  `;
};

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];

  if (!file) {
    setStatus("Select a file to run the pipeline.", "busy");
    return;
  }

  const formData = new FormData(form);
  formData.append("file", file);

  submitBtn.disabled = true;
  setStatus("Processing document... this can take a minute.", "busy");

  try {
    const response = await fetch("/api/process", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Processing failed");
    }

    renderResult(payload);
    setStatus("Done. Review the outputs below.", "");
  } catch (error) {
    resultEl.classList.add("empty");
    resultEl.innerHTML = `<div class="result-empty">${error.message}</div>`;
    setStatus("Failed to process the document.", "");
  } finally {
    submitBtn.disabled = false;
  }
});
