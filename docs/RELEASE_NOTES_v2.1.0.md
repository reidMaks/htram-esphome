# HTRAM Custom Firmware Release Notes — v2.1.0

**Release Tag:** `v2.1.0`  
**Architecture Milestone:** Standalone-First Autonomous Appliance, Captive Portal Provisioning & 1-Click OTA  
**Supported Devices:** Honeywell Transmission Risk Air Monitor (Storm Shadow Main Board REV3)  
**Target MCUs:** ESP32-WROOM-32E (4MB Flash) & GD32F150G8U6 (64KB Flash, 8KB SRAM)

---

## 1. Executive Summary

Version **v2.1.0** transforms HTRAM from an IoT peripheral into a completely autonomous, standalone smart appliance that functions out of the box without requiring Home Assistant, external MQTT brokers, or cloud accounts:

1. **Captive Portal & SoftAP Wi-Fi Provisioning**:
   - Automatic fallback AP (`HTRAM Setup`) with QR Code and readable text credentials on display.
   - Symmetrical physical dismiss & entry gestures (4-click / 5-click setup entry, double-click dismiss).
   - Fast fallback trigger (`ap_timeout: 15s`) and 20ms instant screen transition upon network disconnection.
   - Active Wi-Fi network scanning with automated retry polling and SSID deduplication by RSSI.

2. **Autonomous Responsive Web Dashboard (Port 80)**:
   - Full embedded web interface served directly from ESP32 PROGMEM (`web_page.h`, 0 external CDN dependencies).
   - Dynamic configuration: Wi-Fi credentials, location/city/coordinates, morning alarm with day-of-week selection, Minute of Silence (09:00 with Tryzub), screen brightness, and CO2 auto-LED thresholds.
   - 1-Click OTA updates directly from GitHub Releases with real-time version discovery.

3. **Autonomous Modals & Clock Faces**:
   - **Open-Meteo Weather Screen**: 6-hour segmented forecast modal with day/night weather glyphs.
   - **Kitchen Countdown Timer**: Preset rotation (3m, 5m, 10m, 15m), active countdown, and piezo alarm.
   - **Air Raid Alert Fusion**: JAAM WebSocket integration with automatic preemption and audio alert.
   - **Bezel Orbiting Seconds Dot**: High-contrast seconds indicator smoothly navigating display perimeter.

---

## 2. Key Changes & Enhancements

### 2.1 Connectivity & Network Resilience
- **Fast SoftAP Activation**: `ap_timeout` reduced from 90s to 15s in `htram-core.yaml`.
- **Reactive UI Switching**: Core UI interval detects captive portal activation within 20ms, rendering the QR card immediately.
- **Background Scan Retention**: Wi-Fi component preserves scan cache across reconnect attempts via `wifi.request_wifi_scan_results()`.

### 2.2 Web Management & 1-Click OTA
- **Real-Time Release Discovery**: Web dashboard queries GitHub Releases API on page load and on user demand (`/api/check_update`), displaying an update banner whenever a newer release is detected.
- **Streamed OTA Flashing**: Initiates single-click streamed download (`htram-standalone.bin`) with on-the-fly MD5 validation directly into inactive partition `ota_1`.
- **Hardware Safe Rollback**: Protected by ESP-IDF 2-stage bootloader with automatic rollback if boot fails or trips watchdog.

---

## 3. Release Artifacts & Checksums

| Artifact | Target Component | Description |
|---|---|---|
| `htram-standalone.bin` | ESP32-WROOM-32E | Full standalone firmware application |
| `htram-standalone.bin.md5` | Verification | MD5 checksum for OTA streaming verification |
| `htram-standalone.bin.sha256` | Verification | SHA256 checksum for binary integrity |
| `gd32_firmware-v1.3.0.bin` | GD32F150G8U6 | RLE-accelerated coprocessor firmware |
| `flash_assets.bin` | W25Q32 SPI Flash | UI graphic assets and weather glyphs container |

---

## 4. Upgrade Instructions

### Method 1: Web Interface (Recommended)
1. Open the device web page in your browser (`http://htram.local` or `http://<device-ip>/`).
2. When the update banner appears (**«Доступна нова версія: v2.1.0»**), click **«Оновити в 1 клік»**.
3. Wait 1–2 minutes while the device downloads, stages, and reboots into the new release.

### Method 2: Fleet Makefile
```bash
# Update specific device:
make ota-esp DEVICE=office

# Update entire fleet:
make update-all
```
