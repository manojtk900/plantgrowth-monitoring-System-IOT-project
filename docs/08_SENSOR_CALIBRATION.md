# Sensor Calibration & Moisture Mathematical Model

## 1. Soil Moisture Physical Principles
The system utilizes a capacitive soil moisture sensor (v1.2). Unlike resistive probes that suffer from galvanic corrosion, capacitive probes are insulated and sense capacitance changes governed by the dielectric constant of the surrounding medium ($\varepsilon_{air} \approx 1$, $\varepsilon_{dry\_soil} \approx 3–5$, $\varepsilon_{water} \approx 80$).

As soil moisture increases, the bulk dielectric permittivity increases, increasing capacitance $C$. In the 555-timer / oscillator circuit on the probe, higher capacitance reduces the filtered DC analog output voltage $V_{out}$. The ESP32's 12-bit ADC converts this voltage into a raw integer $0–4095$.

Therefore:
- **Dry Soil $\implies$ Lower Capacitance $\implies$ Higher Voltage $\implies$ Higher Raw ADC.**
- **Wet Soil $\implies$ Higher Capacitance $\implies$ Lower Voltage $\implies$ Lower Raw ADC.**

---

## 2. Measured Calibration Constants
Empirical two-point calibration performed in the target laboratory substrate yielded:
- **Dry Soil Reference Point ($RAW_{dry}$):** `3326` (air-dry soil baseline).
- **Saturated Soil Reference Point ($RAW_{wet}$):** `1520` (submerged / saturated baseline).

---

## 3. Mathematical Transfer Function
The Relative Soil Moisture Index (RSMI, %) is derived linearly on the Flask backend:

$$RSMI = \left( \frac{RAW_{dry} - RAW_{measured}}{RAW_{dry} - RAW_{wet}} \right) \times 100$$

Substituting measured points:
$$RSMI = \left( \frac{3326 - RAW_{measured}}{3326 - 1520} \right) \times 100 = \left( \frac{3326 - RAW_{measured}}{1806} \right) \times 100$$

### Clamping & Normalization
To prevent negative percentages or numbers $>100\%$ resulting from temperature drift or sensor noise:
$$RSMI_{clamped} = \max\left(0.0, \min\left(100.0, RSMI\right)\right)$$

---

## 4. Central Configurable Classification

The system defines non-hardcoded relative classification tiers configured centrally on the server and shared with the client:

| Moisture Range (%) | Classification Label | Color Accent | Agronomic Interpretation |
| :--- | :--- | :--- | :--- |
| **0 – 10%** | Very Dry | `#ef4444` (Crimson) | Severe root moisture deficit; immediate wilting risk. |
| **10 – 25%** | Dry | `#f97316` (Orange) | Moisture depleted below optimal root zone uptake. |
| **25 – 40%** | Low | `#eab308` (Amber) | Sub-optimal moisture; monitoring and irrigation prep required. |
| **40 – 60%** | Moderate | `#84cc16` (Lime) | Adequate moisture for balanced vegetative respiration. |
| **60 – 75%** | Good | `#10b981` (Emerald) | Optimal root-zone hydration zone. |
| **75 – 90%** | Moist | `#06b6d4` (Cyan) | Elevated moisture; optimal for high-transpiration canopies. |
| **90 – 100%** | Very Moist / Saturated | `#3b82f6` (Blue) | Field capacity or saturated reference; withhold irrigation. |

---

## 5. Explicit Agronomic Disclaimer
> [!IMPORTANT]
> **Scientific Clarity Notice:**
> The value produced by this formula represents a **Relative Soil Moisture Index (RSMI)** calibrated specifically between the local laboratory dry baseline and water-saturated baseline. It does **not** represent laboratory-measured volumetric water content ($\theta_v, \text{cm}^3/\text{cm}^3$), gravimetric moisture content, or soil matric potential ($\text{kPa}$). System documentation and UI labels must explicitly designate this metric as a relative index.
