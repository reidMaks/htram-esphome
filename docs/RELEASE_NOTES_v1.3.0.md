# HTRAM Custom Firmware Release Notes — v1.3.0

**Release Tag:** `v1.3.0`  
**Architecture Milestone:** TGA 16-Bit RGB565 RLE Stream Compression & High-Performance Display Acceleration  
**Supported Devices:** Honeywell Transmission Risk Air Monitor (Storm Shadow Main Board REV3)

---

## 1. Summary of Changes

Version **v1.3.0** introduces streaming hardware-accelerated **TGA 2.0 16-bit RGB565 Run-Length Encoding (RLE)** across the inter-chip UART link (921,600 baud), solving the display refresh bottleneck for all dynamic UI rendering:

1. **TGA 16-Bit RGB565 RLE Protocol (`CMD_TYPE_DRAW_RECT_RLE` / `0x16`)**:
   - PackBits-style run-length encoding:
     - **Run packet** (`ctrl & 0x80`): `(ctrl & 0x7F) + 1` repeated pixels (1..128) encoded as 1 control byte + 2 bytes RGB565 LE.
     - **Raw packet** (`!(ctrl & 0x80)`): `(ctrl & 0x7F) + 1` distinct pixels (1..128) encoded as 1 control byte + $N \times 2$ bytes RGB565 LE.
   - End-to-end CCITT-16 CRC packet verification.

2. **Zero-SRAM Streaming Decompressor on GD32**:
   - The GD32 decompressor operates strictly in-flight within `STATE_PIXELS_RLE`, requiring only **4 bytes of RAM state** (run count, raw count, hi/lo byte flags).
   - Pixels are pumped directly into the ST7789 display controller's GRAM via `display_send_pixel_stream()` as UART bytes arrive in the circular RX buffer.
   - Zero heap allocation and no full-frame SRAM buffering needed on GD32 (which only has 8 KB SRAM total).

3. **Dynamic Chunker & RLE Compression in ESPHome**:
   - `HtramGd32Display::draw_pixels_at` now encodes pixel rows using `encode_tga_rle_rgb565` and partitions output into chunks $\le 512$ bytes to strictly respect GD32 UART RX ring limits.
   - For predominantly black areas (e.g. screen transitions and dark background areas), a 240×30 strip (14,400 raw bytes) collapses into a single 171-byte packet (**84× compression**).

4. **Performance Gains & Visual Fluidity**:
   - **Full-screen invalidation / modal transition wire time**: Drops from **~1.25 seconds to ~15 milliseconds**.
   - **Sweep elimination**: Completely eliminates visible downward line-by-line sweeping when toggling modal screens (Weather, Timer, Minute of Silence, Alert).
   - **Ghosting prevention**: Instant background flush completely prevents digit ghosting under transparent containers.

---

## 2. Benchmark Comparison

| Scenario | Uncompressed `0x10` | Compressed RLE `0x16` | Improvement |
|---|---|---|---|
| Solid black fill (128 pixels) | 256 bytes | **3 bytes** | **85.3×** smaller |
| Single 240×30 strip (7200 px) | 14,400 bytes | **171 bytes** | **84.2×** smaller |
| Full 240×240 frame clear | 115,200 bytes | **~1,368 bytes** | **84.2×** smaller |
| Full frame UART transit latency | ~1,250 ms | **~15 ms** | **83× faster** |
| GD32 RAM overhead | 0 bytes | **4 bytes** | Negligible |

---

## 3. Backwards Compatibility & Safe Rolling Deployments

### Rolling Deployment Safety
- ESPHome checks `supports_rle()` (`raw_fw_ver_ >= 0x0130`).
- If an updated ESP32 communicates with an older GD32 running v1.2.0, it automatically falls back to uncompressed `CMD_TYPE_DRAW_RECT` (`0x10`).
- If GD32 is updated to v1.3.0 before ESP32, GD32 continues supporting `0x10` seamlessly.

---

## 4. Upgrade Verification

To verify that devices in the fleet are operating with v1.3.0:

```bash
make status-all
```

Expected output for each node:
- `GD32 Firmware: 1.3.0 gd47961e2`
- `GD32 SPI Flash: W25Q32 4MB [EF 40 16, S=0x00]`
- `ESPHome Version: 2026.8.2`
