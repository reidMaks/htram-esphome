#ifndef SPI_FLASH_H
#define SPI_FLASH_H

#include <stdint.h>

/* Winbond W25Q32 JEDEC constants */
#define JEDEC_MFG_WINBOND    0xEF
#define JEDEC_TYPE_W25Q      0x40
#define JEDEC_CAP_W25Q32     0x16 /* 32 Mbit = 4 MByte */

typedef struct {
    uint8_t mfg_id;      /* Manufacturer ID (0xEF) */
    uint8_t memory_type; /* Memory Type (0x40) */
    uint8_t capacity;    /* Capacity (0x16 for 4MB) */
    uint8_t status_reg1; /* Status Register 1 */
    uint8_t is_detected; /* 1 if valid JEDEC ID read, 0 otherwise */
} spi_flash_info_t;

void spi_flash_init(void);
int spi_flash_read_jedec_id(uint8_t *mfg, uint8_t *type, uint8_t *capacity);
uint8_t spi_flash_read_status(void);
const spi_flash_info_t *spi_flash_get_info(void);

#endif /* SPI_FLASH_H */
