/**
 * Video Downloader - Frontend
 * Connects to Python API server at localhost:8000
 */

const API_BASE = window.location.origin;

// DOM Elements
const urlInput = document.getElementById("urlInput");
const platformBadge = document.getElementById("platformBadge");
const qualitySelect = document.getElementById("qualitySelect");
const qualityGroup = document.getElementById("qualityGroup");
const downloadBtn = document.getElementById("downloadBtn");
const resultArea = document.getElementById("resultArea");
const resultContent = document.getElementById("resultContent");
const historyList = document.getElementById("historyList");
const historyCount = document.getElementById("historyCount");
const clearHistoryBtn = document.getElementById("clearHistoryBtn");
const serverStatus = document.getElementById("serverStatus");
const formatBtns = document.querySelectorAll(".format-btn");

// Progress Elements
const progressArea = document.getElementById("progressArea");
const progressStatus = document.getElementById("progressStatus");
const progressPercent = document.getElementById("progressPercent");
const progressBarFill = document.getElementById("progressBarFill");
const progressSpeed = document.getElementById("progressSpeed");
const progressEta = document.getElementById("progressEta");

let selectedFormat = "mp4";
let pollTimer = null;
let history = JSON.parse(localStorage.getItem("dl_history") || "[]");

// ===== Server Status Check =====
async function checkServer() {
    try {
        const res = await fetch(`${API_BASE}/api/status`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
            serverStatus.textContent = "Online";
            serverStatus.className = "status-dot online";
            return true;
        }
    } catch {}
    serverStatus.textContent = "Offline";
    serverStatus.className = "status-dot offline";
    return false;
}

// ===== Format Toggle (MP4 / MP3) =====
formatBtns.forEach(btn => {
    btn.addEventListener("click", () => {
        formatBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        selectedFormat = btn.dataset.format;

        // Hide quality selector for MP3
        if (selectedFormat === "mp3") {
            qualityGroup.classList.add("hidden");
        } else {
            qualityGroup.classList.remove("hidden");
        }
    });
});

// ===== Platform Detection =====
let detectTimer = null;
function onUrlChange() {
    const url = urlInput.value.trim();
    clearTimeout(detectTimer);

    if (!url) {
        platformBadge.classList.add("hidden");
        downloadBtn.disabled = true;
        return;
    }

    const platform = detectPlatformLocal(url);
    showPlatformBadge(platform);
    downloadBtn.disabled = false;

    detectTimer = setTimeout(async () => {
        try {
            const res = await fetch(`${API_BASE}/api/detect`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url }),
            });
            const data = await res.json();
            showPlatformBadge(data.platform);
        } catch {}
    }, 500);
}

function detectPlatformLocal(url) {
    if (/youtube\.com|youtu\.be/i.test(url)) return "youtube";
    if (/tiktok\.com/i.test(url)) return "tiktok";
    if (/facebook\.com|fb\.watch/i.test(url)) return "facebook";
    return "unknown";
}

function showPlatformBadge(platform) {
    platformBadge.className = `platform-badge ${platform}`;
    const names = { youtube: "YouTube", tiktok: "TikTok", facebook: "Facebook", unknown: "Không rõ" };
    platformBadge.textContent = names[platform] || platform;
    platformBadge.classList.remove("hidden");
}

// ===== Download =====
async function startDownload() {
    const url = urlInput.value.trim();
    if (!url) return;

    // UI loading state
    downloadBtn.disabled = true;
    downloadBtn.classList.add("loading");
    downloadBtn.querySelector(".btn-text").classList.add("hidden");
    downloadBtn.querySelector(".btn-loading").classList.remove("hidden");
    resultArea.classList.add("hidden");

    showProgress(0, "Đang khởi tạo...", "", "");

    try {
        const payload = {
            url,
            format: selectedFormat,
            quality: selectedFormat === "mp3" ? "audio" : qualitySelect.value,
        };

        // Start async download
        const res = await fetch(`${API_BASE}/api/download/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        const startData = await res.json();
        if (!startData.task_id) {
            throw new Error(startData.error || "Failed to start download");
        }

        // Poll progress until done
        const result = await pollProgress(startData.task_id);
        hideProgress();

        if (result.success && result.file_id) {
            showProgress(100, "Đang lưu file...", "", "");
            await saveFileWithPicker(result.file_id, result.file_name || "video.mp4");
            hideProgress();
            showResult(result);
            addToHistory(result);
        } else {
            showResult(result);
        }
    } catch (err) {
        hideProgress();
        showResult({ success: false, error: `Không kết nối được server: ${err.message}` });
    } finally {
        downloadBtn.disabled = false;
        downloadBtn.classList.remove("loading");
        downloadBtn.querySelector(".btn-text").classList.remove("hidden");
        downloadBtn.querySelector(".btn-loading").classList.add("hidden");
    }
}

async function saveFileWithPicker(fileId, fileName) {
    const fileUrl = `${API_BASE}/api/file?id=${fileId}`;
    const ext = fileName.split(".").pop().toLowerCase();

    // Dùng showSaveFilePicker để người dùng chọn nơi lưu
    if (window.showSaveFilePicker) {
        try {
            const mimeTypes = {
                mp4: "video/mp4",
                mp3: "audio/mpeg",
                mkv: "video/x-matroska",
                webm: "video/webm",
                m4a: "audio/mp4",
            };

            const handle = await window.showSaveFilePicker({
                suggestedName: fileName,
                types: [{
                    description: ext.toUpperCase() + " file",
                    accept: { [mimeTypes[ext] || "application/octet-stream"]: ["." + ext] },
                }],
            });

            const res = await fetch(fileUrl);
            const blob = await res.blob();
            const writable = await handle.createWritable();
            await writable.write(blob);
            await writable.close();
            return;
        } catch (err) {
            // Người dùng huỷ dialog -> không làm gì
            if (err.name === "AbortError") return;
        }
    }

    // Fallback cho trình duyệt không hỗ trợ showSaveFilePicker
    const a = document.createElement("a");
    a.href = fileUrl;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// ===== Progress Polling =====
function pollProgress(taskId) {
    return new Promise((resolve, reject) => {
        const poll = async () => {
            try {
                const res = await fetch(`${API_BASE}/api/progress?task_id=${taskId}`);
                const data = await res.json();

                if (data.status === "done") {
                    showProgress(100, "Hoàn thành!", "", "");
                    progressBarFill.classList.add("done");
                    setTimeout(() => resolve(data.result), 400);
                    return;
                }

                if (data.status === "downloading") {
                    showProgress(
                        data.percent || 0,
                        "Đang tải...",
                        data.speed_str || "",
                        data.eta_str ? `Còn lại: ${data.eta_str}` : ""
                    );
                } else if (data.status === "processing") {
                    showProgress(100, "Đang xử lý video...", "", "");
                } else if (data.status === "starting") {
                    showProgress(0, "Đang phân tích link...", "", "");
                }

                pollTimer = setTimeout(poll, 500);
            } catch (err) {
                pollTimer = setTimeout(poll, 1000);
            }
        };
        poll();
    });
}

function showProgress(percent, status, speed, eta) {
    progressArea.classList.remove("hidden");
    progressBarFill.classList.remove("done");
    progressBarFill.style.width = `${percent}%`;
    progressPercent.textContent = `${Math.round(percent)}%`;
    progressStatus.textContent = status;
    progressSpeed.textContent = speed;
    progressEta.textContent = eta;
}

function hideProgress() {
    clearTimeout(pollTimer);
    setTimeout(() => {
        progressArea.classList.add("hidden");
        progressBarFill.style.width = "0%";
        progressBarFill.classList.remove("done");
    }, 500);
}

// ===== Result Display =====
function showResult(data) {
    resultArea.classList.remove("hidden", "result-success", "result-error");

    if (data.success) {
        resultArea.classList.add("result-success");
        resultContent.innerHTML = `
            <div class="result-title">Tải thành công!</div>
            <div class="result-detail">
                <div>${escapeHtml(data.title || "")}</div>
                <div>${data.platform || ""} &bull; ${data.file_name || ""}</div>
            </div>
        `;
    } else {
        resultArea.classList.add("result-error");
        resultContent.innerHTML = `
            <div class="result-title">Lỗi!</div>
            <div class="result-detail">${escapeHtml(data.error || "Unknown error")}</div>
        `;
    }
}

// ===== History =====
function addToHistory(data) {
    const item = {
        title: data.title,
        platform: data.platform,
        format: data.file_name ? data.file_name.split(".").pop().toUpperCase() : "MP4",
        time: new Date().toLocaleString("vi-VN"),
    };
    history.unshift(item);
    if (history.length > 50) history = history.slice(0, 50);
    localStorage.setItem("dl_history", JSON.stringify(history));
    renderHistory();
}

function renderHistory() {
    historyCount.textContent = history.length;

    if (history.length === 0) {
        historyList.innerHTML = '<p class="empty-history">Chưa có video nào được tải.</p>';
        clearHistoryBtn.classList.add("hidden");
        return;
    }

    clearHistoryBtn.classList.remove("hidden");
    historyList.innerHTML = history.map(item => `
        <div class="history-item">
            <span class="history-platform ${item.platform}">${item.platform}</span>
            <div class="history-info">
                <div class="history-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                <div class="history-time">${escapeHtml(item.format || "")} &bull; ${escapeHtml(item.time)}</div>
            </div>
        </div>
    `).join("");
}

function clearHistory() {
    if (!confirm("Xoá toàn bộ lịch sử tải?")) return;
    history = [];
    localStorage.setItem("dl_history", JSON.stringify(history));
    renderHistory();
}

// ===== Utilities =====
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ===== Event Listeners =====
urlInput.addEventListener("input", onUrlChange);
urlInput.addEventListener("paste", () => setTimeout(onUrlChange, 50));
downloadBtn.addEventListener("click", startDownload);
clearHistoryBtn.addEventListener("click", clearHistory);

urlInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !downloadBtn.disabled) startDownload();
});

// ===== Init =====
checkServer();
setInterval(checkServer, 15000);
renderHistory();
