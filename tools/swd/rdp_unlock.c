/*
 * GD32F150 read-protection (RDP) removal — runs from SRAM (0x20000000).
 *
 * The main flash is read-protected (FMC_OBSTAT.SPC = 1), so SWD cannot read or
 * write it and openocd's flash driver can't even examine the target. This
 * program lifts protection from inside the chip, the same class of trick the
 * factory dump used (SRAM code doing what the debugger is blocked from).
 *
 * Sequence:
 *   1. unlock FMC          (FMC_KEY  <- 0x45670123, 0xCDEF89AB)
 *   2. unlock option bytes (FMC_OBKEY same two keys -> sets OBWEN)
 *   3. erase option bytes  (OBER + START) -> all OB fields become 0xFF, which
 *      is the factory-default/safe state for USER (soft watchdog, no reset on
 *      stop/standby) and for the write-protect bytes (no WP)
 *   4. program RDP = 0xA5  (OBPG, write half-word to 0x1FFFF800) -> "no protect"
 *
 * The programmed option bytes take effect on the next POWER-ON reset. At that
 * POR the hardware sees protection being lifted and MASS-ERASES the main flash
 * -- that is the security interlock, and it is why the factory image goes away.
 * We keep tools/swd/gd32_flash.bin as the restore image.
 *
 * This program does NOT trigger the reload itself: it programs, verifies the
 * FMC status, reports over USART1 (PA2 @ 115200), and stops. Apply by power-
 * cycling the board. Read-back of 0x1FFFF800 stays blocked until that POR, so
 * success is judged from FMC_STAT (ENDF set, no PGERR/WPERR), not from a read.
 */

#include <stdint.h>

#define RCU_BASE      0x40021000
#define RCU_AHBEN     (*(volatile uint32_t *)(RCU_BASE + 0x14))
#define RCU_APB1EN    (*(volatile uint32_t *)(RCU_BASE + 0x1C))

#define GPIOA_BASE    0x48000000
#define GPIOA_CTL     (*(volatile uint32_t *)(GPIOA_BASE + 0x00))
#define GPIOA_OSPD    (*(volatile uint32_t *)(GPIOA_BASE + 0x08))
#define GPIOA_AFSEL0  (*(volatile uint32_t *)(GPIOA_BASE + 0x20))

#define GPIOB_BASE    0x48000400
#define GPIOC_BASE    0x48000800
#define GPIOF_BASE    0x48001400
#define GPIO_CTL(b)   (*(volatile uint32_t *)((b) + 0x00))
#define GPIO_BOP(b)   (*(volatile uint32_t *)((b) + 0x18))

#define FWDGT_BASE       0x40003000
#define FWDGT_CTL        (*(volatile uint32_t *)(FWDGT_BASE + 0x00))
#define FWDGT_PSC        (*(volatile uint32_t *)(FWDGT_BASE + 0x04))
#define FWDGT_RLD        (*(volatile uint32_t *)(FWDGT_BASE + 0x08))
#define FWDGT_KEY_RELOAD 0xAAAA
#define FWDGT_KEY_ACCESS 0x5555

#define UNLOCK_MAILBOX_ADDR 0x20001000U
#define UNLOCK_MAGIC        0x554E4C4BU /* "UNLK" */

typedef struct {
    volatile uint32_t magic;      /* +0x00: 0x554E4C4B ("UNLK") */
    volatile uint32_t status;     /* +0x04: 0=busy, 1=programmed_ok, 2=already_unprotected, 3=err */
    volatile uint32_t err_step;   /* +0x08: 0=none, 1=obwen, 2=ober, 3=obpg */
    volatile uint32_t fmc_stat;   /* +0x0C: final FMC_STAT */
    volatile uint32_t fmc_ctl;    /* +0x10: final FMC_CTL */
    volatile uint32_t fmc_obstat; /* +0x14: final FMC_OBSTAT */
} unlock_mailbox_t;

#define umb (*(volatile unlock_mailbox_t *)UNLOCK_MAILBOX_ADDR)

#define USART1_BASE   0x40004400
#define USART1_CTL0   (*(volatile uint32_t *)(USART1_BASE + 0x00))
#define USART1_BAUD   (*(volatile uint32_t *)(USART1_BASE + 0x0C))
#define USART1_STAT   (*(volatile uint32_t *)(USART1_BASE + 0x1C))
#define USART1_TDATA  (*(volatile uint32_t *)(USART1_BASE + 0x28))

#define UEN   (1 << 0)
#define TEN   (1 << 3)
#define TBE   (1 << 7)

/* ── FMC ── */
#define FMC_BASE      0x40022000
#define FMC_KEY       (*(volatile uint32_t *)(FMC_BASE + 0x04))
#define FMC_OBKEY     (*(volatile uint32_t *)(FMC_BASE + 0x08))
#define FMC_STAT      (*(volatile uint32_t *)(FMC_BASE + 0x0C))
#define FMC_CTL       (*(volatile uint32_t *)(FMC_BASE + 0x10))
#define FMC_OBSTAT    (*(volatile uint32_t *)(FMC_BASE + 0x1C))

#define OB_SPC_ADDR   0x1FFFF800

#define UNLOCK_KEY0   0x45670123UL
#define UNLOCK_KEY1   0xCDEF89ABUL

#define CTL_OBPG      (1 << 4)
#define CTL_OBER      (1 << 5)
#define CTL_START     (1 << 6)
#define CTL_LK        (1 << 7)
#define CTL_OBWEN     (1 << 9)

#define STAT_BUSY     (1 << 0)
#define STAT_PGERR    (1 << 2)
#define STAT_WPERR    (1 << 4)
#define STAT_ENDF     (1 << 5)

static void delay(volatile uint32_t n)
{
    while (n--) {
        FWDGT_CTL = FWDGT_KEY_RELOAD;
        __asm__ volatile("");
    }
}

static void uart_putc(uint8_t c)
{
    while (!(USART1_STAT & TBE))
        ;
    USART1_TDATA = c;
}

static void uart_puts(const char *s)
{
    while (*s)
        uart_putc((uint8_t)*s++);
}

static const char hex_lut[] = "0123456789ABCDEF";

static void uart_hex32(uint32_t v)
{
    uart_puts("0x");
    for (int i = 7; i >= 0; i--)
        uart_putc(hex_lut[(v >> (i * 4)) & 0xF]);
}

static void fmc_wait_idle(void)
{
    uint32_t guard = 2000000;
    while ((FMC_STAT & STAT_BUSY) && --guard) {
        FWDGT_CTL = FWDGT_KEY_RELOAD;
    }
}

static void sync_mailbox(uint32_t status, uint32_t err_step)
{
    umb.fmc_stat = FMC_STAT;
    umb.fmc_ctl = FMC_CTL;
    umb.fmc_obstat = FMC_OBSTAT;
    umb.err_step = err_step;
    umb.status = status;
}

static void report(const char *label)
{
    uart_puts(label);
    uart_puts(" STAT=");
    uart_hex32(FMC_STAT);
    uart_puts(" CTL=");
    uart_hex32(FMC_CTL);
    uart_puts(" OBSTAT=");
    uart_hex32(FMC_OBSTAT);
    uart_puts("\r\n");
}

void main(void)
{
    /* Disable interrupts and SysTick so flash operations do not vector to Flash */
    __asm__ volatile("cpsid i");
    *(volatile uint32_t *)0xE000E010 = 0;          /* SysTick CTL */
    *(volatile uint32_t *)0xE000E180 = 0xFFFFFFFF; /* NVIC ICER */
    *(volatile uint32_t *)0xE000E280 = 0xFFFFFFFF; /* NVIC ICPR */

    /* Extend Watchdog to maximum ~26 seconds and freeze during debug */
    FWDGT_CTL = FWDGT_KEY_ACCESS;
    FWDGT_PSC = 7;
    FWDGT_RLD = 0x0FFF;
    FWDGT_CTL = FWDGT_KEY_RELOAD;
    *(volatile uint32_t *)0x40015804 |= (1 << 8);

    umb.magic = UNLOCK_MAGIC;
    sync_mailbox(0, 0); /* BUSY */

    RCU_AHBEN  |= (1 << 17) | (1 << 18) | (1 << 19) | (1 << 22);
    RCU_APB1EN |= (1 << 17);
    delay(1000);

    /* Hold the main power latches so the board does not cut its own supply. */
    {
        uint32_t ctl = GPIO_CTL(GPIOC_BASE);
        ctl &= ~(3U << (15 * 2));
        ctl |=  (1U << (15 * 2));
        GPIO_CTL(GPIOC_BASE) = ctl;
        GPIO_BOP(GPIOC_BASE) = (1 << 15);

        ctl = GPIO_CTL(GPIOB_BASE);
        ctl &= ~(3U << (3 * 2));
        ctl |=  (1U << (3 * 2));
        GPIO_CTL(GPIOB_BASE) = ctl;
        GPIO_BOP(GPIOB_BASE) = (1 << 3);

        ctl = GPIO_CTL(GPIOF_BASE);
        ctl &= ~(3U << (7 * 2));
        ctl |=  (1U << (7 * 2));
        GPIO_CTL(GPIOF_BASE) = ctl;
        GPIO_BOP(GPIOF_BASE) = (1 << 7);
    }

    /* PA2 = USART1 TX (AF1) */
    GPIOA_CTL   = (GPIOA_CTL   & ~(3U << (2 * 2))) | (2U << (2 * 2));
    GPIOA_OSPD |= (1U << (2 * 2));
    GPIOA_AFSEL0 = (GPIOA_AFSEL0 & ~(0xFU << (2 * 4))) | (0x1U << (2 * 4));

    USART1_CTL0 = 0;
    USART1_BAUD = 0x0045;               /* 8 MHz / 115200 */
    USART1_CTL0 = UEN | TEN;

    delay(5000);
    uart_puts("\r\n=== GD32 RDP unlock ===\r\n");
    report("[before]");

    if (!(FMC_OBSTAT & (1 << 1))) {
        sync_mailbox(2, 0);
        uart_puts("[info] SPC already clear -- flash is NOT protected. Aborting.\r\n");
        while (1)
            delay(100000);
    }

    /* 1. Unlock FMC */
    fmc_wait_idle();
    if (FMC_CTL & CTL_LK) {
        FMC_KEY = UNLOCK_KEY0;
        FMC_KEY = UNLOCK_KEY1;
    }
    report("[fmc unlocked]");

    /* 2. Unlock option-byte programming */
    FMC_OBKEY = UNLOCK_KEY0;
    FMC_OBKEY = UNLOCK_KEY1;
    report("[ob unlocked]");

    if (!(FMC_CTL & CTL_OBWEN)) {
        sync_mailbox(3, 1);
        uart_puts("[FAIL] OBWEN not set -- option-byte unlock rejected. Aborting.\r\n");
        while (1)
            delay(100000);
    }

    /* 3. Erase option bytes -> all fields 0xFF (safe defaults) */
    fmc_wait_idle();
    FMC_CTL |= CTL_OBER;
    FMC_CTL |= CTL_START;
    fmc_wait_idle();
    FMC_CTL &= ~CTL_OBER;
    report("[ob erased]");

    if (FMC_STAT & (STAT_PGERR | STAT_WPERR)) {
        sync_mailbox(3, 2);
        uart_puts("[FAIL] error during OB erase. Aborting.\r\n");
        while (1)
            delay(100000);
    }
    FMC_STAT = STAT_ENDF | STAT_PGERR | STAT_WPERR; /* clear flags */

    /* 4. Program RDP = 0xA5 (no protection) */
    fmc_wait_idle();
    FMC_CTL |= CTL_OBPG;
    *(volatile uint16_t *)OB_SPC_ADDR = 0x00A5;
    fmc_wait_idle();
    FMC_CTL &= ~CTL_OBPG;
    report("[rdp=A5 programmed]");

    if (FMC_STAT & (STAT_PGERR | STAT_WPERR)) {
        sync_mailbox(3, 3);
        uart_puts("[FAIL] error programming RDP. Aborting.\r\n");
        while (1)
            delay(100000);
    }

    sync_mailbox(1, 0);
    uart_puts("\r\n[OK] Option bytes written. RDP set to 0xA5 (unprotected).\r\n");
    uart_puts("[OK] Now POWER-CYCLE the board: at power-on the option bytes\r\n");
    uart_puts("     reload, the chip MASS-ERASES main flash and clears protection.\r\n");
    uart_puts("     0x1FFFF800 stays unreadable until that power cycle -- expected.\r\n");
    uart_puts("=== done ===\r\n");

    while (1)
        delay(100000);
}
