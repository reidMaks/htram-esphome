#include "sensors.h"
#include "gd32f150.h"

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
 * Board self-heating compensation.
 *
 * The SHT30 sits on the PCB beside the MCU and the 5 V boost, so it reads well
 * above ambient: the bench probe measured 31.9 C at the sensor with the die at
 * ~43 C (internal channel 16, V25 = 1.45 V, 4.1 mV/C) on an open board.
 * A correction is genuinely needed -- the factory firmware has one for a reason.
 *
 * The factory does not use a constant. Its model (flash 0x080059E0..0x08005A94,
 * documented in docs/GD32_HARDWARE_MAP.md 5.1) ramps three counters -- backlight,
 * USB, 5 V boost -- pushes each through a log2 and subtracts whole degrees,
 * up to 13 C in total, adding up to 31 points of RH to match.
 *
 * A single constant was tried here first, and it was not enough. 6.50 C was
 * calibrated against a factory unit alongside, both settled -- but on battery,
 * on an open board, which is the factory's own off_bl + off_boost = 8 case with
 * off_usb = 0. Assembled and on the charger the USB term is missing entirely and
 * this board reads 5-6 C high: 29 C observed where the reference showed 23.
 *
 * So the state is back, but not the quantisation. Whole degrees through a log2
 * are what made the reading slide ~8 C in 1 C steps over the first ~96 s after
 * boot and jump 5 C the moment USB changed -- the wandering that b07ce05 set out
 * to remove. Here the offset is carried in 0.01 C, relaxes toward its target
 * with a time constant of about 8 minutes (one step per 30 s measurement cycle),
 * and is seeded to the target on the first reading so a boot does not ramp.
 *
 * The USB term is the factory's own 5.00 C. PC13 does deliver the bit reliably:
 * verified in both states in b07ce05 (on battery PC13=0 -> Status []; on external
 * power PC13=1 -> Status [Charging, USB]). An older comment here claimed it did
 * not; that predates the check.
 *
 * The backlight and boost terms stay folded into the base constant. Both are on
 * whenever telemetry flows -- the panel comes up lit and the CO2 rail is never
 * duty-cycled -- so splitting them out would add state that never changes.
 *
 * Humidity has no constant of its own any more, and should not: a sensor above
 * ambient reads a lower RH for the same water content, so it follows from the
 * temperature offset through saturation pressure. That also settles the caveat
 * the old constant carried, which was only honest near one operating point.
 * Cross-check against the same bench calibration: raw 34.46 %RH at 31.5 C with
 * a 6.5 C offset gives 49.9 %RH against the reference's 50 %.
 *
 * Per-device trim lives on the ESP (a Home Assistant number, default 0), because
 * each board and each room differ slightly and reflashing this chip to chase
 * half a degree is not a trade worth making.
 */
#define SHT30_T_OFF_BASE_001C   650   /* battery + backlight + boost, settled */
#define SHT30_T_OFF_USB_001C    500   /* extra while on external power        */
#define SHT30_T_OFF_RELAX_SHIFT 4     /* 1/16 per 30 s cycle -> tau ~ 8 min   */

/* exp(x) for 0 <= x <= 1, argument and result in Q16.
 * Fourth-order Taylor: 0.06 % at x = 0.38 (a 6.5 C offset), 0.4 % at x = 1.
 * A libm expf would cost a soft-float import for a number that only has to be
 * good to a tenth of a percent of RH. */
static uint32_t exp_q16(uint32_t x)
{
    if (x > (1u << 16)) x = 1u << 16;
    uint64_t term = 1u << 16;
    uint64_t sum = term;
    for (uint32_t n = 1; n <= 4; n++) {
        term = (term * x) >> 16;
        term /= n;
        sum += term;
    }
    return (uint32_t)sum;
}

/* es(T_sensor) / es(T_sensor - off), Q16 -- the factor the measured RH has to
 * be multiplied by to express it at ambient instead of at the warm sensor.
 *
 * Magnus: ln es = a*T/(b+T) with a = 17.62, b = 243.12 C, so d(ln es)/dT is
 * a*b/(b+T)^2 and the ratio is exp(k*off). Taking k at the midpoint of the
 * interval rather than at either end makes the first-order form second-order
 * accurate: across 25..31.5 C it lands on 1.4595 against an exact 1.4595.
 *
 * Both arguments are in 0.01 C. With D = 100*(b + T_mid) the two 1e-4 scale
 * factors collapse into the constant: x = 428380 * off / D^2. */
static uint32_t rh_ratio_q16(int32_t t_sensor_001c, int32_t off_001c)
{
    if (off_001c <= 0)
        return 1u << 16;

    int32_t d = 24312 + t_sensor_001c - off_001c / 2;
    if (d < 1000)                       /* far below anything this board sees */
        d = 1000;

    uint64_t x = ((uint64_t)428380 * (uint32_t)off_001c) << 16;
    x /= (uint64_t)d * (uint64_t)d;

    return exp_q16((uint32_t)x);
}

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

    /* Move the offset one step toward what this power state calls for. The
     * first reading takes the target outright: ramping from zero after every
     * boot or reflash is the very artefact this model is written to avoid. */
    static int32_t t_off_001c = 0;
    static uint8_t t_off_valid = 0;

    int32_t target = SHT30_T_OFF_BASE_001C
                   + (usb_present ? SHT30_T_OFF_USB_001C : 0);
    if (!t_off_valid) {
        t_off_001c = target;
        t_off_valid = 1;
    } else {
        int32_t d = target - t_off_001c;
        int32_t step = d >> SHT30_T_OFF_RELAX_SHIFT;
        if (step == 0)                  /* otherwise it stalls short of target */
            step = (d > 0) ? 1 : (d < 0 ? -1 : 0);
        t_off_001c += step;
    }

    int32_t t_comp = t_raw - t_off_001c;

    uint32_t ratio = rh_ratio_q16(t_raw, t_off_001c);
    int32_t h_comp = (int32_t)(((uint64_t)h_raw * ratio) >> 16);
    if (h_comp > 10000) h_comp = 10000;
    if (h_comp < 0) h_comp = 0;

    *temp_001c = (int16_t)t_comp;
    *hum_001pct = (uint16_t)h_comp;
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
