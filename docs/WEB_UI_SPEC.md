# HTRAM Embedded Web Interface & REST API Specification

**Document Revision:** 2.0.0  
**Status:** Authoritative Technical Specification  
**Component:** `custom_components/htram_web`  
**Dependencies:** ESPHome `web_server_base:`, ESP-IDF NVS, AsyncTCP / ESPAsyncWebServer

---

## 1. System Architecture

### 1.1 Embedded Web Server on Port 80
HTRAM provides a native, low-latency embedded web management interface running on standard HTTP port 80. The server subsystem is constructed on top of ESPHome's native `web_server_base:` component, leveraging `AsyncWebServer` (asynchronous TCP socket model) to ensure non-blocking HTTP request processing that does not starve real-time display rendering or peripheral polling.

```
                      +---------------------------------------+
                      |       Web Browser (Phone / PC)        |
                      +-------------------+-------------------+
                                          |
                                          | HTTP / 80 (Wi-Fi)
                                          v
+---------------------------------------------------------------------------------+
| ESP32 FIRMWARE                                                                  |
|                                                                                 |
|   +-------------------------------------------------------------------------+   |
|   | AsyncWebServer (web_server_base:)                                       |   |
|   | - GET  / (Inlined PROGMEM HTML/CSS/JS)                                  |   |
|   | - GET  /api/status                                                      |   |
|   | - POST /api/settings                                                    |   |
|   | - POST /api/check_update                                                |   |
|   | - POST /api/ota_update                                                  |   |
|   | - POST /api/reboot                                                      |   |
|   +------------------------------------+------------------------------------+   |
|                                        |                                        |
|                     AsyncTCP Thread    | Safe Dispatch via Component::defer     |
|                                        v                                        |
|   +-------------------------------------------------------------------------+   |
|   | HtramWebComponent (Main ESPHome Event Loop)                             |   |
|   |                                                                         |   |
|   |   +-------------------+    +--------------------+    +--------------+   |   |
|   |   |   NVS Storage     |    |   Entity Control   |    | Core Arbiter |   |   |
|   |   | (HtramWebSettings)|    | (Switches/Numbers) |    |  Callbacks   |   |   |
|   |   | 0x48545232 / 80 B |    | Temp Trim / Alarm  |    |  Geo Update  |   |   |
|   |   +-------------------+    +--------------------+    +--------------+   |   |
|   +-------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------+
```

### 1.2 Zero-CDN Single-Page Application (SPA)
To fulfill the Standalone-First paradigm during network outages or air-gapped deployments:
1. **Zero External Resource Dependencies:** The Web UI requires **zero** external CSS libraries (e.g. Bootstrap, Tailwind), JavaScript frameworks (e.g. React, Vue), or remote web fonts (e.g. Google Fonts). 
2. **Flash PROGMEM Inlining:** The complete responsive web application is declared as a C++ raw string literal (`STANDALONE_INDEX_HTML`) stored in flash memory (`web_page.h`).
3. **Bandwidth & Footprint Efficiency:** The inlined page occupies less than 35 KB of flash memory. The browser loads the interface in a single HTTP GET request without round-trip latency.
4. **Mobile-First Responsive Layout:** Implements CSS Flexbox and Grid layouts, optimized for one-handed mobile touch interaction and dark-room viewing (`#090d16` background, `#131b2e` cards).

---

## 2. Exhaustive REST API Contracts

All API endpoints reside under the `/api/` path. Payloads are strictly formatted as UTF-8 encoded JSON.

### 2.1 GET `/api/status`
Retrieves live sensor telemetry, device operational metrics, active air raid threat status, and persistent configuration settings.

#### 2.1.1 HTTP Request
- **Method:** `GET`
- **Path:** `/api/status`
- **Headers:** None required (`Accept: application/json` recommended)

#### 2.1.2 JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "HtramStatusResponse",
  "type": "object",
  "required": [
    "version", "new_version", "region", "lat", "lon", "city", 
    "alert_active", "free_heap", "min_free_heap", "reset_reason"
  ],
  "properties": {
    "version": { "type": "string", "description": "Running firmware version" },
    "new_version": { "type": "string", "description": "Available update tag or empty string" },
    "region": { "type": "integer", "description": "Configured JAAM region ID" },
    "lat": { "type": "number", "description": "Latitude coordinate for Open-Meteo" },
    "lon": { "type": "number", "description": "Longitude coordinate for Open-Meteo" },
    "city": { "type": "string", "description": "Human-readable settlement name" },
    "alert_active": { "type": "boolean", "description": "Current air raid alert status" },
    "free_heap": { "type": "integer", "description": "Instantaneous free DRAM in bytes" },
    "min_free_heap": { "type": "integer", "description": "Lowest historical free DRAM in bytes" },
    "reset_reason": { "type": "integer", "description": "ESP-IDF reset reason enum code" },
    "co2": { "type": "number", "description": "CO2 concentration in ppm" },
    "temp": { "type": "number", "description": "Calibrated temperature in degrees Celsius" },
    "hum": { "type": "number", "description": "Psychrometrically compensated relative humidity in %" },
    "batt_pct": { "type": "number", "description": "Battery charge percentage (0-100)" },
    "usb": { "type": "boolean", "description": "True if external USB-C power is connected" },
    "ip": { "type": "string", "description": "Current Wi-Fi Station IPv4 address" },
    "gd32_version": { "type": "string", "description": "Running GD32 coprocessor firmware version" },
    "alarm_enabled": { "type": "boolean", "description": "Morning alarm enabled toggle" },
    "silence_enabled": { "type": "boolean", "description": "09:00 Minute of Silence tribute toggle" },
    "led_auto": { "type": "boolean", "description": "Automatic CO2 LED indication toggle" },
    "brightness": { "type": "number", "description": "ST7789 display backlight duty (0-100%)" },
    "temp_trim": { "type": "number", "description": "Manual temperature calibration offset (-10.0 to +10.0 °C)" },
    "co2_yellow": { "type": "number", "description": "CO2 Yellow threshold in ppm" },
    "co2_red": { "type": "number", "description": "CO2 Red threshold in ppm" },
    "alarm_time": { "type": "string", "description": "Configured alarm time in HH:MM format" },
    "alarm_days": { 
      "type": "array", 
      "items": { "type": "integer", "minimum": 1, "maximum": 7 },
      "description": "Active days of the week for alarm (1=Monday .. 7=Sunday)" 
    }
  }
}
```

#### 2.1.3 Sample Response (200 OK)
```json
{
  "version": "1.0.0",
  "new_version": "",
  "region": 31,
  "lat": 50.4500,
  "lon": 30.5241,
  "city": "Київ",
  "alert_active": false,
  "free_heap": 128448,
  "min_free_heap": 98304,
  "reset_reason": 1,
  "co2": 645.0,
  "temp": 22.4,
  "hum": 48.2,
  "batt_pct": 100.0,
  "usb": true,
  "ip": "192.168.0.78",
  "gd32_version": "v1.3.0",
  "alarm_enabled": false,
  "silence_enabled": true,
  "led_auto": true,
  "brightness": 100,
  "temp_trim": 0.0,
  "co2_yellow": 1000,
  "co2_red": 1500,
  "alarm_time": "07:30",
  "alarm_days": [1, 2, 3, 4, 5, 6, 7]
}
```

---

### 2.2 POST `/api/settings`
Updates persistent device settings, calibration offsets, alert region, and user preferences. Supports partial patch semantics.

#### 2.2.1 HTTP Request
- **Method:** `POST`
- **Path:** `/api/settings`
- **Headers:** `Content-Type: application/json`

#### 2.2.2 Patch Semantics & Thread Safety
- **Partial Patching:** Any parameter not included in the JSON payload retains its current state in memory and NVS.
- **AsyncTCP Thread Safety via `Component::defer`:** HTTP requests are parsed inside the asynchronous network thread. Direct mutation of ESPHome entities from this thread would trigger race conditions with the main LVGL rendering loop. Therefore, `HtramWebComponent` captures parsed parameters by value and dispatches execution to the main thread using `this->defer([...])`:
  ```cpp
  parent->defer_action([parent, reg, lat, lon, city, ...]() {
    // Safely executes on the core ESPHome component loop
    if (geo_changed) {
      parent->set_region(reg);
      parent->save_preferences();
      parent->trigger_save_settings(reg, lat, lon, city);
    }
    // Safely updates switch, number, and time entities
  });
  ```

#### 2.2.3 Parameter Reference Table
| Field | Type | Description | Valid Range / Format | Default |
| :--- | :--- | :--- | :--- | :--- |
| `region` | integer | JAAM settlement / rayon ID | 1 .. 1400 | `31` (Kyiv) |
| `lat` | float | Latitude for Open-Meteo forecast | -90.0 .. 90.0 | `50.45` |
| `lon` | float | Longitude for Open-Meteo forecast | -180.0 .. 180.0 | `30.52` |
| `city` | string | Display city name | UTF-8, max 63 chars | `"Київ"` |
| `alarm_enabled`| boolean | Master enable for daily alarm | `true` / `false` | `false` |
| `alarm_time` | string | Alarm trigger time | `"HH:MM"` (24-hour) | `"07:30"` |
| `alarm_days` | array of int / bitmask | Active days of the week (1=Mon..7=Sun) | `[1..7]` or bitmask (0..127) | `[1, 2, 3, 4, 5, 6, 7]` |
| `silence_enabled`| boolean | Enable 09:00 Minute of Silence tribute | `true` / `false` | `true` |
| `led_auto` | boolean | Ambient CO2 LED auto indication | `true` / `false` | `true` |
| `brightness` | number | Display backlight percentage | 5 .. 100 (%) | `100` |
| `temp_trim` | number | Manual temperature calibration offset | -10.0 .. +10.0 (°C) | `0.0` |
| `co2_yellow` | number | Ambient CO2 yellow threshold | 600 .. 2500 (ppm) | `1000` |
| `co2_red` | number | Ambient CO2 red threshold | 800 .. 5000 (ppm) | `1500` |

#### 2.2.4 Sample Payloads & Responses
**Example Request (Updating Alert Location & Backlight):**
```json
{
  "region": 75,
  "lat": 50.5449,
  "lon": 29.8987,
  "city": "Буча",
  "brightness": 85
}
```

**Success Response (200 OK):**
```json
{
  "result": "ok"
}
```

**Malformed Payload Response (400 Bad Request):**
```json
{
  "result": "error",
  "reason": "invalid json"
}
```

---

### 2.3 POST `/api/check_update`
Checks for newer firmware releases hosted on GitHub Releases or internal OTA mirrors.

#### 2.3.1 HTTP Request
- **Method:** `POST`
- **Path:** `/api/check_update`
- **Payload:** None (empty body)

#### 2.3.2 Response Payload (200 OK)
```json
{
  "result": "ok",
  "current_version": "1.0.0",
  "new_version": "v1.1.0"
}
```
*(If no newer release exists, `"new_version"` returns `""`).*

---

### 2.4 POST `/api/ota_update`
Initiates 1-click autonomous over-the-air firmware update. The device downloads the compiled binary over HTTP from GitHub Releases, performs MD5 verification, stages the flash partition, and triggers a safe restart.

#### 2.4.1 HTTP Request
- **Method:** `POST`
- **Path:** `/api/ota_update`

#### 2.4.2 Response Payload (200 OK)
```json
{
  "result": "updating"
}
```

---

### 2.5 POST `/api/reboot`
Performs a safe, graceful restart of the ESP32 system.

#### 2.5.1 HTTP Request
- **Method:** `POST`
- **Path:** `/api/reboot`

#### 2.5.2 Execution Flow
The handler sends HTTP 200 immediately to ensure the client receives network confirmation before the socket closes. It then dispatches a deferred task calling `App.safe_reboot()` on the subsequent loop iteration:
```cpp
request->send(200, "application/json", "{\"result\":\"rebooting\"}");
this->parent_->defer_action([]() { App.safe_reboot(); });
```

#### 2.5.3 Response Payload (200 OK)
```json
{
  "result": "rebooting"
}
```

---

### 2.6 Standard HTTP Status Codes Summary
| Status Code | Description | Condition |
| :--- | :--- | :--- |
| **200 OK** | Success | Request was parsed, validated, and applied successfully. |
| **400 Bad Request** | Client Error | Malformed JSON body or unparseable payload structure. |
| **404 Not Found** | Endpoint Not Found | Unknown URL or unsupported HTTP request method. |
| **500 Internal Error** | Server Error | Flash memory write failure or internal hardware exception. |

---

## 3. NVS Non-Volatile Storage Schema

To ensure that geographic coordinates, alert region bindings, and user configurations survive firmware updates, power cycles, and Wi-Fi resets, `htram_web` persists its state into the ESP-IDF Non-Volatile Storage (NVS) partition using ESPHome's `global_preferences` subsystem.

### 3.1 Preference Key Hash
The NVS storage entry is indexed using an 32-bit FNV-1 hash of the unique identifier string:
$$\text{Key Hash} = \text{fnv1\_hash}(\text{"htram\_web\_geo\_v1"}) = \text{0x291A25C9}$$

### 3.2 C++ Struct Definition (`HtramWebSettings`)
```cpp
struct HtramWebSettings {
  uint32_t magic;      // Magic verification constant (0x48545232)
  int region;          // JAAM Region / District ID (e.g. 31)
  float lat;           // Geographical Latitude (e.g. 50.45f)
  float lon;           // Geographical Longitude (e.g. 30.52f)
  char city[64];       // Null-terminated UTF-8 settlement string
};
```

### 3.3 Memory Layout & Alignment
The structure is engineered for natural 4-byte word alignment without compiler packing overhead:

```
Offset (Bytes)   Field Name      Type         Size (Bytes)   Hex Representation
+00              magic           uint32_t     4              0x48545232 ("HTR2")
+04              region          int32_t      4              0x0000001F (31)
+08              lat             float        4              IEEE-754 32-bit float
+12              lon             float        4              IEEE-754 32-bit float
+16..+79         city            char[64]     64             UTF-8 string (zero-padded)
---------------------------------------------------------------------------------
Total Size:      80 Bytes (0 Padding / Hole Bytes)
```

### 3.4 Verification & Migration Mechanics
1. **Magic Verification:** On boot during `load_preferences()`, the firmware verifies `s.magic == 0x48545232` (`'H' 'T' 'R' '2'`). If uninitialized or corrupted, the struct is populated with default factory coordinates: Kyiv (region 31, 50.45° N, 30.52° E).
2. **Legacy Index Migration:** If upgrading from legacy firmware where regions were indexed 0..26, the component maps indices via `LEGACY_MAP[27]` to modern JAAM region IDs:
   ```cpp
   static const uint16_t LEGACY_MAP[27] = {
     7266, 11, 13, 21, 27, 8, 5, 10, 14, 25, 20, 22, 16, 28, 12, 23, 18, 17, 9, 19, 24, 15, 4, 3, 26, 31, 31
   };
   ```
3. **Atomic Flash Sync:** Mutations call `global_preferences->sync()` to flush pending dirty pages to SPI Flash immediately.

---

## 4. Client-Side Geocoding & District Hierarchy

The web interface integrates client-side settlement search and district resolution directly in JavaScript, eliminating backend geocoding computation.

```
                           [User Enters Query in Search Box]
                                           │
                                           ▼
                      [Tier 1: Photon API (Komoot OSM Ukraine)]
                                           │
                        Found? ──► [YES] ──┴──► [Extract Coordinates & Admin]
                           │
                          [NO]
                           │
                           ▼
                      [Tier 2 Fallback: Nominatim OpenStreetMap]
                                           │
                        Found? ──► [YES] ──┴──► [Extract Coordinates & Admin]
                           │
                          [NO]
                           │
                           ▼
                      [Tier 3 Fallback: Open-Meteo Geocoding]
                                           │
                                           ▼
                       [detectJaamDistrict Algorithm Execution]
                                           │
                ┌──────────────────────────┼──────────────────────────┐
                ▼                          ▼                          ▼
     [Priority 1: Stem Match]    [Priority 2: Haversine]    [Priority 3: Oblast]
     (Match Rayon / City Name)    (Closest Rayon Center)     (Parent State Match)
                │                          │                          │
                └──────────────────────────┼──────────────────────────┘
                                           │
                                           ▼
                       [Resolved JAAM Region ID (e.g. 75 Bucha)]
                       [Auto-Save to Device via POST /api/settings]
```

### 4.1 Three-Tier Geocoding Waterfall
1. **Primary Provider (Photon API):** Uses `https://photon.komoot.io/api/?q={query}&limit=10`. Prioritized for exceptional coverage of Ukrainian villages, settlements, and territorial communities (ТГ).
2. **Secondary Provider (Nominatim OSM):** Queries `https://nominatim.openstreetmap.org/search?q={query}&format=json&countrycodes=ua&accept-language=uk&limit=6&addressdetails=1`. Provides granular administrative hierarchy (`county`, `district`, `state`).
3. **Tertiary Provider (Open-Meteo Geocoding):** Queries `https://geocoding-api.open-meteo.com/v1/search?name={query}&count=6&language=uk&format=json` as an autonomous fallback.

### 4.2 District Resolution Algorithm (`detectJaamDistrict`)
The JavaScript function maps geocoded places to the closest authoritative JAAM administrative rayon:
- **Rule 1 (Kyiv Special Case):** If the settlement matches `"Київ"`, `"Kyiv"`, or `"Kiev"`, it resolves immediately to ID `31` (`м. Київ`).
- **Rule 2 (Rayon Name Stem Matching):** Normalizes the administrative county string (`admin2`), strips suffixes (`" район"`, `"м. "`, `" + ТГ"`), extracts the stem, and matches against the 140+ options in the `<select id="sel-region">` catalog.
- **Rule 3 (Haversine Distance Minimization):** If no textual match occurs, calculates Euclidean/Haversine distance between the place's GPS coordinates and the coordinates of all known district administrative centers:
  $$\text{dist}^2 = (\text{lat}_{\text{target}} - \text{lat}_{\text{district}})^2 + [(\text{lon}_{\text{target}} - \text{lon}_{\text{district}}) \cdot \cos(\text{lat}_{\text{target}})]^2$$
  The closest district center is selected.
- **Rule 4 (Oblast-Level Fallback):** If outside known rayon coordinates, maps to the parent Oblast (`admin1`).
- **Default:** ID `31`.

### 4.3 IP-Based One-Click Auto-Detection
The interface includes a dedicated button (`📍 Визначити локацію автоматично (по IP)`). It contacts `https://ipapi.co/json/` (with fallback to `https://get.geojs.io/v1/ip/geo.json`) to discover the user's city and ISP coordinates, automatically runs the district detection waterfall, and posts the resulting configuration to the device.

---

## 5. Two-Way State Synchronization

### 5.1 Real-Time 4-Second Polling Loop
To reflect external environment changes (sensor telemetry, air raid alert triggers, Home Assistant overrides) without persistent WebSocket overhead on the web server, the browser runs an autonomous polling interval:
```javascript
window.addEventListener('DOMContentLoaded', () => {
  loadInitialSettings();
  setInterval(fetchStatus, 4000); // 4-second polling loop
});
```

During each poll:
1. `GET /api/status` is executed.
2. CO2, Temperature, Humidity, Battery, and USB power displays update.
3. If CO2 values change, font color shifts adaptively:
   - `< co2_yellow`: Green (`#22c55e`).
   - `co2_yellow .. co2_red`: Yellow (`#f59e0b`).
   - `> co2_red`: Red (`#ef4444`).
4. If `alert_active` is true, an emergency alert banner pulses red across the top of the interface.

### 5.2 Debounced Auto-Save & Visual State Badge
All form inputs on the web dashboard feature instant auto-save:
- **Sliders (Brightness):** Debounced by 100 ms to prevent flooding the ESP32 while the user drags the touch slider.
- **City Search:** Debounced by 300 ms.
- **Toggles (Switches, Numbers):** Execute immediate background `POST /api/settings`.

#### 5.2.1 Visual Status Badge Lifecycle
A dedicated badge (`#save-status`) in the header provides instant feedback:
```
[User Interacts] ──► [Saving: "⟳ Збереження..." (#f59e0b)]
                            │
            ┌───────────────┴───────────────┐
            ▼                               ▼
   [HTTP 200 Received]             [Network / HTTP Error]
            │                               │
   [Saved: "✓ Збережено" (#22c55e)] [Error: "⚠ Помилка" (#ef4444)]
            │                               │
       (After 2s)                           ▼
            │                     [Toast Error Displayed]
            ▼
   [Idle: "● Збережено" (#22c55e)]
```

---

## 6. Document Metadata & Sign-off

- **Author:** Teamwork Systems Engineering (M5 Documentation Worker)
- **Approved by:** Project Technical Lead & Antigravity Orchestrator
- **Applicable Git Branches:** `main`, `feature/standalone-first`
- **Related Specifications:**
  - `docs/PRODUCT_SPEC.md` (Product Architecture, Journeys, FSM)
  - `docs/RELEASE_LIFECYCLE.md` (Release Policies, 1-Click OTA, Bench Recovery)
