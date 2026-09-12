#ifndef SPI_FLASH_H
#define SPI_FLASH_H

#include <stdint.h>
#include <stddef.h>

/* Winbond W25Q32 JEDEC constants */
#define JEDEC_MFG_WINBOND       0xEF
#define JEDEC_TYPE_W25Q         0x40
#define JEDEC_CAP_W25Q32        0x16 /* 32 Mbit = 4 MByte */

/* Flash Geometry */
#define SPI_FLASH_TOTAL_SIZE    0x00400000UL /* 4 MB */
#define SPI_FLASH_SECTOR_SIZE   4096UL       /* 4 KB */
#define SPI_FLASH_BLOCK_SIZE    65536UL      /* 64 KB */
#define SPI_FLASH_PAGE_SIZE     256UL        /* 256 bytes */

/* W25Q32 SPI Opcodes */
#define CMD_W25Q_PAGE_PROGRAM   0x02
#define CMD_W25Q_READ_DATA      0x03
#define CMD_W25Q_WRITE_DISABLE  0x04
#define CMD_W25Q_READ_STATUS1   0x05
#define CMD_W25Q_WRITE_ENABLE   0x06
#define CMD_W25Q_SECTOR_ERASE   0x20
#define CMD_W25Q_BLOCK_ERASE    0xD8
#define CMD_W25Q_JEDEC_ID       0x9F

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

/* Flash write & erase operations */
void spi_flash_write_enable(void);
void spi_flash_write_disable(void);
int spi_flash_wait_busy(uint32_t timeout_ms);
int spi_flash_sector_erase_4k(uint32_t addr);
int spi_flash_block_erase_64k(uint32_t addr);
int spi_flash_page_program(uint32_t addr, const uint8_t *data, size_t len);
int spi_flash_read_data(uint32_t addr, uint8_t *data, size_t len);
int spi_flash_verify_crc32(uint32_t addr, uint32_t len, uint32_t expected_crc32);

#endif /* SPI_FLASH_H */
