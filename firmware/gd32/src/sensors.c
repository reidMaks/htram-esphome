#include "sensors.h"
#include "gd32f150.h"
#include "periph.h"

/* ── SHT30 I2C Bitbang (PB6 = SCL, PB7 = SDA, PA8 = nRESET, PB2 = PWR) ── */

#define SCL_PIN  6
#define SDA_PIN  7

static inline void i2c_delay(void)
{
    delay_us(20); /* Slow down I2C to ~25kHz to match original behavior and account for weak pull-ups */
}

static inline void sda_mode_input(void)
{
    uint32_t ctl = GPIO_CTL(GPIOB_BASE);
    ctl &= ~(3U << (SDA_PIN * 2));
    GPIO_CTL(GPIOB_BASE) = ctl;
}

static inline void sda_mode_output(void)
{
    uint32_t ctl = GPIO_CTL(GPIOB_BASE);
    ctl &= ~(3U << (SDA_PIN * 2));
    ctl |=  (1U << (SDA_PIN * 2));
    GPIO_CTL(GPIOB_BASE) = ctl;
}

static inline int sda_read(void)
{
    return (GPIO_ISTAT(GPIOB_BASE) & (1U << SDA_PIN)) ? 1 : 0;
}

static void i2c_start(void)
{
    sda_mode_output();
    GPIOB_BOP = (1 << SDA_PIN);
    GPIOB_BOP = (1 << SCL_PIN);
    i2c_delay();
    GPIOB_BC  = (1 << SDA_PIN);
    i2c_delay();
    GPIOB_BC  = (1 << SCL_PIN);
    i2c_delay();
}

static void i2c_stop(void)
{
    sda_mode_output();
    GPIOB_BC  = (1 << SDA_PIN);
    i2c_delay();
    GPIOB_BOP = (1 << SCL_PIN);
    i2c_delay();
    GPIOB_BOP = (1 << SDA_PIN);
    i2c_delay();
    sda_mode_input();
}

static int i2c_write_byte(uint8_t byte)
{
    sda_mode_output();
    for (int i = 7; i >= 0; i--) {
        GPIOB_BC = (1 << SCL_PIN);
        if (byte & (1 << i))
            GPIOB_BOP = (1 << SDA_PIN);
        else
            GPIOB_BC  = (1 << SDA_PIN);
        i2c_delay();
        GPIOB_BOP = (1 << SCL_PIN);
        i2c_delay();
    }
    GPIOB_BC = (1 << SCL_PIN);
    sda_mode_input();
    i2c_delay();

    /* Read ACK */
    GPIOB_BOP = (1 << SCL_PIN);
    i2c_delay();
    int ack = (sda_read() == 0) ? 1 : 0;
    GPIOB_BC = (1 << SCL_PIN);
    i2c_delay();

    return ack;
}

static uint8_t i2c_read_byte(int ack)
{
    uint8_t byte = 0;
    sda_mode_input();
    for (int i = 7; i >= 0; i--) {
        GPIOB_BOP = (1 << SCL_PIN);
        i2c_delay();
        if (sda_read())
            byte |= (1 << i);
        GPIOB_BC = (1 << SCL_PIN);
        i2c_delay();
    }

    sda_mode_output();
    if (ack)
        GPIOB_BC  = (1 << SDA_PIN);
    else
        GPIOB_BOP = (1 << SDA_PIN);
    i2c_delay();
    GPIOB_BOP = (1 << SCL_PIN);
    i2c_delay();
    GPIOB_BC  = (1 << SCL_PIN);
    i2c_delay();
    sda_mode_input();

    return byte;
}

static uint8_t sht30_crc8(const uint8_t *data, int len)
{
    uint8_t crc = 0xFF;
    for (int i = 0; i < len; i++) {
        crc ^= data[i];
        for (int b = 0; b < 8; b++) {
            if (crc & 0x80)
                crc = (crc << 1) ^ 0x31;
            else
                crc <<= 1;
        }
    }
    return crc;
}

/*
 * Raw SHT30 readings:
 * Sensor self-heating compensation is performed on the ESP32 / ESPHome side
 * via transparent calibration trim and psychrometric saturation pressure formulas.
 * The GD32 transmits unadulterated raw physical sensor measurements over UART.
 */

int sensors_sht30_start(void)
{
    /* Single-shot measurement (0x2400): SHT30 sleeps in 0.2uA mode between measurements */
    i2c_start();
    if (!i2c_write_byte(0x88)) { i2c_stop(); return -1; }
    if (!i2c_write_byte(0x24)) { i2c_stop(); return -2; }
    if (!i2c_write_byte(0x00)) { i2c_stop(); return -3; }
    i2c_stop();
    return 0;
}

/* Call no sooner than SHT30_CONVERSION_MS after sensors_sht30_start(). The
 * datasheet limit for high repeatability is 15.5 ms; the margin is kept
 * because delay_ms() calibration runs short at full core speed. */
int sensors_sht30_fetch(int16_t *temp_001c, uint16_t *hum_001pct,
                        uint8_t usb_present)
{
    (void)usb_present;
    uint8_t buf[6];

    i2c_start();
    if (!i2c_write_byte(0x89)) { i2c_stop(); return -4; }
    for (int i = 0; i < 5; i++)
        buf[i] = i2c_read_byte(1);
    buf[5] = i2c_read_byte(0);
    i2c_stop();

    if (sht30_crc8(&buf[0], 2) != buf[2] || sht30_crc8(&buf[3], 2) != buf[5]) {
        return -5;
    }

    uint16_t raw_t = ((uint16_t)buf[0] << 8) | buf[1];
    uint16_t raw_h = ((uint16_t)buf[3] << 8) | buf[4];

    /* Raw T [0.01 C] = -4500 + 17500 * raw_t / 65535 */
    int32_t t_raw = -4500 + ((int32_t)17500 * raw_t) / 65535;
    /* Raw RH [0.01 %] = 10000 * raw_h / 65535 */
    uint32_t h_raw = ((uint32_t)10000 * raw_h) / 65535;

    *temp_001c = (int16_t)t_raw;
    *hum_001pct = (uint16_t)h_raw;
    return 0;
}

/* ── Honeywell CRIR M1 CO2 Sensor (USART0 @ 9600, PB11 = 5V Boost, PB9 = Pwr) ── */

static const uint8_t crir_query_cmd[8] = {
    0xFE, 0x04, 0x00, 0x07, 0x00, 0x01, 0x94, 0x04
};

static uint16_t modbus_crc16(const uint8_t *buf, int len)
{
    uint16_t crc = 0xFFFF;
    for (int i = 0; i < len; i++) {
        crc ^= buf[i];
        for (int b = 0; b < 8; b++) {
            if (crc & 1)
                crc = (crc >> 1) ^ 0xA001;
            else
                crc >>= 1;
        }
    }
    return crc;
}

static int usart0_getc_timeout(uint32_t timeout_ms)
{
    while (timeout_ms--) {
        for (uint32_t i = 0; i < 200; i++) {
            if (USART0_STAT & USART_RBNE)
                return (uint8_t)USART0_RDATA;
            delay_cycles(10);
        }
    }
    return -1;
}

int sensors_poll_co2(uint16_t *co2_ppm, uint8_t *warmup_flag)
{
    /* Clear RX FIFO */
    while (USART0_STAT & USART_RBNE) {
        volatile uint32_t dummy = USART0_RDATA;
        (void)dummy;
    }

    /* Send Modbus Query */
    for (int i = 0; i < 8; i++) {
        uint32_t to = 10000;
        while (!(USART0_STAT & USART_TBE) && --to)
            ;
        USART0_TDATA = crir_query_cmd[i];
    }

    /* Read 7-byte response: FE 04 02 <hi> <lo> <crc_lo> <crc_hi> */
    uint8_t resp[7] = {0};
    for (int i = 0; i < 7; i++) {
        watchdog_kick();
        int b = usart0_getc_timeout(i == 0 ? 300 : 100);
        if (b < 0) return -(i + 1);
        resp[i] = (uint8_t)b;
    }

    if (resp[0] != 0xFE || resp[1] != 0x04 || resp[2] != 0x02) return -10;

    uint16_t calc_crc = modbus_crc16(resp, 5);
    uint16_t resp_crc = (uint16_t)resp[5] | ((uint16_t)resp[6] << 8);
    if (calc_crc != resp_crc) return -11;

    uint16_t val = ((uint16_t)resp[3] << 8) | resp[4];
    *co2_ppm = val;
    *warmup_flag = (val == 0) ? 1 : 0;
    return 0;
}

void sensors_init(void)
{
    /* 1. SHT30 Pins (PB6 SCL, PB7 SDA). PA8 is the sensor's hardware nRESET
     * and is left as INPUT here -- but not for the reason this comment used to
     * give.
     *
     * It claimed PA8 was the ESP32 enable line and that the factory never
     * drove it. Both are wrong, and both were checked on hardware 2026-09-07:
     * holding PA8 low removed temperature and humidity from telemetry entirely
     * while CO2 kept publishing, and pulsing it never once restarted the ESP.
     * The factory does drive PA8 -- only inside its SHT30 read-failure path,
     * which a snapshot of live GPIO never catches.
     *
     * Leaving it INPUT is still correct: the SHT3x nRESET has an internal
     * pull-up and the I2C soft reset below is enough for every fault seen so
     * far. What we give up is the recovery the factory keeps for the case the
     * sensor stops answering I2C at all -- see docs/GD32_HARDWARE_MAP.md
     * "PA8" for the pulse it uses (low 3 ms, then 3 s before retrying). */
    gpio_cfg_in(GPIOA_BASE, 8, 1); /* input, pull-up (matches factory idle) */

    /* SCL (PB6) and SDA (PB7): Open-Drain, 50MHz, Pull-up */
    uint32_t ctl_b = GPIO_CTL(GPIOB_BASE);
    ctl_b &= ~((3U << (6 * 2)) | (3U << (7 * 2)));
    ctl_b |=  ((1U << (6 * 2)) | (1U << (7 * 2)));
    GPIO_CTL(GPIOB_BASE) = ctl_b;

    GPIO_OMD(GPIOB_BASE) |= (1U << 6) | (1U << 7);
    GPIO_OSPD(GPIOB_BASE) |= (3U << (6 * 2)) | (3U << (7 * 2));
    GPIO_PUD(GPIOB_BASE) &= ~((3U << (6 * 2)) | (3U << (7 * 2)));
    GPIO_PUD(GPIOB_BASE) |=  ((1U << (6 * 2)) | (1U << (7 * 2)));

    GPIOB_BOP = (1 << 6);
    sda_mode_input();

    /* SHT30 soft reset over I2C (0x30A2), replacing the removed nRESET pulse */
    i2c_start();
    if (i2c_write_byte(0x88)) {
        i2c_write_byte(0x30);
        i2c_write_byte(0xA2);
    }
    i2c_stop();
    delay_ms(20);

    /* Send Break command (0x3093) to ensure SHT30 is in low-power idle mode */
    i2c_start();
    if (i2c_write_byte(0x88)) {
        i2c_write_byte(0x30);
        i2c_write_byte(0x93);
    }
    i2c_stop();

    /* 2. CRIR M1 Power (PB11 = 5V Boost, PB9 = Power Switch) */
    gpio_cfg_out_pp(GPIOB_BASE, 11);
    GPIOB_BOP = (1 << 11); /* PB11 = 1 (5V Boost ON) */

    gpio_cfg_out_pp(GPIOB_BASE, 9);
    GPIOB_BOP = (1 << 9);  /* PB9 = 1 (CO2 Sensor Power ON) */

    /* 3. USART0 on PA9 (TX) and PA10 (RX) @ 9600 8N1 */
    RCU_APB2EN |= RCU_APB2EN_USART0EN;

    /* PA9 (TX) & PA10 (RX) -> AF1, 50MHz, Pull-up */
    uint32_t ctl_a = GPIO_CTL(GPIOA_BASE);
    ctl_a &= ~((3U << (9 * 2)) | (3U << (10 * 2)));
    ctl_a |= (2U << (9 * 2)) | (2U << (10 * 2)); /* Both Alternate Function */
    GPIO_CTL(GPIOA_BASE) = ctl_a;

    GPIO_OSPD(GPIOA_BASE) |= (3U << (9 * 2)) | (3U << (10 * 2));
    GPIO_PUD(GPIOA_BASE) &= ~((3U << (9 * 2)) | (3U << (10 * 2)));
    GPIO_PUD(GPIOA_BASE) |=  ((1U << (9 * 2)) | (1U << (10 * 2)));

    GPIO_AFSEL1(GPIOA_BASE) &= ~((0x0F << ((9 - 8) * 4)) | (0x0F << ((10 - 8) * 4)));
    GPIO_AFSEL1(GPIOA_BASE) |= (1 << ((9 - 8) * 4)) | (1 << ((10 - 8) * 4)); /* AF1 = USART0 */

    USART0_CTL0 = 0;
    USART0_BAUD = SYSTEM_CLOCK_HZ / 9600;
    USART0_CTL0 = USART_UEN | USART_TEN | USART_REN;
}
