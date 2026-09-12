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

/* SPI Flash Memory Map */
#define SPI_FLASH_SUPERBLOCK_ADDR    0x00000000UL /* Sector 0 (4 KB) */
#define SPI_FLASH_SLOT_A_ADDR        0x00010000UL /* Block 1: Golden Slot (64 KB) */
#define SPI_FLASH_SLOT_B_ADDR        0x00020000UL /* Block 2: Rollback Slot (64 KB) */
#define SPI_FLASH_SLOT_STAGING_ADDR  0x00030000UL /* Block 3: Staging Slot (64 KB) */
#define SPI_FLASH_ASSETS_ADDR        0x00040000UL /* Blocks 4..63: Graphic Assets */

#define SPI_FLASH_SUPERBLOCK_MAGIC   0x534C464D41525448ULL /* "HTRAMFLS" in LE */
#define SPI_FLASH_LAYOUT_VERSION     1

#define BOOT_STATUS_CONFIRMED        0x01
#define BOOT_STATUS_TESTING          0x02

typedef struct __attribute__((packed)) {
    uint64_t magic;              /* "HTRAMFLS" (0x534C464D41525448ULL) */
    uint16_t layout_version;     /* 1 */
    uint8_t  boot_status;        /* 0x01=CONFIRMED, 0x02=TESTING */
    uint8_t  boot_attempts;      /* Number of failed boot attempts */
    uint8_t  active_fw_slot;     /* 0=Slot A, 1=Slot B, 2=Staging */
    uint8_t  reserved[3];
    uint32_t fw_slot_a_size;
    uint32_t fw_slot_a_crc32;
    uint32_t fw_slot_b_size;
    uint32_t fw_slot_b_crc32;
    uint32_t staging_size;
    uint32_t staging_crc32;
    uint32_t superblock_crc32;   /* IEEE CRC32 of preceding 40 bytes */
} spi_flash_superblock_t;

/* Firmware backup, restore and boot guard operations */
uint32_t spi_flash_get_fw_size(void);
int spi_flash_backup_firmware(uint8_t slot_idx, uint32_t *out_crc32);
int spi_flash_read_superblock(spi_flash_superblock_t *sb);
int spi_flash_write_superblock(const spi_flash_superblock_t *sb);
int spi_flash_confirm_boot(void);
void spi_flash_boot_guard_check(void);

#endif /* SPI_FLASH_H */
