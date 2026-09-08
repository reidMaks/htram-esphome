#ifndef SENSORS_H
#define SENSORS_H

#include <stdint.h>

void sensors_init(void);
/* SHT30 in two phases. The single-shot conversion needs ~40 ms, which is
 * longer than the RX ring can absorb at 921600 (22 ms), so the wait belongs to
 * the main loop rather than to a delay_ms() inside the driver.
 * SHT30_CONVERSION_MS after _start(), call _fetch(). */
#define SHT30_CONVERSION_MS 40
int sensors_sht30_start(void);
/* usb_present drives the self-heating model: external power costs this board
 * about 5 C more than battery, and the offset relaxes toward the new target
 * over ~8 minutes rather than stepping. Pass the value read in the same cycle. */
int sensors_sht30_fetch(int16_t *temp_001c, uint16_t *hum_001pct,
                        uint8_t usb_present);
int sensors_poll_co2(uint16_t *co2_ppm, uint8_t *warmup_flag);

#endif /* SENSORS_H */
