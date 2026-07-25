// Constants & State
let ws = null;
let reconnectInterval = 1000;
let maxReconnectInterval = 30000;
let trendChart = null;
let currentHistorySource = "live_camera";
let cameraHost = null;
const CAMERA_HOST_STORAGE_KEY = 'cameraHost';

let previousPassed = 0;
let previousFailed = 0;
let previousTotal = 0;

// Cumulative counts for Trend Charting
let chartLabels = [];
let chartPassData = [];
let chartFailData = [];
const maxChartPoints = 15;

document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

function initApp() {
    // Defensive chart initialization: guard against missing Chart.js and
    // ensure layout has settled before creating the chart so it has
    // non-zero pixel dimensions.
    if (typeof Chart === "undefined") {
        console.error("Chart.js failed to load from CDN — check network/internet access");
    } else {
        // Double rAF to allow layout / font metrics to settle (prevents
        // canvas being zero-size when Chart.js initializes).
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                try {
                    setupTrendChart();
                } catch (e) {
                    console.error("Chart init failed:", e);
                }
            });
        });
    }

    // Continue startup regardless of chart outcome
    registerEventHandlers();
    loadCameraHost();
    updateCameraHostUI();
    updateTabIndicator();
    window.addEventListener('resize', updateTabIndicator);
    fetchSystemStatus();
    fetchAnalyticsSummary();
    fetchHistory();
    connectWebSocket();
}

function normalizeCameraHost(value) {
    if (!value) return null;
    const host = value.trim().replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '').replace(/\/.*/, '').replace(/\/$/, '');
    return host || null;
}

function loadCameraHost() {
    const stored = localStorage.getItem(CAMERA_HOST_STORAGE_KEY);
    cameraHost = normalizeCameraHost(stored);
    return cameraHost;
}

function saveCameraHost(value) {
    cameraHost = normalizeCameraHost(value);
    if (cameraHost) {
        localStorage.setItem(CAMERA_HOST_STORAGE_KEY, cameraHost);
    } else {
        localStorage.removeItem(CAMERA_HOST_STORAGE_KEY);
    }
    updateCameraHostUI();
}

function updateCameraHostUI(overrideStatus) {
    const input = document.getElementById('camera-host-input');
    const statusText = document.getElementById('camera-connect-status');
    const disconnectBtn = document.getElementById('disconnect-camera-btn');
    if (input) input.value = cameraHost || '';
    if (disconnectBtn) disconnectBtn.disabled = !cameraHost;
    if (statusText) {
        if (overrideStatus) {
            statusText.textContent = overrideStatus;
        } else if (cameraHost) {
            statusText.textContent = `Using remote host ${cameraHost}`;
        } else {
            statusText.textContent = 'Using local host';
        }
    }
}

function buildApiUrl(path) {
    if (!path.startsWith('/')) path = '/' + path;
    return cameraHost ? `http://${cameraHost}${path}` : path;
}

function buildWsUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    if (!cameraHost) {
        return `${protocol}//${window.location.host}/ws/dashboard`;
    }
    return `${protocol}//${cameraHost}/ws/dashboard`;
}

function reconnectWebSocket() {
    if (ws) {
        ws.close();
    }
    connectWebSocket();
}

function handleCameraConnect() {
    const input = document.getElementById('camera-host-input');
    if (!input) return;
    const host = normalizeCameraHost(input.value);
    if (!host) {
        updateCameraHostUI('Enter a valid host');
        return;
    }

    saveCameraHost(host);
    updateCameraHostUI(`Connecting to ${cameraHost}...`);
    reconnectWebSocket();
    fetchSystemStatus();
    fetchAnalyticsSummary();
    fetchHistory();
}

function handleCameraDisconnect() {
    saveCameraHost(null);
    updateCameraHostUI('Using local host');
    reconnectWebSocket();
    fetchSystemStatus();
    fetchAnalyticsSummary();
    fetchHistory();
}

function triggerStampAnimation(element) {
    if (!element) return;
    element.classList.remove('stamp-animate');
    void element.offsetWidth;
    element.classList.add('stamp-animate');
}

function updateMetricStampOnChange(id, previousValue, nextValue) {
    if (previousValue === nextValue) return;
    const badge = document.getElementById(id);
    if (badge) {
        triggerStampAnimation(badge);
    }
}

// 1. Connection Status Badges Update
function updateStatusBadge(badgeId, isOnline, textPrefix) {
    const badge = document.getElementById(badgeId);
    if (!badge) return;
    
    const label = badge.querySelector(".badge-label");
    if (!label) return;
    
    // Toggle online/offline classes per approved design guide
    if (isOnline) {
        badge.classList.remove("offline");
        badge.classList.add("online");
        label.textContent = `${textPrefix}: CONNECTED`;
        if (badgeId === "status-inspection") {
            label.textContent = `${textPrefix}: RUNNING`;
            // Update scope status indicator in video bezel
            const scopeStatus = document.getElementById("scope-status");
            const scanningMarker = document.querySelector('.scan-indicator');
            if (scopeStatus) {
                scopeStatus.textContent = "STATUS: ACTIVE";
                scopeStatus.style.color = "var(--color-pass-stamp-text)";
            }
            if (scanningMarker) {
                scanningMarker.classList.add('pulse-active');
            }
        }
    } else {
        badge.classList.remove("online");
        badge.classList.add("offline");
        label.textContent = `${textPrefix}: OFFLINE`;
        if (badgeId === "status-inspection") {
            label.textContent = `${textPrefix}: IDLE`;
            // Update scope status indicator in video bezel
            const scopeStatus = document.getElementById("scope-status");
            const scanningMarker = document.querySelector('.scan-indicator');
            if (scopeStatus) {
                scopeStatus.textContent = "STATUS: STANDBY";
                scopeStatus.style.color = "var(--color-text-secondary)";
            }
            if (scanningMarker) {
                scanningMarker.classList.remove('pulse-active');
            }
        }
    }
}

// 2. HTTP Requests & Controls
async function fetchSystemStatus() {
    try {
        const response = await fetch(buildApiUrl('/inspection/status'));
        const data = await response.json();
        
        // Update badges
        updateStatusBadge("status-inspection", data.running, "Inspection");
        updateStatusBadge("status-mongodb", data.mongodb_connected, "Database");
        updateStatusBadge("status-mqtt", data.mqtt_connected, "MQTT Broker");
        
        // Update button states
        const btnStart = document.getElementById("btn-start");
        const btnStop = document.getElementById("btn-stop");
        btnStart.disabled = data.running;
        btnStop.disabled = !data.running;
        // Hide settings for VIEWER role machines
        const openSettingsBtn = document.getElementById('open-settings-btn');
        if (openSettingsBtn) {
            if (data.role && data.role.toUpperCase() === 'VIEWER') {
                openSettingsBtn.style.display = 'none';
            } else {
                openSettingsBtn.style.display = '';
            }
        }
    } catch (e) {
        console.error("Error fetching system status:", e);
    }
}

async function fetchAnalyticsSummary() {
    try {
        const response = await fetch(buildApiUrl(`/analytics/summary?source=${currentHistorySource}`));
        const data = await response.json();
        updateMetricCards(data);
        updateDefectBreakdown(data.defect_counts, data.failed);
    } catch (e) {
        console.error("Error fetching analytics:", e);
    }
}

async function fetchHistory() {
    const statusFilter = document.getElementById("filter-status").value;
    const defectFilter = document.getElementById("filter-defect").value;
    
    let url = `/history?source=${currentHistorySource}`;
    if (statusFilter) url += `&status=${statusFilter}`;
    if (defectFilter) url += `&defect_type=${defectFilter}`;
    
    try {
        const response = await fetch(buildApiUrl(url));
        const historyData = await response.json();
        renderHistoryTable(historyData);
    } catch (e) {
        console.error("Error fetching history:", e);
    }
}

async function startInspection() {
    try {
        const response = await fetch(buildApiUrl('/inspection/start'), { method: 'POST' });
        const data = await response.json();
        if (data.status === "started" || data.status === "already_running") {
            document.getElementById("btn-start").disabled = true;
            document.getElementById("btn-stop").disabled = false;
            updateStatusBadge("status-inspection", true, "Inspection");
        }
    } catch (e) {
        console.error("Error starting inspection:", e);
    }
}

async function stopInspection() {
    try {
        const response = await fetch(buildApiUrl('/inspection/stop'), { method: 'POST' });
        const data = await response.json();
        if (data.status === "stopped" || data.status === "already_stopped") {
            document.getElementById("btn-start").disabled = false;
            document.getElementById("btn-stop").disabled = true;
            updateStatusBadge("status-inspection", false, "Inspection");
        }
    } catch (e) {
        console.error("Error stopping inspection:", e);
    }
}

// 3. UI Content Renders
function updateMetricCards(data) {
    document.getElementById("metric-total").textContent = data.total || 0;
    document.getElementById("metric-passed").textContent = data.passed || 0;
    document.getElementById("metric-failed").textContent = data.failed || 0;
    
    // Update SVG Circular Gauge
    const rateVal = data.defect_rate || 0.0;
    document.getElementById("metric-rate").textContent = `${rateVal}%`;
    
    const gaugeFill = document.getElementById("gauge-fill");
    if (gaugeFill) {
        const pathLength = 165;
        const offset = pathLength - (parseFloat(rateVal) / 100) * pathLength;
        gaugeFill.style.setProperty('--gauge-target-offset', offset);
        gaugeFill.style.strokeDashoffset = offset;
        gaugeFill.classList.remove('animate-sweep');
        void gaugeFill.offsetWidth;
        gaugeFill.classList.add('animate-sweep');
    }

    updateMetricStampOnChange('badge-pass-counter', previousPassed, data.passed || 0);
    updateMetricStampOnChange('badge-fail-counter', previousFailed, data.failed || 0);

    previousPassed = data.passed || 0;
    previousFailed = data.failed || 0;
    previousTotal = data.total || 0;
}

function updateDefectBreakdown(defectCounts, totalFailed) {
    const categories = ["Scratch", "Dent", "Crack", "Pinhole"];
    categories.forEach(cat => {
        const count = defectCounts[cat] || 0;
        const percent = totalFailed > 0 ? Math.round((count / totalFailed) * 100) : 0;
        
        // Update label text in page-analysis
        document.getElementById(`breakdown-${cat.toLowerCase()}-val`).textContent = `${count} (${percent}%)`;
        
        // Animate progress bar width from previous value to new value
        const bar = document.getElementById(`breakdown-${cat.toLowerCase()}-bar`);
        if (bar) {
            const previousWidth = parseFloat(bar.style.width) || 0;
            if (previousWidth !== percent) {
                bar.style.width = `${percent}%`;
            }
        }
        
        // Update compact list in page-live
        const liveCountElement = document.getElementById(`live-breakdown-${cat.toLowerCase()}`);
        if (liveCountElement) {
            liveCountElement.textContent = count;
        }
    });
}

function renderHistoryTable(records) {
    const tbody = document.getElementById("history-table-body");
    tbody.innerHTML = "";
    
    if (!records || records.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="placeholder-row font-tech">NO MATCHING RECORDS IN STORAGE ENGINE.</td></tr>`;
        return;
    }
    
    records.forEach(rec => {
        const row = document.createElement("tr");
        
        // Format timestamp
        const time = new Date(rec.timestamp).toLocaleTimeString();
        
        // Format source
        const srcText = rec.source === "live_camera" ? "LIVE CAMERA" : "MANUAL UPLOAD";
        
        // Format defects
        let defectText = "None";
        if (rec.defects && rec.defects.length > 0) {
            defectText = rec.defects.map(d => `${d.type} (${Math.round(d.confidence * 100)}%)`).join(", ");
        }
        
        // Tilted ink stamp style
        const stampClass = rec.status === "PASS" ? "stamp stamp-pass" : "stamp stamp-fail";
            
        row.innerHTML = `
            <td class="font-tech tabular-nums">${time}</td>
            <td class="font-tech" style="font-size: 0.75rem; font-weight: bold;">${srcText}</td>
            <td style="color: ${rec.status === 'FAIL' ? 'var(--color-fail-rust-accent)' : 'inherit'}">${defectText}</td>
            <td><span class="${stampClass}">${rec.status}</span></td>
        `;
        
        tbody.appendChild(row);
    });
}

function appendToHistoryTable(rec) {
    const tbody = document.getElementById("history-table-body");
    
    // Remove placeholder row if present
    const placeholder = tbody.querySelector(".placeholder-row");
    if (placeholder) {
        tbody.innerHTML = "";
    }
    
    const row = document.createElement("tr");
    const time = new Date(rec.timestamp).toLocaleTimeString();
    const srcText = rec.source === "live_camera" ? "LIVE CAMERA" : "MANUAL UPLOAD";
    
    let defectText = "None";
    if (rec.defects && rec.defects.length > 0) {
        defectText = rec.defects.map(d => `${d.type} (${Math.round(d.confidence * 100)}%)`).join(", ");
    }
    
    const stampClass = rec.status === "PASS" ? "stamp stamp-pass" : "stamp stamp-fail";
        
    row.innerHTML = `
        <td class="font-tech tabular-nums">${time}</td>
        <td class="font-tech" style="font-size: 0.75rem; font-weight: bold;">${srcText}</td>
        <td style="color: ${rec.status === 'FAIL' ? 'var(--color-fail-rust-accent)' : 'inherit'}">${defectText}</td>
        <td><span class="${stampClass}">${rec.status}</span></td>
    `;
    
    // Insert at top
    tbody.insertBefore(row, tbody.firstChild);

    row.classList.add('row-flash');
    row.addEventListener('animationend', () => {
        row.classList.remove('row-flash');
    }, { once: true });

    const newStamp = row.querySelector('.stamp');
    if (newStamp) {
        requestAnimationFrame(() => {
            newStamp.classList.add('stamp-animate');
            newStamp.addEventListener('animationend', () => {
                newStamp.classList.remove('stamp-animate');
            }, { once: true });
        });
    }
    
    // Cap table size at 50 rows
    if (tbody.children.length > 50) {
        tbody.removeChild(tbody.lastChild);
    }
}

// 4. WebSocket Client Connection
function connectWebSocket() {
    const wsUrl = buildWsUrl();
    
    logger("Connecting to WebSocket: " + wsUrl);
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        logger("WebSocket connection established.");
        reconnectInterval = 1000; // Reset backoff
    };
    
    ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        
        // Handle connection initialization setup
        if (payload.event === "connected") {
            updateStatusBadge("status-mongodb", payload.system_status.mongodb_connected, "Database");
            updateStatusBadge("status-mqtt", payload.system_status.mqtt_connected, "MQTT Broker");
            updateStatusBadge("status-inspection", payload.system_status.inspection_running, "Inspection");
            
            // Set initial counters (only if currently viewing live camera stats)
            if (currentHistorySource === "live_camera") {
                updateMetricCards(payload.counters);
                updateDefectBreakdown(payload.counters.defect_counts, payload.counters.failed);
            }
            return;
        }
        
        // Handle status updates
        if (payload.event === "status_update") {
            updateStatusBadge("status-mongodb", payload.system_status.mongodb_connected, "Database");
            updateStatusBadge("status-mqtt", payload.system_status.mqtt_connected, "MQTT Broker");
            updateStatusBadge("status-inspection", payload.system_status.inspection_running, "Inspection");
            return;
        }
        
        // Primary Inspection Loop broadcasts
        // 1. Update Video Frame Feed
        if (payload.image_base64) {
            document.getElementById("live-feed").src = `data:image/jpeg;base64,${payload.image_base64}`;
        }
        
        // 2. Update Metrics
        if (payload.counters && currentHistorySource === "live_camera") {
            updateMetricCards(payload.counters);
            updateDefectBreakdown(payload.counters.defect_counts, payload.counters.failed);
            
            // Add point to Trend Chart
            updateChartData(payload.counters.passed, payload.counters.failed);
        }
        
        // 3. Add to History list
        if (payload.product_id && currentHistorySource === "live_camera") {
            const historyRecord = {
                timestamp: payload.timestamp,
                product_id: payload.product_id,
                status: payload.status,
                defects: payload.defects,
                source: "live_camera"
            };
            appendToHistoryTable(historyRecord);
        }
    };
    
    ws.onclose = () => {
        logger("WebSocket disconnected. Attempting reconnect...");
        scheduleReconnect();
    };
    
    ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        ws.close();
    };
}

function scheduleReconnect() {
    setTimeout(() => {
        reconnectInterval = Math.min(reconnectInterval * 2, maxReconnectInterval);
        connectWebSocket();
    }, reconnectInterval);
}

// 5. Charting Implementation (Clean Gridlines & Restricted Palette)
function setupTrendChart() {
    const ctx = document.getElementById("trendChart").getContext("2d");
    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [
                {
                    label: 'Passed Items',
                    borderColor: '#5f9e73',
                    backgroundColor: 'transparent',
                    data: chartPassData,
                    borderWidth: 2,
                    tension: 0.15,
                    fill: false,
                    pointRadius: 2,
                    pointBackgroundColor: '#5f9e73'
                },
                {
                    label: 'Failed Items',
                    borderColor: '#d85a30',
                    backgroundColor: 'transparent',
                    data: chartFailData,
                    borderWidth: 2,
                    tension: 0.15,
                    fill: false,
                    pointRadius: 2,
                    pointBackgroundColor: '#d85a30'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#8a8d92', font: { family: 'Oswald, sans-serif', size: 12 } }
                }
            },
            scales: {
                x: {
                    grid: { color: '#3a3d42' },
                    ticks: { color: '#8a8d92', font: { family: 'Share Tech Mono, monospace', size: 11 } }
                },
                y: {
                    grid: { color: '#3a3d42' },
                    ticks: { color: '#8a8d92', font: { family: 'Share Tech Mono, monospace', size: 11 }, stepSize: 1 }
                }
            }
        }
    });
}

function updateChartData(passed, failed) {
    const nowLabel = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    chartLabels.push(nowLabel);
    chartPassData.push(passed);
    chartFailData.push(failed);
    
    // Enforce sliding window length
    if (chartLabels.length > maxChartPoints) {
        chartLabels.shift();
        chartPassData.shift();
        chartFailData.shift();
    }
    
    trendChart.update('none'); // Update without animation for raw performance
}

// 6. Upload & Modal Handlers
async function handleUploadClick() {
    document.getElementById("upload-input").click();
}

async function uploadImage(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const btnUpload = document.getElementById("btn-upload");
    const originalText = btnUpload.innerHTML;
    
    // Show loading state
    btnUpload.disabled = true;
    btnUpload.innerHTML = `<i class="fa-solid fa-spinner spin-loader"></i> INGESTING...`;
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await fetch(buildApiUrl('/inspection/upload'), {
            method: "POST",
            body: formData
        });
        
        if (!response.ok) {
            const err = await response.json();
            alert("Error: " + (err.message || "Failed to inspect image"));
            return;
        }
        
        const data = await response.json();
        
        // Show manual results modal
        showUploadResultModal(data);
        
        // If we are currently viewing the manual uploads history tab, refresh history & stats
        if (currentHistorySource === "manual_upload") {
            fetchHistory();
            fetchAnalyticsSummary();
        }
        
    } catch (e) {
        console.error("Upload error:", e);
        alert("Upload failed. Make sure backend is running.");
    } finally {
        event.target.value = "";
        btnUpload.disabled = false;
        btnUpload.innerHTML = originalText;
    }
}

function showUploadResultModal(data) {
    const modal = document.getElementById("upload-modal");
    const modalImage = document.getElementById("modal-image");
    const modalStatus = document.getElementById("modal-status-badge");
    const modalProductId = document.getElementById("modal-product-id");
    const modalDefects = document.getElementById("modal-defects-list");
    
    // Set image source
    modalImage.src = `data:image/jpeg;base64,${data.image_base64}`;
    
    // Set status badge
    modalStatus.textContent = data.status;
    modalStatus.className = data.status === "PASS" ? "stamp stamp-pass" : "stamp stamp-fail";
    triggerStampAnimation(modalStatus);
    
    // Set product ID
    modalProductId.textContent = data.product_id;
    
    // Set defects list
    modalDefects.innerHTML = "";
    if (!data.defects || data.defects.length === 0) {
        const li = document.createElement("li");
        li.textContent = "No Defects Identified (Good Surface)";
        li.style.color = "var(--color-pass-stamp-text)";
        li.style.fontFamily = "var(--font-tech)";
        modalDefects.appendChild(li);
    } else {
        data.defects.forEach(d => {
            const li = document.createElement("li");
            li.textContent = `${d.type} (Confidence: ${Math.round(d.confidence * 100)}%)`;
            li.style.fontFamily = "var(--font-tech)";
            modalDefects.appendChild(li);
        });
    }
    
    // Unhide modal
    modal.classList.remove("hidden");
}

// Close upload modal
function closeUploadModal() {
    document.getElementById("upload-modal").classList.add("hidden");
}

// Settings modal helpers
async function fetchSettings() {
    try {
        const resp = await fetch(buildApiUrl('/settings/camera'));
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        console.error('Failed to fetch settings:', e);
        return null;
    }
}

function openSettingsModal() {
    const modal = document.getElementById('settings-modal');
    if (!modal) return;
    modal.classList.remove('hidden');
    // populate current settings
    fetchSettings().then(cfg => {
        if (!cfg) return;
        document.getElementById('settings-mode').value = cfg.mode || (cfg.mode === 'mock' ? 'mock' : 'live');
        document.getElementById('settings-resolution').value = cfg.resolution || '640x480';
        // populate camera select with current index as placeholder until scan
        const sel = document.getElementById('settings-camera-select');
        sel.innerHTML = '';
        const opt = document.createElement('option');
        opt.value = cfg.camera_index || 0;
        opt.textContent = `Index ${cfg.camera_index || 0}`;
        sel.appendChild(opt);
    });
}

function closeSettingsModal() {
    document.getElementById('settings-modal').classList.add('hidden');
}

async function scanForCameras() {
    const btn = document.getElementById('settings-scan');
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    try {
        const resp = await fetch(buildApiUrl('/settings/camera/scan'));
        const data = await resp.json();
        const sel = document.getElementById('settings-camera-select');
        sel.innerHTML = '';
        if (data && data.results && data.results.length > 0) {
            // Group by index, prefer backends that opened
            const seen = {};
            data.results.forEach(r => {
                const idx = r.index;
                if (!seen[idx]) seen[idx] = [];
                seen[idx].push(r);
            });
            Object.keys(seen).forEach(idx => {
                const variants = seen[idx];
                // Prefer opened entries
                const opened = variants.find(v => v.opened) || variants[0];
                const label = opened.opened ? `Index ${idx} — ${opened.width || '?'}x${opened.height || '?'} @ ${Math.round(opened.fps||0)}fps (${opened.backend})` : `Index ${idx} — unavailable (${variants.map(v=>v.backend).join(',')})`;
                const opt = document.createElement('option');
                opt.value = idx;
                opt.textContent = label;
                sel.appendChild(opt);
            });
        } else {
            const opt = document.createElement('option');
            opt.value = 0;
            opt.textContent = 'No cameras found';
            sel.appendChild(opt);
        }
    } catch (e) {
        console.error('Camera scan failed:', e);
        alert('Camera scan failed. See console for details.');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Scan for Cameras';
    }
}

async function saveSettings() {
    const mode = document.getElementById('settings-mode').value;
    const camera_index = parseInt(document.getElementById('settings-camera-select').value || 0);
    const resolution = document.getElementById('settings-resolution').value;
    const status = document.getElementById('settings-status');
    status.textContent = 'Applying...';
    try {
        // Post settings and let backend handle stopping/starting if needed
        const resp = await fetch(buildApiUrl('/settings/camera'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode, camera_index, resolution })
        });
        const data = await resp.json();
        if (!resp.ok) {
            status.textContent = 'Error applying settings';
            alert('Failed to save settings: ' + (data.message || JSON.stringify(data)));
            return;
        }

        status.textContent = data.camera_opened ? `Active: ${data.mode}` : `Fell back to mock`;
        // Refresh system status and UI
        fetchSystemStatus();
        fetchAnalyticsSummary();
        fetchHistory();
        // Update live feed placeholder if switched to mock
        if (!data.camera_opened) {
            document.getElementById('live-feed').src = `data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480' viewBox='0 0 640 480'><rect width='100%' height='100%' fill='%231b1d21'/><text x='50%' y='50%' font-family='monospace' font-size='16' fill='%238a8d92' text-anchor='middle'>MOCK MODE ACTIVE</text></svg>`;
        }

        setTimeout(() => { closeSettingsModal(); status.textContent = ''; }, 900);
    } catch (e) {
        console.error('Save settings failed:', e);
        status.textContent = 'Error';
        alert('Save failed. See console.');
    }
}

// 7. Helpers & Event Listeners
function registerEventHandlers() {
    document.getElementById("btn-start").addEventListener("click", startInspection);
    document.getElementById("btn-stop").addEventListener("click", stopInspection);
    document.getElementById("btn-apply-filters").addEventListener("click", fetchHistory);
    
    // Camera host override controls
    const connectButton = document.getElementById("connect-camera-btn");
    const disconnectButton = document.getElementById("disconnect-camera-btn");
    if (connectButton) connectButton.addEventListener("click", handleCameraConnect);
    if (disconnectButton) disconnectButton.addEventListener("click", handleCameraDisconnect);

    // Settings button & modal
    const openSettingsBtn = document.getElementById('open-settings-btn');
    if (openSettingsBtn) openSettingsBtn.addEventListener('click', openSettingsModal);
    const settingsClose = document.getElementById('settings-close');
    if (settingsClose) settingsClose.addEventListener('click', closeSettingsModal);
    const settingsCancel = document.getElementById('settings-cancel');
    if (settingsCancel) settingsCancel.addEventListener('click', closeSettingsModal);
    const settingsScanBtn = document.getElementById('settings-scan');
    if (settingsScanBtn) settingsScanBtn.addEventListener('click', scanForCameras);
    const settingsSaveBtn = document.getElementById('settings-save');
    if (settingsSaveBtn) settingsSaveBtn.addEventListener('click', saveSettings);

    // Upload event listeners
    document.getElementById("btn-upload").addEventListener("click", handleUploadClick);
    document.getElementById("upload-input").addEventListener("change", uploadImage);
    document.getElementById("modal-close").addEventListener("click", closeUploadModal);
    
    // Close modal when clicking outside
    document.getElementById("upload-modal").addEventListener("click", (e) => {
        if (e.target.id === "upload-modal") {
            closeUploadModal();
        }
    });

    // Navigation screen switcher tabs (2-screen structure)
    const navButtons = document.querySelectorAll(".screen-switcher .nav-btn");
    const pageContainers = document.querySelectorAll(".page-container");
    
    navButtons.forEach(btn => {
        btn.addEventListener("click", (e) => {
            navButtons.forEach(b => b.classList.remove("active"));
            e.currentTarget.classList.add("active");
            
            const targetPage = e.currentTarget.dataset.page;
            pageContainers.forEach(container => {
                if (container.id === targetPage) {
                    container.classList.add("active");
                } else {
                    container.classList.remove("active");
                }
            });

            updateTabIndicator();
        });
    });

    // History source switching tabs
    const tabButtons = document.querySelectorAll(".history-tabs .tab-btn");
    tabButtons.forEach(btn => {
        btn.addEventListener("click", (e) => {
            tabButtons.forEach(b => b.classList.remove("active"));
            e.currentTarget.classList.add("active");
            
            currentHistorySource = e.currentTarget.dataset.source;
            
            // Re-fetch data and analytics based on selected tab source
            fetchHistory();
            fetchAnalyticsSummary();
        });
    });
}

function updateTabIndicator() {
    const activeTab = document.querySelector('.screen-switcher .nav-btn.active');
    const indicator = document.querySelector('.screen-switcher .tab-indicator');
    if (!activeTab || !indicator) return;

    const tabRect = activeTab.getBoundingClientRect();
    const parentRect = activeTab.parentElement.getBoundingClientRect();
    const left = tabRect.left - parentRect.left;
    const width = tabRect.width;

    indicator.style.width = `${width}px`;
    indicator.style.transform = `translateX(${left}px)`;
}

// Dynamic logger console output
function logger(msg) {
    console.log(`[MetalSense] ${msg}`);
}
