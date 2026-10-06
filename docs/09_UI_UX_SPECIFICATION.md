# UI/UX Design & Liquid Visualization Specification

## 1. Design Philosophy & Aesthetic Identity
The dashboard is designed as a **modern, high-precision Precision Agriculture IoT interface**. It balances visual appeal with scientific clarity, utilizing a dark-green natural palette accented with clean glassmorphic panels, clear typographic hierarchy, and micro-interactions.

---

## 2. Color System & Typography

### 2.1 Color Tokens
```css
:root {
  /* Brand / Nature Greens */
  --bg-app: #f4f7f5;
  --sidebar-bg: #0f281e;
  --sidebar-hover: #1b4332;
  --sidebar-active: #2d6a4f;
  --primary-green: #2d6a4f;
  --emerald-accent: #10b981;
  --leaf-tint: #ecfdf5;

  /* Neutrals */
  --surface-card: #ffffff;
  --text-primary: #111827;
  --text-secondary: #4b5563;
  --text-muted: #9ca3af;
  --border-light: #e5e7eb;

  /* Liquid Wave Palette */
  --water-deep: #0284c7;
  --water-mid: #38bdf8;
  --water-crest: rgba(255, 255, 255, 0.35);

  /* Status Accents */
  --status-good: #10b981;
  --status-good-bg: #dcfce7;
  --status-warn: #f59e0b;
  --status-warn-bg: #fef3c7;
  --status-danger: #ef4444;
  --status-danger-bg: #fee2e2;
}
```

### 2.2 Typography
- **Headings & Key Metrics:** `Outfit`, sans-serif (weights 600, 700).
- **Body & Telemetry Data:** `Inter`, system-ui, sans-serif (weights 400, 500).
- **Tabular & Code Readouts:** Fixed-width numeric tabular figures (`font-variant-numeric: tabular-nums`).

---

## 3. Animated Liquid Moisture Visualization Component

### 3.1 Anatomical Architecture
The moisture visualization replaces the static progress bar with an interactive, transparent water column:
```
┌─────────────────────────────────┐
│        SOIL MOISTURE TANK       │
│  ┌───────────────────────────┐  │
│  │ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ │ <── Continuous Wave Crest (Dual Sine Wave)
│  │                           │  │
│  │          64 %             │ <── Centered High-Contrast Percentage
│  │         "Good"            │ <── Relative Classification
│  │                           │  │
│  │ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ │ <── Smoothly Rising/Falling Liquid Body
│  └───────────────────────────┘  │
│  Raw ADC: 2170 | Soil Temp: 27.7°C
│  Drying Risk: Low | Saturated Ref
└─────────────────────────────────┘
```

### 3.2 Technical Requirements
1. **Container Dimensions:** Rounded rectangular viewport ($140\text{px} \times 180\text{px}$) with subtle glass border and depth shadow.
2. **Smooth Value Interpolation:** CSS `transition: height 1.2s cubic-bezier(0.34, 1.56, 0.64, 1)` or transform-based height update. Never reset to zero during periodic polls.
3. **Continuous Wave Animation:** Two phase-shifted SVG wave paths or CSS sinusoidal pseudo-elements animating horizontally (`animation: wave-slide 4s linear infinite`).
4. **Error & Disconnected State:** When `moisture_percent` is null or invalid, the tank renders a tranquil empty baseline with a dashed error badge ("Sensor Offline").

---

## 4. Multi-View Navigation Architecture
The interface provides a seamless single-page application experience with dedicated active sections:
1. **Dashboard (Default):** Hero cards, liquid tank, environmental score, live telemetry table, quick recommendation.
2. **Plant Growth:** Vertical gantry diagram, canopy height tracking, $\Delta H$ growth rate, historical growth chart.
3. **Analytics:** Multi-variable trend comparison, min/avg/max aggregates, rate of drying analysis.
4. **Sensor History:** Paginated, searchable, exportable history table with raw and calculated columns.
5. **Device & Status:** ESP32 hardware telemetry, signal latency, firmware pinout, connection diagnostic history.
6. **Settings:** Configurable moisture classification thresholds, drying risk temperature limits, sensor baseline mounting height ($30\text{ cm}$).
