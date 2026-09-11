#ifndef MOCK_GD32_H
#define MOCK_GD32_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SYSTEM_CLOCK_HZ 72000000UL
#define USART1_IRQn 28
#define GD32_UART_BAUD 921600UL

void USART1_IRQHandler(void);

/* RCU bits */
#define RCU_AHBEN_PAEN      (1 << 17)
#define RCU_AHBEN_PBEN      (1 << 18)
#define RCU_AHBEN_PCEN      (1 << 19)
#define RCU_AHBEN_PFEN      (1 << 22)
#define RCU_APB1EN_USART1EN (1 << 17)
#define RCU_APB2EN_USART0EN (1 << 14)
#define RCU_APB2EN_ADCEN    (1 << 9)
#define RCU_APB1EN_TIMER2EN (1 << 1)
#define RCU_APB2EN_TIMER15EN (1 << 17)

/* USART bits */
#define USART_CTL0_UEN      (1 << 0)
#define USART_CTL0_REN      (1 << 2)
#define USART_CTL0_TEN      (1 << 3)
#define USART_CTL0_RBNEIE   (1 << 5)
#define USART_UEN           USART_CTL0_UEN
#define USART_REN           USART_CTL0_REN
#define USART_TEN           USART_CTL0_TEN
#define USART_RBNEIE        USART_CTL0_RBNEIE

#define USART_STAT_RBNE     (1 << 5)
#define USART_STAT_TC       (1 << 6)
#define USART_STAT_TBE      (1 << 7)
#define USART_STAT_ORE      (1 << 3)
#define USART_RBNE          USART_STAT_RBNE
#define USART_TC            USART_STAT_TC
#define USART_TBE           USART_STAT_TBE
#define USART_ORE           USART_STAT_ORE

/* GPIO base indexes */
#define GPIOA_BASE 0
#define GPIOB_BASE 1
#define GPIOC_BASE 2
#define GPIOF_BASE 3

typedef struct {
    uint32_t ctl;
    uint32_t omd;
    uint32_t ospd;
    uint32_t pud;
    uint32_t istat;
    uint32_t octl;
    uint32_t bop;
    uint32_t afsel0;
    uint32_t afsel1;
    uint32_t bc;
} mock_gpio_t;

extern mock_gpio_t mock_gpios[4];

#define GPIO_CTL(b)     (mock_gpios[b].ctl)
#define GPIO_OMD(b)     (mock_gpios[b].omd)
#define GPIO_OSPD(b)    (mock_gpios[b].ospd)
#define GPIO_PUD(b)     (mock_gpios[b].pud)
extern uint32_t (*mock_gpio_istat_hook)(uint32_t b);
uint32_t mock_get_gpio_istat(uint32_t b);
#define GPIO_ISTAT(b)   mock_get_gpio_istat(b)
#define GPIO_OCTL(b)    (mock_gpios[b].octl)
#define GPIO_BOP(b)     (mock_gpios[b].bop)
#define GPIO_AFSEL0(b)  (mock_gpios[b].afsel0)
#define GPIO_AFSEL1(b)  (mock_gpios[b].afsel1)
#define GPIO_BC(b)      (mock_gpios[b].bc)

#define GPIOA_BOP       GPIO_BOP(GPIOA_BASE)
#define GPIOB_BOP       GPIO_BOP(GPIOB_BASE)
#define GPIOC_BOP       GPIO_BOP(GPIOC_BASE)
#define GPIOA_BC        GPIO_BC(GPIOA_BASE)
#define GPIOB_BC        GPIO_BC(GPIOB_BASE)
#define GPIOC_BC        GPIO_BC(GPIOC_BASE)

/* RCU registers */
extern volatile uint32_t mock_rcu_ctl;
uint32_t *mock_get_rcu_cfg0_ptr(void);
extern volatile uint32_t mock_rcu_ahben;
extern volatile uint32_t mock_rcu_apb1en;
extern volatile uint32_t mock_rcu_apb2en;
#define RCU_CTL    mock_rcu_ctl
#define RCU_CFG0   (*mock_get_rcu_cfg0_ptr())
#define RCU_AHBEN  mock_rcu_ahben
#define RCU_APB1EN mock_rcu_apb1en
#define RCU_APB2EN mock_rcu_apb2en

/* USART1 registers */
uint32_t *mock_get_usart1_tdata_ptr(void);
uint32_t mock_read_usart1_rdata(void);
extern volatile uint32_t mock_usart1_stat;
extern volatile uint32_t mock_usart1_rdata_val;
extern volatile uint32_t mock_usart1_baud;
extern volatile uint32_t mock_usart1_ctl0;
#define USART1_STAT  mock_usart1_stat
#define USART1_TDATA (*mock_get_usart1_tdata_ptr())
#define USART1_RDATA mock_read_usart1_rdata()
#define USART1_BAUD  mock_usart1_baud
#define USART1_CTL0  mock_usart1_ctl0

/* USART0 registers (CO2 sensor) */
extern volatile uint32_t mock_usart0_stat;
extern volatile uint32_t mock_usart0_tdata;
extern volatile uint32_t mock_usart0_rdata;
extern volatile uint32_t mock_usart0_ctl0;
extern volatile uint32_t mock_usart0_baud;
#define USART0_STAT  mock_usart0_stat
#define USART0_TDATA mock_usart0_tdata
#define USART0_RDATA mock_usart0_rdata
#define USART0_CTL0  mock_usart0_ctl0
#define USART0_BAUD  mock_usart0_baud

/* TIMER2 registers */
extern volatile uint32_t mock_timer2_ctl0;
extern volatile uint32_t mock_timer2_swevg;
extern volatile uint32_t mock_timer2_chctl1;
extern volatile uint32_t mock_timer2_chctl2;
extern volatile uint32_t mock_timer2_psc;
extern volatile uint32_t mock_timer2_car;
extern volatile uint32_t mock_timer2_ch2cv;
#define TIMER2_CTL0   mock_timer2_ctl0
#define TIMER2_SWEVG  mock_timer2_swevg
#define TIMER2_CHCTL1 mock_timer2_chctl1
#define TIMER2_CHCTL2 mock_timer2_chctl2
#define TIMER2_PSC    mock_timer2_psc
#define TIMER2_CAR    mock_timer2_car
#define TIMER2_CH2CV  mock_timer2_ch2cv

extern volatile uint32_t mock_rcu_apb1rst;
extern volatile uint32_t mock_rcu_apb2rst;
#define RCU_APB1RST mock_rcu_apb1rst
#define RCU_APB2RST mock_rcu_apb2rst

/* ADC registers */
extern int mock_adc_auto_eoc;
uint32_t *mock_get_adc_ctl1_ptr(void);
extern volatile uint32_t mock_adc_stat;
extern volatile uint32_t mock_adc_ctl1;
extern volatile uint32_t mock_adc_rsq0;
extern volatile uint32_t mock_adc_rsq2;
extern volatile uint32_t mock_adc_rdata;
extern volatile uint32_t mock_adc_sampt1;
#define ADC_STAT mock_adc_stat
#define ADC_CTL1 (*mock_get_adc_ctl1_ptr())
#define ADC_RSQ0 mock_adc_rsq0
#define ADC_RSQ2 mock_adc_rsq2
#define ADC_RDATA mock_adc_rdata
#define ADC_SAMPT1 mock_adc_sampt1

/* FWDGT registers & keys */
extern volatile uint32_t mock_fwdgt_ctl;
extern volatile uint32_t mock_fwdgt_psc;
extern volatile uint32_t mock_fwdgt_rld;
#define FWDGT_CTL mock_fwdgt_ctl
#define FWDGT_PSC mock_fwdgt_psc
#define FWDGT_RLD mock_fwdgt_rld
#define FWDGT_KEY_RELOAD 0xAAAA
#define FWDGT_KEY_ACCESS 0x5555
#define FWDGT_KEY_ENABLE 0xCCCC

/* NVIC registers */
extern volatile uint32_t mock_nvic_iser0;
#define NVIC_ISER0 mock_nvic_iser0

/* Core delay functions */
extern void (*mock_delay_us_hook)(uint32_t us);
extern void (*mock_delay_cycles_hook)(uint32_t cycles);
void delay_ms(uint32_t ms);
void delay_us(uint32_t us);
void delay_cycles(uint32_t cycles);

/* GPIO helpers */
void gpio_cfg_out_pp(uint32_t base, uint8_t pin);
void gpio_cfg_in(uint32_t base, uint8_t pin, uint8_t pud);
int gpio_get(uint32_t base, uint8_t pin);

/* TX capture buffer for UART1 */
#define TX_CAPTURE_MAX 4096
extern uint8_t mock_tx_capture[TX_CAPTURE_MAX];
extern size_t mock_tx_capture_len;
void mock_tx_clear(void);

/* Reset all mocks */
void mock_gd32_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* MOCK_GD32_H */
