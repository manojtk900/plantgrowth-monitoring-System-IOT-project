/**
 * app.js
 * ======
 * IoT Plant Growth & Environmental Monitoring System
 * Modern Client Application Controller & Animated Liquid Visualizer
 */

// =====================================================================
// GLOBAL STATE & SYSTEM CONFIGURATION
// =====================================================================

const APP_CONFIG = {
    // Calibrated Capacitive Soil Moisture Sensor Points
    dryRaw: 3326,
    wetRaw: 1520,
    sensorMountHeightCm: 30.0,

    // Relative Soil Moisture Index (RSMI) Configurable Bands
    moistureClassifications: [
        { min: 0,  max: 10,  label: "Very Dry",                 badgeClass: "danger",  color: "#ef4444" },
        { min: 10, max: 25,  label: "Dry",                      badgeClass: "warning", color: "#f97316" },
        { min: 25, max: 40,  label: "Low",                      badgeClass: "warning", color: "#eab308" },
        { min: 40, max: 60,  label: "Moderate",                 badgeClass: "good",    color: "#84cc16" },
        { min: 60, max: 75,  label: "Good",                     badgeClass: "good",    color: "#10b981" },
        { min: 75, max: 90,  label: "Moist",                    badgeClass: "good",    color: "#06b6d4" },
        { min: 90, max: 100, label: "Very Moist / Wet Ref",     badgeClass: "info",    color: "#3b82f6" }
    ],

    // Heartbeat Timeout Thresholds (Seconds)
    heartbeatTimeouts: {
        online: 30,
        recent: 90,
        stale: 300,
        offline: 300
    }
};

// Global Chart Instances (Preserved across polling cycles to avoid recreation flicker)
let moistureChartInstance = null;
let temperatureChartInstance = null;
let heightChartInstance = null;

// History Pagination & Filter State
let historyState = {
    offset: 0,
    limit: 30,
    total: 0,
    searchQuery: "",
    deviceId: "",
    dateFrom: "",
    dateTo: "",
    minMoisture: "",
    maxMoisture: "",
    minTemp: "",
    maxTemp: "",
    rawRecords: []
};

// Current Active Telemetry Snapshot
let currentTelemetry = {
    deviceId: "ESP32_003",
    moisturePercent: null,
    moistureRaw: null,
    temperatureC: null,
    distanceCm: null,
    plantHeightCm: null,
    createdAt: null
};


// =====================================================================
// CENTRAL CONFIGURATION LOADER
// =====================================================================

async function loadSystemConfig() {
    try {
        const response = await fetch("/api/config");
        if (!response.ok) return;
        const config = await response.json();
        if (config.success) {
            if (config.calibration) {
                APP_CONFIG.dryRaw = config.calibration.dry_raw || APP_CONFIG.dryRaw;
                APP_CONFIG.wetRaw = config.calibration.wet_raw || APP_CONFIG.wetRaw;
                APP_CONFIG.sensorMountHeightCm = config.calibration.sensor_mount_height_cm || APP_CONFIG.sensorMountHeightCm;
            }
            if (config.moisture_classifications) {
                APP_CONFIG.moistureClassifications = config.moisture_classifications;
            }
            if (config.heartbeat_timeouts) {
                APP_CONFIG.heartbeatTimeouts = config.heartbeat_timeouts;
            }
        }
    } catch (e) {
        console.warn("Using local configuration constants:", e);
    }
}


// =====================================================================
// MOISTURE CLASSIFICATION HELPER
// =====================================================================

function getMoistureTier(percent) {
    if (percent === null || percent === undefined) {
        return { label: "Offline", badgeClass: "danger", color: "#9ca3af" };
    }
    for (const tier of APP_CONFIG.moistureClassifications) {
        if (percent >= tier.min && percent <= tier.max) {
            return {
                label: tier.label,
                badgeClass: tier.status_key || tier.badgeClass || "good",
                color: tier.color || "#10b981"
            };
        }
    }
    return percent > 100
        ? { label: "Saturated Ref", badgeClass: "info", color: "#3b82f6" }
        : { label: "Very Dry", badgeClass: "danger", color: "#ef4444" };
}


// =====================================================================
// TELEMETRY: LOAD LATEST DATA
// =====================================================================

async function loadLatestData() {
    try {
        const response = await fetch("/api/latest");
        if (!response.ok) {
            throw new Error(`HTTP Error ${response.status}`);
        }

        const result = await response.json();
        if (!result.success || !result.data) {
            throw new Error("No telemetry data returned");
        }

        const data = result.data;
        currentTelemetry = data;

        // 1. Device ID Synchronization (Removes any hardcoded ESP32_001)
        const deviceId = data.device_id || "ESP32_003";
        updateElementText("sidebarDeviceId", `Node: ${deviceId}`);
        updateElementText("headerDeviceId", deviceId);
        updateElementText("deviceNodeId", deviceId);

        // 2. Soil Moisture & Animated Liquid Tank
        const moisture = (data.moisture_percent !== null && data.moisture_percent !== undefined)
            ? Number(data.moisture_percent)
            : null;
        const moistureRaw = (data.moisture_raw !== null && data.moisture_raw !== undefined)
            ? Number(data.moisture_raw)
            : null;

        updateLiquidMoistureTank(moisture, moistureRaw, data.moisture_status, data.drying_risk);

        // 3. Soil Temperature
        const temperature = (data.temperature_c !== null && data.temperature_c !== undefined)
            ? Number(data.temperature_c)
            : null;
        updateTemperatureDisplay(temperature);

        // 4. HC-SR04 Distance & Plant Height
        const distance = (data.distance_cm !== null && data.distance_cm !== undefined)
            ? Number(data.distance_cm)
            : null;
        const height = (data.plant_height_cm !== null && data.plant_height_cm !== undefined)
            ? Number(data.plant_height_cm)
            : null;
        updateDistanceAndHeightDisplay(distance, height);

        // 5. Environmental Plant Condition Score
        if (data.plant_condition) {
            updatePlantConditionScore(data.plant_condition);
        }

        // 6. Live Telemetry Frame Table
        updateTelemetryTable(moisture, moistureRaw, temperature, distance, height, data.created_at);

        // 7. Device Heartbeat & Freshness
        if (data.device_liveness) {
            updateDeviceLiveness(data.device_liveness, data.created_at);
        }

        // 8. Contextual Alert Banner
        updateAlertBanner(moisture, data.drying_risk);

    } catch (error) {
        console.error("Latest telemetry fetch error:", error);
        setDeviceOfflineUI();
    }
}


// =====================================================================
// COMPONENT: ANIMATED LIQUID MOISTURE TANK
// =====================================================================

function updateLiquidMoistureTank(moisture, rawAdc, serverMoistureStatus, dryingRiskObj) {
    const liquidBody = document.getElementById("tankLiquidBody");
    const moistureValEl = document.getElementById("moistureValue");
    const rawValEl = document.getElementById("moistureRaw");
    const statusBadge = document.getElementById("moistureStatus");
    const classificationEl = document.getElementById("tankClassificationLabel");
    const dryingRiskEl = document.getElementById("moistureDryingRiskBadge");

    if (!liquidBody) return;

    if (moisture !== null) {
        // SMOOTH TRANSITION: Update height without restarting from zero!
        const clampedMoisture = Math.max(0, Math.min(100, moisture));
        liquidBody.style.height = `${clampedMoisture}%`;

        // Classification Tier
        const tier = getMoistureTier(clampedMoisture);
        const displayLabel = serverMoistureStatus || tier.label;

        if (moistureValEl) moistureValEl.textContent = clampedMoisture.toFixed(0);
        if (classificationEl) {
            classificationEl.textContent = displayLabel;
            classificationEl.style.color = tier.color;
        }

        if (statusBadge) {
            statusBadge.textContent = displayLabel.toUpperCase();
            statusBadge.className = `status-badge ${tier.badgeClass}`;
        }
    } else {
        // Disconnected or null sensor state
        liquidBody.style.height = "0%";
        if (moistureValEl) moistureValEl.textContent = "--";
        if (classificationEl) {
            classificationEl.textContent = "Sensor Offline";
            classificationEl.style.color = "#9ca3af";
        }
        if (statusBadge) {
            statusBadge.textContent = "OFFLINE";
            statusBadge.className = "status-badge danger";
        }
    }

    // Raw ADC Display
    if (rawValEl) {
        rawValEl.textContent = (rawAdc !== null) ? Math.round(rawAdc) : "--";
    }

    // Live Feed Tab mirror
    updateElementText("liveMoistureRaw", (rawAdc !== null) ? `${Math.round(rawAdc)} ADC` : "--");
    const liveRawBar = document.getElementById("liveRawAdcBar");
    if (liveRawBar && rawAdc !== null) {
        const pct = Math.max(0, Math.min(100, (rawAdc / 4095.0) * 100));
        liveRawBar.style.width = `${pct}%`;
    }

    // Drying Risk in Tank Footer
    if (dryingRiskEl) {
        const riskLevel = dryingRiskObj?.risk_level || "Unknown";
        dryingRiskEl.textContent = riskLevel;
        dryingRiskEl.style.color = (dryingRiskObj?.color) || "#10b981";
    }
}


// =====================================================================
// COMPONENT: SOIL TEMPERATURE DISPLAY
// =====================================================================

function updateTemperatureDisplay(temperature) {
    const tempValEl = document.getElementById("temperatureValue");
    const tempStatusEl = document.getElementById("temperatureStatus");
    const tempBarEl = document.getElementById("temperatureBar");
    const tempStateEl = document.getElementById("tempThermalState");
    const tempRecEl = document.getElementById("temperatureRecommendation");
    const tempMsgEl = document.getElementById("temperatureMessage");

    const tNum = (temperature !== null && temperature !== undefined && !isNaN(Number(temperature))) ? Number(temperature) : null;

    if (tempValEl) {
        tempValEl.textContent = (tNum !== null) ? tNum.toFixed(2) : "--";
    }

    updateElementText("liveTempRaw", (tNum !== null) ? `${tNum.toFixed(2)} °C` : "--");

    if (tNum !== null) {
        // Temperature progress bar (Scale 0 to 50°C)
        if (tempBarEl) {
            const barPct = Math.max(0, Math.min(100, (tNum / 50.0) * 100));
            tempBarEl.style.width = `${barPct}%`;
        }

        if (tNum < 15.0) {
            if (tempStatusEl) {
                tempStatusEl.textContent = "COLD";
                tempStatusEl.className = "status-badge warning";
            }
            if (tempStateEl) tempStateEl.textContent = "Cool Root Zone";
            if (tempRecEl) tempRecEl.textContent = "Thermal Alert: Cold Soil";
            if (tempMsgEl) tempMsgEl.textContent = "Low root-zone temperature may slow water uptake. Protect from chill.";
        } else if (tNum > 32.0) {
            if (tempStatusEl) {
                tempStatusEl.textContent = "HEAT ALERT";
                tempStatusEl.className = "status-badge danger";
            }
            if (tempStateEl) tempStateEl.textContent = "Thermal Stress";
            if (tempRecEl) tempRecEl.textContent = "Thermal Alert: High Heat";
            if (tempMsgEl) tempMsgEl.textContent = "High soil temperature accelerates transpiration and drying risk.";
        } else {
            if (tempStatusEl) {
                tempStatusEl.textContent = "OPTIMAL";
                tempStatusEl.className = "status-badge good";
            }
            if (tempStateEl) tempStateEl.textContent = "Optimal (20-28°C)";
            if (tempRecEl) tempRecEl.textContent = "Thermal State Normal";
            if (tempMsgEl) tempMsgEl.textContent = "Root-zone temperature is within optimal range for nutrient absorption.";
        }
    } else {
        if (tempStatusEl) {
            tempStatusEl.textContent = "DISCONNECTED";
            tempStatusEl.className = "status-badge danger";
        }
        if (tempStateEl) tempStateEl.textContent = "Sensor Offline";
    }
}


// =====================================================================
// COMPONENT: DISTANCE & PLANT HEIGHT DISPLAY
// =====================================================================

function updateDistanceAndHeightDisplay(distance, height) {
    const dNum = (distance !== null && distance !== undefined && !isNaN(Number(distance))) ? Number(distance) : null;
    const hNum = (height !== null && height !== undefined && !isNaN(Number(height))) ? Number(height) : null;

    updateElementText("distanceValue", (dNum !== null) ? dNum.toFixed(2) : "--");
    updateElementText("heightValue", (hNum !== null) ? hNum.toFixed(2) : "--");
    updateElementText("liveDistanceRaw", (dNum !== null) ? `${dNum.toFixed(2)} cm` : "--");

    // Beam graphic
    updateElementText("beamDistanceLabel", (dNum !== null) ? `${dNum.toFixed(1)} cm free gap` : "-- cm gap");

    // Mini plant stem in dashboard height card
    const miniStem = document.getElementById("miniPlantStem");
    if (miniStem) {
        if (hNum !== null) {
            const miniStemPct = Math.max(10, Math.min(95, (hNum / APP_CONFIG.sensorMountHeightCm) * 100));
            miniStem.style.height = `${miniStemPct}%`;
        } else {
            miniStem.style.height = "50%";
        }
    }

    // Gantry view update
    if (dNum !== null && hNum !== null) {
        updateElementText("rigDistanceText", `Flight Distance: ${dNum.toFixed(1)} cm`);
        updateElementText("rigHeightText", `Canopy Height: ${hNum.toFixed(1)} cm`);
        updateElementText("growthCurrentHeight", `${hNum.toFixed(2)} cm`);

        const canopyZone = document.getElementById("rigCanopyZone");
        if (canopyZone) {
            // Scale canopy height relative to 30.0 cm gantry
            const canopyPct = Math.max(5, Math.min(95, (hNum / APP_CONFIG.sensorMountHeightCm) * 100));
            canopyZone.style.height = `${canopyPct}%`;
        }
    }
}


// =====================================================================
// COMPONENT: ENVIRONMENTAL PLANT CONDITION SCORE
// =====================================================================

function updatePlantConditionScore(condition) {
    const scoreValEl = document.getElementById("healthScore");
    const badgeEl = document.getElementById("healthBadge");
    const titleEl = document.getElementById("healthTitle");
    const msgEl = document.getElementById("healthMessage");
    const reasonsContainer = document.getElementById("conditionBreakdownList");

    if (scoreValEl) scoreValEl.textContent = condition.score;

    if (badgeEl) {
        badgeEl.textContent = condition.status.toUpperCase();
        badgeEl.style.backgroundColor = `${condition.badge_color}22`;
        badgeEl.style.color = condition.badge_color;
    }

    if (titleEl) titleEl.textContent = `Plant Condition: ${condition.status}`;
    if (msgEl) {
        msgEl.textContent = condition.score >= 80
            ? "Environmental conditions are favorable for vegetative canopy growth."
            : condition.score >= 50
                ? "Suboptimal parameters detected. Review contributing factors below."
                : "Environmental stress detected. Immediate intervention recommended.";
    }

    // Render itemized transparent explanations
    if (reasonsContainer && condition.reasons && condition.reasons.length > 0) {
        reasonsContainer.innerHTML = condition.reasons
            .map(r => `<div class="reason-chip">✓ ${escapeHtml(r)}</div>`)
            .join("");
    }
}


// =====================================================================
// COMPONENT: DEVICE LIVENESS & ACCURATE HEARTBEAT
// =====================================================================

function updateDeviceLiveness(liveness, createdAt) {
    const statusBox = document.getElementById("connectionStatusBox");
    const dot = document.getElementById("connectionDot");
    const text = document.getElementById("connectionText");
    const secondsSub = document.getElementById("connectionSeconds");
    const devConn = document.getElementById("deviceConnection");
    const devIndicator = document.getElementById("deviceIndicator");
    const lastUpdateEl = document.getElementById("lastUpdate");
    const latencyEl = document.getElementById("heartbeatLatencyLabel");

    if (dot) {
        dot.className = `connection-dot ${liveness.online ? (liveness.state === "ONLINE" ? "online" : "recent") : "offline"}`;
    }

    if (text) {
        text.textContent = liveness.label || `● ${liveness.state}`;
    }

    if (secondsSub && liveness.seconds_since_last_seen !== null) {
        secondsSub.textContent = `(${liveness.seconds_since_last_seen}s ago)`;
    }

    if (devConn) {
        devConn.textContent = liveness.online ? "● Connected (Live Stream)" : "● Stale / Offline";
        devConn.className = liveness.online ? "status-online" : "status-badge danger";
    }

    if (devIndicator) {
        devIndicator.textContent = liveness.online ? "● LIVE" : "● OFFLINE";
        devIndicator.style.color = liveness.online ? "var(--emerald)" : "var(--status-danger)";
    }

    // Sync mobile top bar pill & mobile greeting status
    const mobileText = document.getElementById("mobileConnectionText");
    const mobilePill = document.getElementById("mobileLivePill");
    const mobileGreetingHeartbeat = document.getElementById("mobileGreetingHeartbeat");

    if (mobileText) {
        mobileText.textContent = liveness.online ? "LIVE" : liveness.state;
    }
    if (mobilePill) {
        mobilePill.className = `mobile-live-pill ${liveness.online ? "online" : "offline"}`;
    }
    if (mobileGreetingHeartbeat) {
        mobileGreetingHeartbeat.textContent = liveness.online ? "LIVE Telemetry" : `${liveness.state}`;
    }

    if (lastUpdateEl && createdAt) {
        try {
            const dt = new Date(createdAt.replace(" ", "T"));
            lastUpdateEl.textContent = dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        } catch (e) {
            lastUpdateEl.textContent = createdAt;
        }
    }

    if (latencyEl && liveness.seconds_since_last_seen !== null) {
        latencyEl.textContent = `${liveness.seconds_since_last_seen} seconds ago (${liveness.state})`;
    }
}

function setDeviceOfflineUI() {
    const dot = document.getElementById("connectionDot");
    const text = document.getElementById("connectionText");
    const devConn = document.getElementById("deviceConnection");
    const devIndicator = document.getElementById("deviceIndicator");

    if (dot) dot.className = "connection-dot offline";
    if (text) text.textContent = "● OFFLINE (No Signal)";
    if (devConn) {
        devConn.textContent = "● Disconnected";
        devConn.className = "status-badge danger";
    }
    if (devIndicator) {
        devIndicator.textContent = "● OFFLINE";
        devIndicator.style.color = "var(--status-danger)";
    }

    const mobileText = document.getElementById("mobileConnectionText");
    const mobilePill = document.getElementById("mobileLivePill");
    const mobileGreetingHeartbeat = document.getElementById("mobileGreetingHeartbeat");
    if (mobileText) mobileText.textContent = "OFFLINE";
    if (mobilePill) mobilePill.className = "mobile-live-pill offline";
    if (mobileGreetingHeartbeat) mobileGreetingHeartbeat.textContent = "Offline";
}


// =====================================================================
// COMPONENT: CONTEXTUAL ALERT BANNER & ADVISORIES
// =====================================================================

function updateAlertBanner(moisture, dryingRiskObj) {
    const alertBox = document.getElementById("alertBox");
    const alertTitle = document.getElementById("alertTitle");
    const alertMessage = document.getElementById("alertMessage");
    const alertIcon = document.getElementById("alertIcon");
    const waterRecTitle = document.getElementById("waterRecommendation");
    const waterRecMsg = document.getElementById("waterMessage");

    if (!alertBox) return;

    const mNum = (moisture !== null && moisture !== undefined && !isNaN(Number(moisture))) ? Number(moisture) : null;

    if (mNum !== null && mNum < 20.0) {
        alertBox.className = "alert-box danger";
        if (alertIcon) alertIcon.textContent = "🚨";
        if (alertTitle) alertTitle.textContent = "Critical Moisture Deficit";
        if (alertMessage) alertMessage.textContent = `Soil moisture is at ${mNum.toFixed(0)}% (Critical). Root-zone dehydration imminent.`;

        if (waterRecTitle) waterRecTitle.textContent = "💧 Irrigation Urgently Required";
        if (waterRecMsg) waterRecMsg.textContent = "Soil is critically dry. Apply controlled watering immediately.";
    } else if (mNum !== null && mNum < 35.0) {
        alertBox.className = "alert-box";
        if (alertIcon) alertIcon.textContent = "💧";
        if (alertTitle) alertTitle.textContent = "Low Soil Moisture Advisory";
        if (alertMessage) alertMessage.textContent = `Soil moisture is at ${mNum.toFixed(0)}%. Schedule irrigation soon.`;

        if (waterRecTitle) waterRecTitle.textContent = "💧 Water Soon";
        if (waterRecMsg) waterRecMsg.textContent = "Moisture is in lower operational zone. Plan next irrigation cycle.";
    } else if (dryingRiskObj && dryingRiskObj.risk_level === "High") {
        alertBox.className = "alert-box danger";
        if (alertIcon) alertIcon.textContent = "🔥";
        if (alertTitle) alertTitle.textContent = "High Evaporative Drying Risk";
        if (alertMessage) alertMessage.textContent = dryingRiskObj.explanation;

        if (waterRecTitle) waterRecTitle.textContent = "💧 Inspect Soil Hydration";
        if (waterRecMsg) waterRecMsg.textContent = dryingRiskObj.recommendation;
    } else {
        alertBox.className = "alert-box hidden";
        if (waterRecTitle) waterRecTitle.textContent = "💧 Hydration Normal";
        if (waterRecMsg) waterRecMsg.textContent = "Current soil moisture does not require immediate irrigation.";
    }
}


// =====================================================================
// COMPONENT: TELEMETRY TABLE
// =====================================================================

function updateTelemetryTable(moisture, rawAdc, temperature, distance, height, createdAt) {
    const mNum = (moisture !== null && moisture !== undefined && !isNaN(Number(moisture))) ? Number(moisture) : null;
    const tNum = (temperature !== null && temperature !== undefined && !isNaN(Number(temperature))) ? Number(temperature) : null;
    const dNum = (distance !== null && distance !== undefined && !isNaN(Number(distance))) ? Number(distance) : null;
    const hNum = (height !== null && height !== undefined && !isNaN(Number(height))) ? Number(height) : null;

    updateElementText("tableMoisture", (mNum !== null) ? `${mNum.toFixed(0)} %` : "--");
    updateElementText("tableMoistureRaw", (rawAdc !== null && rawAdc !== undefined) ? Math.round(Number(rawAdc)) : "--");
    updateElementText("tableTemperature", (tNum !== null) ? `${tNum.toFixed(2)} °C` : "--");
    updateElementText("tableDistance", (dNum !== null) ? `${dNum.toFixed(2)} cm` : "--");
    updateElementText("tableHeight", (hNum !== null) ? `${hNum.toFixed(2)} cm` : "--");

    if (createdAt) {
        const frameEl = document.getElementById("frameTimestamp");
        if (frameEl) {
            frameEl.textContent = `Frame: ${createdAt.replace("T", " ")}`;
        }
    }
}


// =====================================================================
// CHARTS: IN-PLACE DATASET UPDATES (ZERO CANVAS RECREATION FLICKER)
// =====================================================================

async function loadHistoryCharts() {
    try {
        const response = await fetch("/api/history?limit=30");
        if (!response.ok) return;

        const result = await response.json();
        if (!result.success || !result.data || result.data.length === 0) return;

        // Chronological order: Oldest to newest
        const records = [...result.data].reverse();

        const labels = records.map(r => {
            const dt = new Date(r.created_at.replace(" ", "T"));
            return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
        });

        const moistureData = records.map(r => (r.moisture_percent !== null) ? Number(r.moisture_percent) : null);
        const tempData = records.map(r => (r.temperature_c !== null) ? Number(r.temperature_c) : null);
        const heightData = records.map(r => (r.plant_height_cm !== null) ? Number(r.plant_height_cm) : null);

        // Update or instantiate Moisture Chart
        updateOrInitChart(
            "moistureChart",
            "moistureChartInstance",
            labels,
            "Moisture (%)",
            moistureData,
            "#0284c7",
            "rgba(2, 132, 199, 0.1)",
            0,
            100,
            "%"
        );

        // Update or instantiate Temperature Chart
        updateOrInitChart(
            "temperatureChart",
            "temperatureChartInstance",
            labels,
            "Temperature (°C)",
            tempData,
            "#10b981",
            "rgba(16, 185, 129, 0.1)",
            15,
            40,
            "°C"
        );

        // Update or instantiate Plant Height Chart
        updateOrInitChart(
            "heightChart",
            "heightChartInstance",
            labels,
            "Canopy Height (cm)",
            heightData,
            "#15803d",
            "rgba(21, 128, 61, 0.1)",
            0,
            30,
            "cm"
        );

    } catch (e) {
        console.error("Chart data sync error:", e);
    }
}

function updateOrInitChart(canvasId, instanceVarName, labels, label, data, color, bgColor, yMin, yMax, unit) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    let chartRef = window[instanceVarName];

    if (chartRef) {
        // IN-PLACE UPDATE: No destroy/recreate cycle!
        chartRef.data.labels = labels;
        chartRef.data.datasets[0].data = data;
        chartRef.update("none"); // Silent update without redraw stutter
    } else {
        // First-time instantiation
        window[instanceVarName] = new Chart(canvas, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: label,
                    data: data,
                    borderColor: color,
                    backgroundColor: bgColor,
                    borderWidth: 2.2,
                    pointRadius: 2.5,
                    pointHoverRadius: 5,
                    tension: 0.35,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y} ${unit}`
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { maxTicksLimit: 6, font: { size: 10 } },
                        grid: { display: false }
                    },
                    y: {
                        min: yMin,
                        max: yMax,
                        ticks: { font: { size: 10 } },
                        grid: { color: "#f1f5f9" }
                    }
                }
            }
        });
    }
}


// =====================================================================
// COMPONENT: SENSOR HISTORY LOG TABLE (PAGINATED & SEARCHABLE)
// =====================================================================

// =====================================================================
// COMPONENT: SENSOR HISTORY LOG TABLE (PAGINATED, FILTERED, SEARCHABLE)
// =====================================================================

async function loadHistoryTable() {
    const tableBody = document.getElementById("historyTableBody");
    const paginationInfo = document.getElementById("paginationInfo");
    const prevBtn = document.getElementById("prevPageBtn");
    const nextBtn = document.getElementById("nextPageBtn");
    const exportBtn = document.getElementById("exportCsvBtn");

    if (!tableBody) return;

    try {
        const params = new URLSearchParams();
        params.append("limit", historyState.limit);
        params.append("offset", historyState.offset);
        if (historyState.searchQuery) params.append("search", historyState.searchQuery);
        if (historyState.deviceId) params.append("device_id", historyState.deviceId);
        if (historyState.dateFrom) params.append("date_from", historyState.dateFrom);
        if (historyState.dateTo) params.append("date_to", historyState.dateTo);
        if (historyState.minMoisture !== "") params.append("min_moisture", historyState.minMoisture);
        if (historyState.maxMoisture !== "") params.append("max_moisture", historyState.maxMoisture);
        if (historyState.minTemp !== "") params.append("min_temp", historyState.minTemp);
        if (historyState.maxTemp !== "") params.append("max_temp", historyState.maxTemp);

        // Update CSV export link with the same query parameters
        if (exportBtn) {
            exportBtn.href = `/api/history/export?${params.toString()}`;
        }

        const response = await fetch(`/api/history?${params.toString()}`);
        if (!response.ok) throw new Error(`History fetch failed with status ${response.status}`);

        const result = await response.json();
        if (!result.success || !result.data) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="8" class="empty-state-cell">
                        <div class="empty-state-content">
                            <span class="empty-state-icon">📭</span>
                            <span class="empty-state-title">No telemetry records found</span>
                            <span class="empty-state-hint">Database has no telemetry records</span>
                        </div>
                    </td>
                </tr>`;
            if (paginationInfo) paginationInfo.textContent = "Showing 0 records";
            return;
        }

        historyState.total = result.total !== undefined ? result.total : result.count;
        historyState.rawRecords = result.data;
        renderHistoryRows();

        // Pagination controls update
        if (paginationInfo) {
            if (historyState.total === 0) {
                paginationInfo.textContent = "Showing 0 records";
            } else {
                const start = historyState.offset + 1;
                const end = Math.min(historyState.offset + historyState.limit, historyState.total);
                paginationInfo.textContent = `Showing ${start}–${end} of ${historyState.total} records`;
            }
        }

        if (prevBtn) prevBtn.disabled = (historyState.offset === 0);
        if (nextBtn) nextBtn.disabled = (historyState.offset + historyState.limit >= historyState.total);

    } catch (e) {
        console.error("History table error:", e);
        tableBody.innerHTML = `<tr><td colspan="8" class="text-center">Error loading history records: ${escapeHtml(e.message)}</td></tr>`;
    }
}

function renderHistoryRows() {
    const tableBody = document.getElementById("historyTableBody");
    if (!tableBody) return;

    if (historyState.rawRecords.length === 0) {
        const hasFilters = Boolean(
            historyState.searchQuery ||
            historyState.deviceId ||
            historyState.dateFrom ||
            historyState.dateTo ||
            historyState.minMoisture !== "" ||
            historyState.maxMoisture !== "" ||
            historyState.minTemp !== "" ||
            historyState.maxTemp !== ""
        );

        tableBody.innerHTML = `
            <tr>
                <td colspan="8" class="empty-state-cell">
                    <div class="empty-state-content">
                        <span class="empty-state-icon">${hasFilters ? "🔍" : "📭"}</span>
                        <span class="empty-state-title">${hasFilters ? "No matching records found" : "No telemetry records available"}</span>
                        <span class="empty-state-hint">${hasFilters ? "Try broadening date range or clearing search criteria" : "Telemetry readings will appear here once received from ESP32 node"}</span>
                    </div>
                </td>
            </tr>`;
        return;
    }

    tableBody.innerHTML = historyState.rawRecords.map(r => {
        const moisturePct = (r.moisture_percent !== null && r.moisture_percent !== undefined)
            ? `${Number(r.moisture_percent).toFixed(1)}%`
            : "--";
        const temp = (r.temperature_c !== null && r.temperature_c !== undefined)
            ? `${Number(r.temperature_c).toFixed(2)} °C`
            : "--";
        const dist = (r.distance_cm !== null && r.distance_cm !== undefined)
            ? `${Number(r.distance_cm).toFixed(2)} cm`
            : "--";
        const height = (r.plant_height_cm !== null && r.plant_height_cm !== undefined)
            ? `${Number(r.plant_height_cm).toFixed(2)} cm`
            : "--";
        const raw = (r.moisture_raw !== null && r.moisture_raw !== undefined)
            ? Math.round(r.moisture_raw)
            : "--";

        return `
            <tr>
                <td>${escapeHtml((r.created_at || "").replace("T", " "))}</td>
                <td><strong>${escapeHtml(r.device_id || "ESP32_003")}</strong></td>
                <td>${raw}</td>
                <td><strong>${moisturePct}</strong></td>
                <td>${temp}</td>
                <td>${dist}</td>
                <td class="text-green"><strong>${height}</strong></td>
                <td><span class="badge-active">● ${escapeHtml(r.status || "OK")}</span></td>
            </tr>
        `;
    }).join("");
}


// =====================================================================
// COMPONENT: SUMMARY ANALYTICS, TRENDS & RATES (PHASE 5)
// =====================================================================

async function loadAnalyticsData() {
    try {
        const response = await fetch("/api/analytics");
        if (!response.ok) return;

        const result = await response.json();
        if (!result.success) return;

        updateElementText("analyticsSampleCount", result.sample_count || "--");

        // 1. Soil Moisture Analytics & Dynamics
        if (result.moisture) {
            updateElementText("analyticsAvgMoisture", (result.moisture.avg !== null) ? `${result.moisture.avg}%` : "-- %");
            updateElementText("analyticsMoistureRange", `Min: ${result.moisture.min ?? "--"}% | Max: ${result.moisture.max ?? "--"}%`);

            const mTrend = result.moisture.trend || "Stable";
            const mBadge = document.getElementById("analyticsMoistureTrendBadge");
            if (mBadge) {
                mBadge.className = `trend-badge trend-${mTrend.toLowerCase()}`;
                const arrow = mTrend === "Increasing" ? "↑ Rising" : (mTrend === "Falling" ? "↓ Falling" : "→ Stable");
                mBadge.textContent = arrow;
            }
            updateElementText("analyticsMoistureRateValue", result.moisture.rate_label || "Insufficient data");
        }

        // 2. Temperature Analytics & Dynamics
        if (result.temperature) {
            updateElementText("analyticsAvgTemp", (result.temperature.avg !== null) ? `${result.temperature.avg} °C` : "-- °C");
            updateElementText("analyticsTempRange", `Min: ${result.temperature.min ?? "--"}°C | Max: ${result.temperature.max ?? "--"}°C`);

            const tTrend = result.temperature.trend || "Stable";
            const tBadge = document.getElementById("analyticsTempTrendBadge");
            if (tBadge) {
                tBadge.className = `trend-badge trend-${tTrend.toLowerCase()}`;
                const arrow = tTrend === "Increasing" ? "↑ Rising" : (tTrend === "Falling" ? "↓ Falling" : "→ Stable");
                tBadge.textContent = arrow;
            }
            updateElementText("analyticsTempRateValue", result.temperature.rate_label || "Insufficient data");
        }

        // 3. Plant Canopy Growth Analytics & Dynamics
        if (result.growth) {
            const currentHgt = (result.growth.current_height_cm !== null && result.growth.current_height_cm !== undefined)
                ? `${result.growth.current_height_cm} cm`
                : "-- cm";
            updateElementText("analyticsCurrentHeight", currentHgt);
            updateElementText("analyticsHeightRange", `Min: ${result.growth.min_height_cm ?? "--"} cm | Max: ${result.growth.max_height_cm ?? "--"} cm`);

            const gTrend = result.growth.trend || "Stable";
            const gBadge = document.getElementById("analyticsGrowthTrendBadge");
            if (gBadge) {
                const isGrowing = gTrend === "Growing";
                gBadge.className = `trend-badge ${isGrowing ? "trend-growing" : "trend-stable"}`;
                gBadge.textContent = isGrowing ? "🌱 Growing" : (gTrend === "Stable" ? "→ Stable" : "— No Trend");
            }
            updateElementText("analyticsGrowthRateValue", result.growth.rate_label || "Insufficient data");

            const growthDelta = result.growth.total_growth_cm;
            const sign = (growthDelta !== undefined && growthDelta >= 0) ? "+" : "";
            const formattedDelta = (growthDelta !== undefined) ? `${sign}${growthDelta} cm` : "-- cm";
            updateElementText("analyticsNetGrowth", formattedDelta);
            updateElementText("growthNetElongation", formattedDelta);
            updateElementText("growthDeltaValue", formattedDelta);
            if (result.growth.baseline_height_cm) {
                updateElementText("baselineHeightValue", `${result.growth.baseline_height_cm} cm`);
                updateElementText("growthInitialHeight", `${result.growth.baseline_height_cm} cm`);
            }
        }
    } catch (e) {
        console.error("Analytics fetch error:", e);
    }
}


// =====================================================================
// COMPONENT: CALIBRATION & SETTINGS CONTROLLER (PHASE 6)
// =====================================================================

async function loadCalibrationSettings() {
    try {
        const response = await fetch("/api/settings");
        if (!response.ok) return;

        const result = await response.json();
        if (result.success && result.settings) {
            const s = result.settings;
            const dryInput = document.getElementById("dryRawInput");
            const wetInput = document.getElementById("wetRawInput");
            const mountInput = document.getElementById("mountHeightInput");
            const tempInput = document.getElementById("dryingRiskTempInput");
            const lowMInput = document.getElementById("lowMoistureInput");
            const updatedLabel = document.getElementById("calLastUpdatedLabel");

            if (dryInput) dryInput.value = s.dry_raw;
            if (wetInput) wetInput.value = s.wet_raw;
            if (mountInput) mountInput.value = s.sensor_mount_height_cm;
            if (tempInput) tempInput.value = s.drying_risk_temp_threshold;
            if (lowMInput) lowMInput.value = s.low_moisture_threshold;

            if (updatedLabel && s.last_updated) {
                updatedLabel.textContent = `Last update: ${s.last_updated.replace("T", " ").split(".")[0]}`;
            }

            // Sync global APP_CONFIG
            APP_CONFIG.dryRaw = s.dry_raw;
            APP_CONFIG.wetRaw = s.wet_raw;
            APP_CONFIG.sensorMountHeightCm = s.sensor_mount_height_cm;
        }
    } catch (e) {
        console.error("Calibration settings fetch error:", e);
    }
}

async function saveCalibrationSettings() {
    const dryVal = parseFloat(document.getElementById("dryRawInput")?.value);
    const wetVal = parseFloat(document.getElementById("wetRawInput")?.value);
    const mountVal = parseFloat(document.getElementById("mountHeightInput")?.value);
    const tempVal = parseFloat(document.getElementById("dryingRiskTempInput")?.value);
    const lowMVal = parseFloat(document.getElementById("lowMoistureInput")?.value);

    // Client-side validation guardrails
    if (isNaN(dryVal) || isNaN(wetVal) || dryVal <= wetVal) {
        showCalibrationAlert("Invalid calibration: Dry Reference must be strictly greater than Wet Reference for this sensor.", "danger");
        return;
    }
    if (dryVal < 0 || dryVal > 4095 || wetVal < 0 || wetVal > 4095) {
        showCalibrationAlert("Invalid ADC range: Both Dry and Wet values must be within 0 to 4095.", "danger");
        return;
    }
    if ((dryVal - wetVal) < 100) {
        showCalibrationAlert("Calibration span too narrow: Difference between dry and wet must be >= 100 counts.", "danger");
        return;
    }

    try {
        const response = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                dry_raw: dryVal,
                wet_raw: wetVal,
                sensor_mount_height_cm: mountVal,
                drying_risk_temp_threshold: tempVal,
                low_moisture_threshold: lowMVal
            })
        });

        const result = await response.json();
        if (result.success) {
            showCalibrationAlert("✅ Calibration successfully saved and applied to backend RSMI calculations.", "success");
            await loadCalibrationSettings();
            await loadLatestData();
            await loadHistoryCharts();
        } else {
            showCalibrationAlert(`Failed: ${result.message || "Invalid configuration parameters"}`, "danger");
        }
    } catch (e) {
        console.error("Save calibration error:", e);
        showCalibrationAlert("Network error saving calibration settings.", "danger");
    }
}

async function resetCalibrationDefaults() {
    const dryInput = document.getElementById("dryRawInput");
    const wetInput = document.getElementById("wetRawInput");
    const mountInput = document.getElementById("mountHeightInput");
    const tempInput = document.getElementById("dryingRiskTempInput");
    const lowMInput = document.getElementById("lowMoistureInput");

    if (dryInput) dryInput.value = 3326;
    if (wetInput) wetInput.value = 1520;
    if (mountInput) mountInput.value = 30.0;
    if (tempInput) tempInput.value = 30.0;
    if (lowMInput) lowMInput.value = 25.0;

    await saveCalibrationSettings();
}

function showCalibrationAlert(message, type) {
    const alertBox = document.getElementById("calibrationAlert");
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = `cal-alert ${type}`;
    alertBox.classList.remove("hidden");
    setTimeout(() => {
        alertBox.classList.add("hidden");
    }, 6000);
}


// =====================================================================
// TAB NAVIGATION & EVENT CONTROLLER
// =====================================================================

function initNavigation() {
    const navItems = document.querySelectorAll(".nav-item");
    const bottomNavItems = document.querySelectorAll(".bottom-nav-item[data-view]");
    const viewSections = document.querySelectorAll(".view-section");
    const pageTitle = document.getElementById("pageTitle");
    const pageSubtitle = document.getElementById("pageSubtitle");

    // Drawer controls
    const appSidebar = document.getElementById("appSidebar");
    const drawerBackdrop = document.getElementById("drawerBackdrop");
    const mobileMenuBtn = document.getElementById("mobileMenuBtn");
    const drawerCloseBtn = document.getElementById("drawerCloseBtn");
    const bottomMoreBtn = document.getElementById("bottomMoreBtn");

    function openMobileDrawer() {
        if (appSidebar) appSidebar.classList.add("open");
        if (drawerBackdrop) drawerBackdrop.classList.add("active");
        document.body.style.overflow = "hidden";
    }

    function closeMobileDrawer() {
        if (appSidebar) appSidebar.classList.remove("open");
        if (drawerBackdrop) drawerBackdrop.classList.remove("active");
        document.body.style.overflow = "";
    }

    function toggleMobileDrawer() {
        if (appSidebar && appSidebar.classList.contains("open")) {
            closeMobileDrawer();
        } else {
            openMobileDrawer();
        }
    }

    if (mobileMenuBtn) mobileMenuBtn.addEventListener("click", toggleMobileDrawer);
    if (drawerCloseBtn) drawerCloseBtn.addEventListener("click", closeMobileDrawer);
    if (drawerBackdrop) drawerBackdrop.addEventListener("click", closeMobileDrawer);
    if (bottomMoreBtn) {
        bottomMoreBtn.addEventListener("click", (e) => {
            e.preventDefault();
            toggleMobileDrawer();
        });
    }

    const viewTitles = {
        dashboard: {
            title: "Environmental Monitoring Dashboard",
            sub: "Real-time edge telemetry from ESP32 DevKit V1 node"
        },
        live: {
            title: "High-Resolution Live Telemetry Feed",
            sub: "Direct hardware ADC conversions and pulse flight timings"
        },
        growth: {
            title: "Plant Growth & Canopy Elongation Analysis",
            sub: "Non-contact ultrasonic tracking from 30.0 cm reference gantry"
        },
        analytics: {
            title: "Environmental Analytics & Statistics",
            sub: "Summary metrics and honest rate calculations calculated from verified historical records"
        },
        history: {
            title: "Sensor History Log Explorer",
            sub: "Search, filter, paginate, and export historical database records"
        },
        device: {
            title: "Device Diagnostics & Calibration Settings",
            sub: "Configure Relative Soil Moisture Index (RSMI) calibration and review hardware topology"
        }
    };

    function switchView(viewKey) {
        if (!viewKey) return;

        // Sync sidebar items
        navItems.forEach(n => {
            if (n.getAttribute("data-view") === viewKey) {
                n.classList.add("active");
            } else {
                n.classList.remove("active");
            }
        });

        // Sync bottom nav items
        bottomNavItems.forEach(b => {
            if (b.getAttribute("data-view") === viewKey) {
                b.classList.add("active");
            } else {
                b.classList.remove("active");
            }
        });

        // Show corresponding section
        viewSections.forEach(section => {
            if (section.id === `view-${viewKey}`) {
                section.classList.add("active");
            } else {
                section.classList.remove("active");
            }
        });

        // Update header text
        if (viewTitles[viewKey]) {
            if (pageTitle) pageTitle.textContent = viewTitles[viewKey].title;
            if (pageSubtitle) pageSubtitle.textContent = viewTitles[viewKey].sub;
        }

        // Close drawer on mobile if open
        closeMobileDrawer();

        // Scroll to top of content for clean view transition
        window.scrollTo({ top: 0, behavior: "smooth" });

        // Trigger specific view loaders
        if (viewKey === "analytics") loadAnalyticsData();
        if (viewKey === "history") loadHistoryTable();
        if (viewKey === "device") loadCalibrationSettings();
        if (viewKey === "growth") {
            const dist = currentTelemetry.distance_cm ?? currentTelemetry.distanceCm;
            const hgt = currentTelemetry.plant_height_cm ?? currentTelemetry.plantHeightCm;
            updateDistanceAndHeightDisplay(dist, hgt);
        }
    }

    // Attach click listeners to sidebar nav items
    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const viewKey = item.getAttribute("data-view");
            switchView(viewKey);
        });
    });

    // Attach click listeners to bottom nav items
    bottomNavItems.forEach(bItem => {
        bItem.addEventListener("click", (e) => {
            e.preventDefault();
            const viewKey = bItem.getAttribute("data-view");
            switchView(viewKey);
        });
    });

    // 1. History Controls: Search Input (debounced)
    const searchInput = document.getElementById("historySearchInput");
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener("input", (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                historyState.searchQuery = e.target.value.trim();
                historyState.offset = 0;
                loadHistoryTable();
            }, 300);
        });
    }

    // 2. History Controls: Device Filter
    const deviceSelect = document.getElementById("historyDeviceSelect");
    if (deviceSelect) {
        deviceSelect.addEventListener("change", (e) => {
            historyState.deviceId = e.target.value;
            historyState.offset = 0;
            loadHistoryTable();
        });
    }

    // 3. History Controls: Limit Select
    const limitSelect = document.getElementById("historyLimitSelect");
    if (limitSelect) {
        limitSelect.addEventListener("change", (e) => {
            historyState.limit = parseInt(e.target.value, 10);
            historyState.offset = 0;
            loadHistoryTable();
        });
    }

    // 4. History Controls: Filter & Reset Buttons
    const applyFiltersBtn = document.getElementById("applyFiltersBtn");
    if (applyFiltersBtn) {
        applyFiltersBtn.addEventListener("click", () => {
            historyState.dateFrom = document.getElementById("historyDateFrom")?.value || "";
            historyState.dateTo = document.getElementById("historyDateTo")?.value || "";
            historyState.minMoisture = document.getElementById("historyMinMoisture")?.value || "";
            historyState.maxMoisture = document.getElementById("historyMaxMoisture")?.value || "";
            historyState.minTemp = document.getElementById("historyMinTemp")?.value || "";
            historyState.maxTemp = document.getElementById("historyMaxTemp")?.value || "";
            historyState.offset = 0;
            loadHistoryTable();
        });
    }

    const resetFiltersBtn = document.getElementById("resetFiltersBtn");
    if (resetFiltersBtn) {
        resetFiltersBtn.addEventListener("click", () => {
            if (searchInput) searchInput.value = "";
            if (deviceSelect) deviceSelect.value = "";
            const dFrom = document.getElementById("historyDateFrom");
            const dTo = document.getElementById("historyDateTo");
            const minM = document.getElementById("historyMinMoisture");
            const maxM = document.getElementById("historyMaxMoisture");
            const minT = document.getElementById("historyMinTemp");
            const maxT = document.getElementById("historyMaxTemp");
            if (dFrom) dFrom.value = "";
            if (dTo) dTo.value = "";
            if (minM) minM.value = "";
            if (maxM) maxM.value = "";
            if (minT) minT.value = "";
            if (maxT) maxT.value = "";

            historyState.searchQuery = "";
            historyState.deviceId = "";
            historyState.dateFrom = "";
            historyState.dateTo = "";
            historyState.minMoisture = "";
            historyState.maxMoisture = "";
            historyState.minTemp = "";
            historyState.maxTemp = "";
            historyState.offset = 0;
            loadHistoryTable();
        });
    }

    // 5. History Pagination: Prev / Next Buttons
    const prevBtn = document.getElementById("prevPageBtn");
    if (prevBtn) {
        prevBtn.addEventListener("click", () => {
            if (historyState.offset > 0) {
                historyState.offset = Math.max(0, historyState.offset - historyState.limit);
                loadHistoryTable();
            }
        });
    }

    const nextBtn = document.getElementById("nextPageBtn");
    if (nextBtn) {
        nextBtn.addEventListener("click", () => {
            if (historyState.offset + historyState.limit < historyState.total) {
                historyState.offset += historyState.limit;
                loadHistoryTable();
            }
        });
    }

    // 6. Refresh Analytics Button
    const refreshAnalyticsBtn = document.getElementById("refreshAnalyticsBtn");
    if (refreshAnalyticsBtn) {
        refreshAnalyticsBtn.addEventListener("click", () => {
            loadAnalyticsData();
        });
    }

    // 7. Calibration Form: Save & Reset
    const saveCalibrationBtn = document.getElementById("saveCalibrationBtn");
    if (saveCalibrationBtn) {
        saveCalibrationBtn.addEventListener("click", saveCalibrationSettings);
    }

    const resetCalibrationBtn = document.getElementById("resetCalibrationBtn");
    if (resetCalibrationBtn) {
        resetCalibrationBtn.addEventListener("click", resetCalibrationDefaults);
    }
}


// =====================================================================
// UTILITY HELPERS
// =====================================================================

function updateElementText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


function updateGreeting() {
    const hour = new Date().getHours();
    let greeting = "Good Morning 🌱";
    if (hour >= 12 && hour < 17) {
        greeting = "Good Afternoon 🌱";
    } else if (hour >= 17 || hour < 5) {
        greeting = "Good Evening 🌱";
    }
    const el = document.getElementById("mobileGreetingText");
    if (el) el.textContent = greeting;
}


// =====================================================================
// INITIALIZATION & POLLING CYCLES
// =====================================================================

document.addEventListener("DOMContentLoaded", async () => {
    // 0. Set dynamic time-of-day greeting
    updateGreeting();

    // 1. Load central calibration configuration
    await loadSystemConfig();
    await loadCalibrationSettings();

    // 2. Initialize Tab Navigation, Drawer, and Event Handlers
    initNavigation();

    // 3. Initial Data Fetch
    await loadLatestData();
    await loadHistoryCharts();
    await loadHistoryTable();
    await loadAnalyticsData();

    // 4. Polling Cycles
    // Real-time telemetry & liquid tank: every 5 seconds
    setInterval(loadLatestData, 5000);

    // Trend charts (silent in-place updates): every 10 seconds
    setInterval(loadHistoryCharts, 10000);

    // Summary analytics: every 30 seconds
    setInterval(loadAnalyticsData, 30000);
});