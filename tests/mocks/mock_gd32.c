#include "mock_gd32.h"

#include <string.h>
#include <sys/mman.h>

static void __attribute__((constructor)) init_mock_hardware_memory(void) {
  mmap((void*)0x40020000, 0x10000, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
  mmap((void*)0xE000E000, 0x1000, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
}

mock_gpio_t mock_gpios[4];

volatile uint32_t mock_rcu_ctl = (1 << 1) | (1U << 25);
static volatile uint32_t mock_rcu_cfg0_val = 0;

uint32_t* mock_get_rcu_cfg0_ptr(void) {
  if ((mock_rcu_cfg0_val & 3U) == 2U) {
    mock_rcu_cfg0_val = (mock_rcu_cfg0_val & ~(3U << 2)) | (2U << 2);
  }
  return (uint32_t*)&mock_rcu_cfg0_val;
}

volatile uint32_t mock_rcu_ahben = 0;
volatile uint32_t mock_rcu_apb1en = 0;
volatile uint32_t mock_rcu_apb2en = 0;

volatile uint32_t mock_usart1_stat = USART_STAT_TBE | USART_STAT_TC;
volatile uint32_t mock_usart1_rdata_val = 0;
volatile uint32_t mock_usart1_baud = 0;
volatile uint32_t mock_usart1_ctl0 = 0;

uint32_t mock_read_usart1_rdata(void) {
  mock_usart1_stat &= ~(USART_STAT_RBNE | USART_STAT_ORE);
  mock_usart1_stat |= (USART_STAT_TBE | USART_STAT_TC);
  return mock_usart1_rdata_val;
}

volatile uint32_t mock_usart0_stat = USART_STAT_TBE;
volatile uint32_t mock_usart0_tdata = 0;
volatile uint32_t mock_usart0_rdata = 0;
volatile uint32_t mock_usart0_ctl0 = 0;
volatile uint32_t mock_usart0_baud = 0;

volatile uint32_t mock_timer2_ctl0 = 0;
volatile uint32_t mock_timer2_swevg = 0;
volatile uint32_t mock_timer2_chctl1 = 0;
volatile uint32_t mock_timer2_chctl2 = 0;
volatile uint32_t mock_timer2_psc = 0;
volatile uint32_t mock_timer2_car = 0;
volatile uint32_t mock_timer2_ch2cv = 0;

volatile uint32_t mock_rcu_apb1rst = 0;
volatile uint32_t mock_rcu_apb2rst = 0;

int mock_adc_auto_eoc = 1;

uint32_t* mock_get_adc_ctl1_ptr(void) {
  if (mock_adc_auto_eoc) {
    mock_adc_stat |= (1 << 1); /* Set EOC when conversion triggered */
  }
  return (uint32_t*)&mock_adc_ctl1;
}

volatile uint32_t mock_adc_stat = 0;
volatile uint32_t mock_adc_ctl1 = 0;
volatile uint32_t mock_adc_rsq0 = 0;
volatile uint32_t mock_adc_rsq2 = 0;
volatile uint32_t mock_adc_rdata = 0;
volatile uint32_t mock_adc_sampt1 = 0;

volatile uint32_t mock_fwdgt_ctl = 0;
volatile uint32_t mock_fwdgt_psc = 0;
volatile uint32_t mock_fwdgt_rld = 0;

volatile uint32_t mock_nvic_iser0 = 0;

uint8_t mock_tx_capture[TX_CAPTURE_MAX];
size_t mock_tx_capture_len = 0;
static uint32_t dummy_tx = 0;

uint32_t* mock_get_usart1_tdata_ptr(void) {
  if (mock_tx_capture_len < TX_CAPTURE_MAX) {
    return (uint32_t*)&mock_tx_capture[mock_tx_capture_len++];
  }
  return &dummy_tx;
}

void mock_tx_clear(void) {
  mock_tx_capture_len = 0;
  memset(mock_tx_capture, 0, sizeof(mock_tx_capture));
}

void mock_gd32_reset(void) {
  memset(mock_gpios, 0, sizeof(mock_gpios));
  mock_rcu_ctl = (1 << 1) | (1U << 25);
  mock_rcu_cfg0_val = 0;
  mock_rcu_ahben = 0;
  mock_rcu_apb1en = 0;
  mock_rcu_apb2en = 0;

  mock_usart1_stat = USART_STAT_TBE | USART_STAT_TC;
  mock_usart1_rdata_val = 0;
  mock_usart1_baud = 0;
  mock_usart1_ctl0 = 0;

  mock_usart0_stat = USART_STAT_TBE;
  mock_usart0_tdata = 0;
  mock_usart0_rdata = 0;

  mock_timer2_ctl0 = 0;
  mock_timer2_swevg = 0;
  mock_timer2_chctl1 = 0;
  mock_timer2_chctl2 = 0;
  mock_timer2_psc = 0;
  mock_timer2_car = 0;
  mock_timer2_ch2cv = 0;

  mock_nvic_iser0 = 0;
  mock_adc_auto_eoc = 1;
  mock_tx_clear();
}

void (*mock_delay_us_hook)(uint32_t us) = NULL;
void (*mock_delay_cycles_hook)(uint32_t cycles) = NULL;

void delay_ms(uint32_t ms) {
  (void)ms;
}
void delay_us(uint32_t us) {
  if (mock_delay_us_hook) {
    mock_delay_us_hook(us);
  }
}
void delay_cycles(uint32_t cycles) {
  if (mock_delay_cycles_hook) {
    mock_delay_cycles_hook(cycles);
  }
}

uint32_t (*mock_gpio_istat_hook)(uint32_t b) = NULL;

uint32_t mock_get_gpio_istat(uint32_t b) {
  if (mock_gpio_istat_hook) {
    return mock_gpio_istat_hook(b);
  }
  if (b < 4) {
    return mock_gpios[b].istat;
  }
  return 0;
}

void gpio_cfg_out_pp(uint32_t base, uint8_t pin) {
  if (base < 4) {
    mock_gpios[base].ctl &= ~(3U << (pin * 2));
    mock_gpios[base].ctl |= (1U << (pin * 2));
    mock_gpios[base].omd &= ~(1U << pin);
  }
}

void gpio_cfg_in(uint32_t base, uint8_t pin, uint8_t pud) {
  if (base < 4) {
    mock_gpios[base].ctl &= ~(3U << (pin * 2));
    mock_gpios[base].pud &= ~(3U << (pin * 2));
    mock_gpios[base].pud |= ((uint32_t)pud << (pin * 2));
  }
}

int gpio_get(uint32_t base, uint8_t pin) {
  return (mock_get_gpio_istat(base) & (1U << pin)) ? 1 : 0;
}
