#include "spi_flash.h"
#include "gd32f150.h"
#include "periph.h"
#include "protocol.h"
#include "flasher.h"

static spi_flash_info_t g_flash_info;

/*
 * Bit-bang SPI transfer byte (SPI Mode 0: CPOL=0, CPHA=0)
 * PA4 = CS (active LOW)
 * PA5 = SCK (idles LOW, samples on rising edge)
 * PA6 = MISO (input with pull-up)
 * PA7 = MOSI (output push-pull)
 */
static uint8_t spi_transfer_byte(uint8_t tx)
{
    uint8_t rx = 0;
    for (int i = 7; i >= 0; i--) {
        /* Setup MOSI while SCK is LOW */
        if (tx & (1 << i)) {
            gpio_set(GPIOA_BASE, 7, 1);
        } else {
            gpio_set(GPIOA_BASE, 7, 0);
        }
        delay_us(1);

        /* Rising edge of SCK */
        gpio_set(GPIOA_BASE, 5, 1);
        delay_us(1);

        /* Sample MISO */
        if (gpio_get(GPIOA_BASE, 6)) {
            rx |= (1 << i);
        }

        /* Falling edge of SCK */
        gpio_set(GPIOA_BASE, 5, 0);
        delay_us(1);
    }
    return rx;
}

int spi_flash_read_jedec_id(uint8_t *mfg, uint8_t *type, uint8_t *capacity)
{
    /* CS LOW */
    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);

    /* Command 0x9F: Read JEDEC ID */
    spi_transfer_byte(CMD_W25Q_JEDEC_ID);
    uint8_t m = spi_transfer_byte(0xFF);
    uint8_t t = spi_transfer_byte(0xFF);
    uint8_t c = spi_transfer_byte(0xFF);

    /* CS HIGH (deselect) */
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);

    if (mfg) *mfg = m;
    if (type) *type = t;
    if (capacity) *capacity = c;

    /* Bus floating or shorted check */
    if ((m == 0xFF && t == 0xFF && c == 0xFF) || (m == 0x00 && t == 0x00 && c == 0x00)) {
        return -1;
    }
    return 0;
}

uint8_t spi_flash_read_status(void)
{
    /* CS LOW */
    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);

    /* Command 0x05: Read Status Register 1 */
    spi_transfer_byte(CMD_W25Q_READ_STATUS1);
    uint8_t status = spi_transfer_byte(0xFF);

    /* CS HIGH */
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);

    return status;
}

void spi_flash_write_enable(void)
{
    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);
    spi_transfer_byte(CMD_W25Q_WRITE_ENABLE);
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);
}

void spi_flash_write_disable(void)
{
    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);
    spi_transfer_byte(CMD_W25Q_WRITE_DISABLE);
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);
}

int spi_flash_wait_busy(uint32_t timeout_ms)
{
    uint32_t start = periph_millis();
    uint32_t loops = 0;
    while (spi_flash_read_status() & 0x01) {
        watchdog_kick();
        loops++;
        if ((periph_millis() - start > timeout_ms) || (loops > timeout_ms * 1000)) {
            return -1;
        }
    }
    return 0;
}

int spi_flash_sector_erase_4k(uint32_t addr)
{
    if (addr >= SPI_FLASH_TOTAL_SIZE || (addr & 0xFFF) != 0) {
        return -1;
    }
    spi_flash_write_enable();

    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);
    spi_transfer_byte(CMD_W25Q_SECTOR_ERASE);
    spi_transfer_byte((uint8_t)((addr >> 16) & 0xFF));
    spi_transfer_byte((uint8_t)((addr >> 8) & 0xFF));
    spi_transfer_byte((uint8_t)(addr & 0xFF));
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);

    return spi_flash_wait_busy(500);
}

int spi_flash_block_erase_64k(uint32_t addr)
{
    if (addr >= SPI_FLASH_TOTAL_SIZE || (addr & 0xFFFF) != 0) {
        return -1;
    }
    spi_flash_write_enable();

    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);
    spi_transfer_byte(CMD_W25Q_BLOCK_ERASE);
    spi_transfer_byte((uint8_t)((addr >> 16) & 0xFF));
    spi_transfer_byte((uint8_t)((addr >> 8) & 0xFF));
    spi_transfer_byte((uint8_t)(addr & 0xFF));
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);

    return spi_flash_wait_busy(2000);
}

int spi_flash_page_program(uint32_t addr, const uint8_t *data, size_t len)
{
    if (!data || len == 0 || len > SPI_FLASH_PAGE_SIZE) {
        return -1;
    }
    if (addr >= SPI_FLASH_TOTAL_SIZE || ((addr & 0xFF) + len > SPI_FLASH_PAGE_SIZE)) {
        return -1;
    }
    spi_flash_write_enable();

    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);
    spi_transfer_byte(CMD_W25Q_PAGE_PROGRAM);
    spi_transfer_byte((uint8_t)((addr >> 16) & 0xFF));
    spi_transfer_byte((uint8_t)((addr >> 8) & 0xFF));
    spi_transfer_byte((uint8_t)(addr & 0xFF));

    for (size_t i = 0; i < len; i++) {
        spi_transfer_byte(data[i]);
    }
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);

    return spi_flash_wait_busy(30);
}

int spi_flash_read_data(uint32_t addr, uint8_t *data, size_t len)
{
    if (!data && len > 0) {
        return -1;
    }
    if (addr >= SPI_FLASH_TOTAL_SIZE || addr + len > SPI_FLASH_TOTAL_SIZE) {
        return -1;
    }
    if (len == 0) {
        return 0;
    }

    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);
    spi_transfer_byte(CMD_W25Q_READ_DATA);
    spi_transfer_byte((uint8_t)((addr >> 16) & 0xFF));
    spi_transfer_byte((uint8_t)((addr >> 8) & 0xFF));
    spi_transfer_byte((uint8_t)(addr & 0xFF));

    for (size_t i = 0; i < len; i++) {
        data[i] = spi_transfer_byte(0xFF);
        if ((i & 0x3FF) == 0) {
            watchdog_kick();
        }
    }
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);

    return 0;
}

int spi_flash_verify_crc32(uint32_t addr, uint32_t len, uint32_t expected_crc32)
{
    if (addr >= SPI_FLASH_TOTAL_SIZE || addr + len > SPI_FLASH_TOTAL_SIZE) {
        return -1;
    }
    if (len == 0) {
        return (expected_crc32 == 0) ? 0 : -2;
    }

    gpio_set(GPIOA_BASE, 4, 0);
    delay_us(2);
    spi_transfer_byte(CMD_W25Q_READ_DATA);
    spi_transfer_byte((uint8_t)((addr >> 16) & 0xFF));
    spi_transfer_byte((uint8_t)((addr >> 8) & 0xFF));
    spi_transfer_byte((uint8_t)(addr & 0xFF));

    uint32_t crc = 0xFFFFFFFFUL;
    for (uint32_t i = 0; i < len; i++) {
        uint8_t b = spi_transfer_byte(0xFF);
        crc = crc32_ieee_update(crc, b);
        if ((i & 0x3FF) == 0) {
            watchdog_kick();
        }
    }
    gpio_set(GPIOA_BASE, 4, 1);
    delay_us(2);

    crc = ~crc;
    return (crc == expected_crc32) ? 0 : -2;
}

void spi_flash_init(void)
{
    g_flash_info.mfg_id = 0;
    g_flash_info.memory_type = 0;
    g_flash_info.capacity = 0;
    g_flash_info.status_reg1 = 0;
    g_flash_info.is_detected = 0;

    /* 1. Ensure GPIOA clock is enabled */
    RCU_AHBEN |= RCU_AHBEN_PAEN;

    /* 2. CS (PA4) MUST BE DRIVEN HIGH BEFORE CONFIGURING AS OUTPUT
     * This guarantees the Winbond chip remains in tri-state/sleep during init
     * and prevents any bus contention on the 3.3V power rail. */
    gpio_set(GPIOA_BASE, 4, 1);
    gpio_cfg_out_pp(GPIOA_BASE, 4);
    gpio_set(GPIOA_BASE, 4, 1);

    /* 3. SCK (PA5) Output Push-Pull, idles LOW */
    gpio_set(GPIOA_BASE, 5, 0);
    gpio_cfg_out_pp(GPIOA_BASE, 5);

    /* 4. MOSI (PA7) Output Push-Pull, idles LOW */
    gpio_set(GPIOA_BASE, 7, 0);
    gpio_cfg_out_pp(GPIOA_BASE, 7);

    /* 5. MISO (PA6) STRICTLY INPUT WITH PULL-UP. NEVER CONFIGURE AS OUTPUT! */
    gpio_cfg_in(GPIOA_BASE, 6, 1);

    /* Allow rail and pins to settle */
    delay_ms(2);

    /* 6. Probe JEDEC ID */
    uint8_t mfg = 0, type = 0, cap = 0;
    if (spi_flash_read_jedec_id(&mfg, &type, &cap) == 0) {
        g_flash_info.mfg_id = mfg;
        g_flash_info.memory_type = type;
        g_flash_info.capacity = cap;
        g_flash_info.status_reg1 = spi_flash_read_status();
        if (mfg == JEDEC_MFG_WINBOND && type == JEDEC_TYPE_W25Q) {
            g_flash_info.is_detected = 1;
        }
    }
}

const spi_flash_info_t *spi_flash_get_info(void)
{
    return &g_flash_info;
}

#ifdef __arm__
extern uint32_t _sidata;
extern uint32_t _sdata;
extern uint32_t _edata;

uint32_t spi_flash_get_fw_size(void)
{
    uint32_t load_end = (uint32_t)&_sidata + ((uint32_t)&_edata - (uint32_t)&_sdata);
    if (load_end > 0x08000000 && load_end <= 0x08010000) {
        return load_end - 0x08000000;
    }
    return 65536;
}
#else
static uint32_t mock_fw_size = 13000;
void mock_set_fw_size(uint32_t s) { mock_fw_size = s; }
uint32_t spi_flash_get_fw_size(void)
{
    return mock_fw_size;
}
#endif

int spi_flash_read_superblock(spi_flash_superblock_t *sb)
{
    if (!sb) {
        return -1;
    }
    if (spi_flash_read_data(SPI_FLASH_SUPERBLOCK_ADDR, (uint8_t *)sb, sizeof(*sb)) != 0) {
        return -1;
    }
    if (sb->magic != SPI_FLASH_SUPERBLOCK_MAGIC || sb->layout_version != SPI_FLASH_LAYOUT_VERSION) {
        return -1;
    }
    uint32_t crc = crc32_ieee((const uint8_t *)sb, sizeof(*sb) - sizeof(sb->superblock_crc32));
    if (crc != sb->superblock_crc32) {
        return -2;
    }
    return 0;
}

int spi_flash_write_superblock(const spi_flash_superblock_t *sb)
{
    if (!sb) {
        return -1;
    }
    spi_flash_superblock_t copy = *sb;
    copy.superblock_crc32 = crc32_ieee((const uint8_t *)&copy, sizeof(copy) - sizeof(copy.superblock_crc32));

    if (spi_flash_sector_erase_4k(SPI_FLASH_SUPERBLOCK_ADDR) != 0) {
        return -1;
    }
    if (spi_flash_page_program(SPI_FLASH_SUPERBLOCK_ADDR, (const uint8_t *)&copy, sizeof(copy)) != 0) {
        return -1;
    }
    return 0;
}

int spi_flash_backup_firmware(uint8_t slot_idx, uint32_t *out_crc32)
{
    uint32_t slot_addr;
    if (slot_idx == 0) {
        slot_addr = SPI_FLASH_SLOT_A_ADDR;
    } else if (slot_idx == 1) {
        slot_addr = SPI_FLASH_SLOT_B_ADDR;
    } else if (slot_idx == 2) {
        slot_addr = SPI_FLASH_SLOT_STAGING_ADDR;
    } else {
        return -1;
    }

    uint32_t fw_size = spi_flash_get_fw_size();
    if (fw_size == 0 || fw_size > SPI_FLASH_BLOCK_SIZE) {
        return -1;
    }

    if (spi_flash_block_erase_64k(slot_addr) != 0) {
        return -1;
    }

    uint32_t offset = 0;
    while (offset < fw_size) {
        size_t chunk = fw_size - offset;
        if (chunk > SPI_FLASH_PAGE_SIZE) {
            chunk = SPI_FLASH_PAGE_SIZE;
        }
        const uint8_t *src = (const uint8_t *)((uintptr_t)(0x08000000UL + offset));
        if (spi_flash_page_program(slot_addr + offset, src, chunk) != 0) {
            return -1;
        }
        offset += chunk;
        watchdog_kick();
    }

    uint32_t internal_crc = crc32_ieee((const uint8_t *)((uintptr_t)0x08000000UL), fw_size);
    if (spi_flash_verify_crc32(slot_addr, fw_size, internal_crc) != 0) {
        return -2;
    }

    if (out_crc32) {
        *out_crc32 = internal_crc;
    }

    spi_flash_superblock_t sb;
    if (spi_flash_read_superblock(&sb) != 0) {
        uint8_t *p = (uint8_t *)&sb;
        for (size_t i = 0; i < sizeof(sb); i++) {
            p[i] = 0;
        }
        sb.magic = SPI_FLASH_SUPERBLOCK_MAGIC;
        sb.layout_version = SPI_FLASH_LAYOUT_VERSION;
        sb.boot_status = BOOT_STATUS_CONFIRMED;
        sb.active_fw_slot = slot_idx;
    }
    if (slot_idx == 0) {
        sb.fw_slot_a_size = fw_size;
        sb.fw_slot_a_crc32 = internal_crc;
    } else if (slot_idx == 1) {
        sb.fw_slot_b_size = fw_size;
        sb.fw_slot_b_crc32 = internal_crc;
    } else {
        sb.staging_size = fw_size;
        sb.staging_crc32 = internal_crc;
    }
    spi_flash_write_superblock(&sb);

    return 0;
}

int spi_flash_confirm_boot(void)
{
    spi_flash_superblock_t sb;
    if (spi_flash_read_superblock(&sb) != 0) {
        uint8_t *p = (uint8_t *)&sb;
        for (size_t i = 0; i < sizeof(sb); i++) {
            p[i] = 0;
        }
        sb.magic = SPI_FLASH_SUPERBLOCK_MAGIC;
        sb.layout_version = SPI_FLASH_LAYOUT_VERSION;
        sb.active_fw_slot = 0;
    }
    sb.boot_status = BOOT_STATUS_CONFIRMED;
    sb.boot_attempts = 0;
    return spi_flash_write_superblock(&sb);
}

void spi_flash_boot_guard_check(void)
{
    const spi_flash_info_t *info = spi_flash_get_info();
    if (!info->is_detected) {
        return;
    }

    spi_flash_superblock_t sb;
    if (spi_flash_read_superblock(&sb) != 0) {
        /* First boot or uninitialized superblock: create initial backup of
         * currently running known-good firmware into Slot A (Golden) and Slot B (Rollback). */
        uint32_t crc = 0;
        spi_flash_backup_firmware(0, &crc);
        spi_flash_backup_firmware(1, &crc);
        return;
    }

    if (sb.boot_status == BOOT_STATUS_TESTING) {
        if (sb.boot_attempts >= 3) {
            uint32_t size = sb.fw_slot_b_size;
            if (size == 0 || size > SPI_FLASH_BLOCK_SIZE) {
                size = 65536;
            }
            sb.boot_status = BOOT_STATUS_CONFIRMED;
            sb.boot_attempts = 0;
            sb.active_fw_slot = 1;
            spi_flash_write_superblock(&sb);
            flasher_restore_and_reboot(SPI_FLASH_SLOT_B_ADDR, size);
        } else {
            sb.boot_attempts++;
            spi_flash_write_superblock(&sb);
        }
    }
}
