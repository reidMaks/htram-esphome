#include <cstring>
#include <string>
#include <vector>

extern "C" {
#include "unity.h"
}

#include "esphome/custom_components/htram_gd32/htram_gd32.cpp"

using namespace esphome;
using namespace esphome::htram_gd32;

class TestableHtramGd32 : public HtramGd32Component {
 public:
  using HtramGd32Component::click_count_;
  using HtramGd32Component::fire_timeout;
  using HtramGd32Component::has_timeout;
  using HtramGd32Component::head_packet_len_;
  using HtramGd32Component::last_batt_mv_;
  using HtramGd32Component::last_status_;
  using HtramGd32Component::led_state_;
  using HtramGd32Component::ota_mode_;
  using HtramGd32Component::process_packet_;
  using HtramGd32Component::pump_rx_;
  using HtramGd32Component::rom_erase;
  using HtramGd32Component::rom_go;
  using HtramGd32Component::rom_send_command;
  using HtramGd32Component::rom_sync;
  using HtramGd32Component::rom_write_memory;
  using HtramGd32Component::rx_buffer_;
};

static TestableHtramGd32* g_comp = nullptr;
static sensor::Sensor* g_co2_s = nullptr;
static sensor::Sensor* g_temp_s = nullptr;
static sensor::Sensor* g_hum_s = nullptr;
static sensor::Sensor* g_batt_s = nullptr;
static sensor::Sensor* g_batt_lvl_s = nullptr;
static text_sensor::TextSensor* g_fw_s = nullptr;
static text_sensor::TextSensor* g_flash_s = nullptr;
static text_sensor::TextSensor* g_btn_act_s = nullptr;
static binary_sensor::BinarySensor* g_usb_s = nullptr;
static binary_sensor::BinarySensor* g_chrg_s = nullptr;
static binary_sensor::BinarySensor* g_btn_s = nullptr;
static switch_::Switch* g_led_sw[3] = {nullptr, nullptr, nullptr};

void setUp(void) {
  mock_esphome_millis = 1000;
  g_comp = new TestableHtramGd32();

  g_co2_s = new sensor::Sensor();
  g_temp_s = new sensor::Sensor();
  g_hum_s = new sensor::Sensor();
  g_batt_s = new sensor::Sensor();
  g_batt_lvl_s = new sensor::Sensor();
  g_fw_s = new text_sensor::TextSensor();
  g_flash_s = new text_sensor::TextSensor();
  g_btn_act_s = new text_sensor::TextSensor();
  g_usb_s = new binary_sensor::BinarySensor();
  g_chrg_s = new binary_sensor::BinarySensor();
  g_btn_s = new binary_sensor::BinarySensor();

  for (int i = 0; i < 3; i++) {
    g_led_sw[i] = new switch_::Switch();
    g_comp->set_led_switch(i, g_led_sw[i]);
  }

  g_comp->set_co2_sensor(g_co2_s);
  g_comp->set_temperature_sensor(g_temp_s);
  g_comp->set_humidity_sensor(g_hum_s);
  g_comp->set_battery_sensor(g_batt_s);
  g_comp->set_battery_level_sensor(g_batt_lvl_s);
  g_comp->set_fw_version_sensor(g_fw_s);
  g_comp->set_spi_flash_sensor(g_flash_s);
  g_comp->set_button_action_sensor(g_btn_act_s);
  g_comp->set_usb_binary_sensor(g_usb_s);
  g_comp->set_charging_binary_sensor(g_chrg_s);
  g_comp->set_button_binary_sensor(g_btn_s);
}

void tearDown(void) {
  delete g_comp;
  delete g_co2_s;
  delete g_temp_s;
  delete g_hum_s;
  delete g_batt_s;
  delete g_batt_lvl_s;
  delete g_fw_s;
  delete g_flash_s;
  delete g_btn_act_s;
  delete g_usb_s;
  delete g_chrg_s;
  delete g_btn_s;
  for (int i = 0; i < 3; i++)
    delete g_led_sw[i];
}

// ---------------------------------------------------------------------------
// 1. Battery Voltage to Percentage Mapping
// ---------------------------------------------------------------------------
void test_batt_mv_to_pct_logic(void) {
  // Clamp low
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, batt_mv_to_pct(3000));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 0.0f, batt_mv_to_pct(3200));

  // Key curve points
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 8.0f, batt_mv_to_pct(3400));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 20.0f, batt_mv_to_pct(3550));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 35.0f, batt_mv_to_pct(3650));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 50.0f, batt_mv_to_pct(3720));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 62.0f, batt_mv_to_pct(3780));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 72.0f, batt_mv_to_pct(3850));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 84.0f, batt_mv_to_pct(3950));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 93.0f, batt_mv_to_pct(4050));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 97.0f, batt_mv_to_pct(4120));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, batt_mv_to_pct(4180));

  // Clamp high
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, batt_mv_to_pct(4200));
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 100.0f, batt_mv_to_pct(4500));

  // Interpolation midpoints
  TEST_ASSERT_FLOAT_WITHIN(0.05f, 4.0f, batt_mv_to_pct(3300));
  TEST_ASSERT_FLOAT_WITHIN(0.05f, 98.5f, batt_mv_to_pct(4150));
}

// ---------------------------------------------------------------------------
// 2. CRC16 CCITT
// ---------------------------------------------------------------------------
void test_crc16_ccitt_vector(void) {
  const uint8_t data[] = "123456789";
  uint16_t crc = crc16_ccitt(data, 9);
  TEST_ASSERT_EQUAL_HEX16(0x31C3, crc);

  TEST_ASSERT_EQUAL_HEX16(0x0000, crc16_ccitt(nullptr, 0));
}

void test_crc32_ieee_vector(void) {
  const uint8_t data[] = "123456789";
  uint32_t crc = crc32_ieee(data, 9);
  TEST_ASSERT_EQUAL_HEX32(0xCBF43926, crc);
  TEST_ASSERT_EQUAL_HEX32(0x00000000, crc32_ieee(nullptr, 0));
}

// ---------------------------------------------------------------------------
// 3. Head Packet Length
// ---------------------------------------------------------------------------
void test_head_packet_len_cases(void) {
  g_comp->rx_buffer_ = {0xAA};
  TEST_ASSERT_EQUAL(0, g_comp->head_packet_len_());
  g_comp->rx_buffer_ = {0xAA, 0x55};
  TEST_ASSERT_EQUAL(0, g_comp->head_packet_len_());

  g_comp->rx_buffer_ = {0xAA, 0x55, 0x01};
  TEST_ASSERT_EQUAL(14, g_comp->head_packet_len_());

  g_comp->rx_buffer_ = {0xAA, 0x55, 0x02};
  TEST_ASSERT_EQUAL(17, g_comp->head_packet_len_());

  g_comp->rx_buffer_ = {0xAA, 0x55, 0x03};
  TEST_ASSERT_EQUAL(8, g_comp->head_packet_len_());

  g_comp->rx_buffer_ = {0xAA, 0x55, 0x04};
  TEST_ASSERT_EQUAL(6, g_comp->head_packet_len_());

  g_comp->rx_buffer_ = {0xAA, 0x55, 0x05};
  TEST_ASSERT_EQUAL(10, g_comp->head_packet_len_());

  g_comp->rx_buffer_ = {0xAA, 0x55, 0x06};
  TEST_ASSERT_EQUAL(11, g_comp->head_packet_len_());

  g_comp->rx_buffer_ = {0xAA, 0x55, 0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00};
  TEST_ASSERT_EQUAL(16, g_comp->head_packet_len_());

  g_comp->rx_buffer_ = {0xAA, 0x55, 0x99, 0x01, 0x02};
  TEST_ASSERT_EQUAL(0, g_comp->head_packet_len_());
  TEST_ASSERT_EQUAL(0, g_comp->rx_buffer_.size());
}

// ---------------------------------------------------------------------------
// 4. Telemetry Packet Parsing
// ---------------------------------------------------------------------------
static std::vector<uint8_t> make_telemetry_pkt(uint16_t co2, int16_t temp, uint16_t hum, uint16_t batt_mv,
                                               uint8_t status) {
  std::vector<uint8_t> pkt(14);
  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  pkt[2] = 0x01;  // type
  pkt[3] = co2 & 0xFF;
  pkt[4] = co2 >> 8;
  pkt[5] = temp & 0xFF;
  pkt[6] = temp >> 8;
  pkt[7] = hum & 0xFF;
  pkt[8] = hum >> 8;
  pkt[9] = batt_mv & 0xFF;
  pkt[10] = batt_mv >> 8;
  pkt[11] = status;
  uint16_t crc = crc16_ccitt(pkt.data() + 2, 10);
  pkt[12] = crc & 0xFF;
  pkt[13] = crc >> 8;
  return pkt;
}

void test_telemetry_packet_parsing_normal(void) {
  auto pkt = make_telemetry_pkt(800, 2350, 4520, 3950, 0x43);
  g_comp->process_packet_(pkt.data(), pkt.size());

  TEST_ASSERT_TRUE(g_co2_s->has_state);
  TEST_ASSERT_FLOAT_WITHIN(0.1f, 800.0f, g_co2_s->state);

  TEST_ASSERT_TRUE(g_temp_s->has_state);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 23.50f, g_temp_s->state);

  TEST_ASSERT_TRUE(g_hum_s->has_state);
  TEST_ASSERT_FLOAT_WITHIN(0.01f, 45.20f, g_hum_s->state);

  TEST_ASSERT_TRUE(g_batt_s->has_state);
  TEST_ASSERT_FLOAT_WITHIN(0.1f, 3950.0f, g_batt_s->state);

  TEST_ASSERT_TRUE(g_batt_lvl_s->has_state);
  TEST_ASSERT_FLOAT_WITHIN(0.1f, 84.0f, g_batt_lvl_s->state);

  TEST_ASSERT_TRUE(g_usb_s->has_state);
  TEST_ASSERT_TRUE(g_usb_s->state);

  TEST_ASSERT_TRUE(g_chrg_s->has_state);
  TEST_ASSERT_TRUE(g_chrg_s->state);

  TEST_ASSERT_FALSE(g_led_sw[0]->state);
  TEST_ASSERT_TRUE(g_led_sw[1]->state);
  TEST_ASSERT_FALSE(g_led_sw[2]->state);
}

void test_telemetry_packet_corrupt_crc(void) {
  auto pkt = make_telemetry_pkt(800, 2350, 4520, 3950, 0x43);
  pkt[12] ^= 0xFF;  // corrupt CRC
  g_comp->process_packet_(pkt.data(), pkt.size());

  TEST_ASSERT_FALSE(g_co2_s->has_state);
  TEST_ASSERT_FALSE(g_temp_s->has_state);
}

void test_telemetry_packet_flags_suppression(void) {
  auto pkt1 = make_telemetry_pkt(800, 2350, 4520, 3950, 0x08);
  g_comp->process_packet_(pkt1.data(), pkt1.size());
  TEST_ASSERT_TRUE(g_co2_s->has_state);
  TEST_ASSERT_FALSE(g_temp_s->has_state);
  TEST_ASSERT_FALSE(g_hum_s->has_state);

  g_co2_s->has_state = false;
  auto pkt2 = make_telemetry_pkt(800, 2350, 4520, 3950, 0x04);
  g_comp->process_packet_(pkt2.data(), pkt2.size());
  TEST_ASSERT_FALSE(g_co2_s->has_state);

  auto pkt3 = make_telemetry_pkt(0xFFFF, 2350, 4520, 3950, 0x00);
  g_comp->process_packet_(pkt3.data(), pkt3.size());
  TEST_ASSERT_FALSE(g_co2_s->has_state);
}

// ---------------------------------------------------------------------------
// 5. Hello Packet Parsing
// ---------------------------------------------------------------------------
static std::vector<uint8_t> make_hello_pkt(uint8_t proto_ver, uint16_t fw_ver, uint8_t flags, uint32_t epoch,
                                           uint32_t git) {
  std::vector<uint8_t> pkt(17);
  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  pkt[2] = 0x02;  // type
  pkt[3] = proto_ver;
  pkt[4] = fw_ver & 0xFF;
  pkt[5] = fw_ver >> 8;
  pkt[6] = flags;
  pkt[7] = epoch & 0xFF;
  pkt[8] = (epoch >> 8) & 0xFF;
  pkt[9] = (epoch >> 16) & 0xFF;
  pkt[10] = (epoch >> 24) & 0xFF;
  pkt[11] = git & 0xFF;
  pkt[12] = (git >> 8) & 0xFF;
  pkt[13] = (git >> 16) & 0xFF;
  pkt[14] = (git >> 24) & 0xFF;
  uint16_t crc = crc16_ccitt(pkt.data() + 2, 13);
  pkt[15] = crc & 0xFF;
  pkt[16] = crc >> 8;
  return pkt;
}

void test_hello_packet_parsing(void) {
  auto pkt = make_hello_pkt(1, 0x0123, 0x03, 1715000000, 0xABCDEF01);
  g_comp->process_packet_(pkt.data(), pkt.size());

  TEST_ASSERT_TRUE(g_fw_s->has_state);
  TEST_ASSERT_NOT_NULL(strstr(g_fw_s->state.c_str(), "1.2.3"));
  TEST_ASSERT_NOT_NULL(strstr(g_fw_s->state.c_str(), "+"));

  TEST_ASSERT_TRUE(g_comp->consume_gd32_boot());
  TEST_ASSERT_FALSE(g_comp->consume_gd32_boot());
}

static std::vector<uint8_t> make_flash_info_pkt(uint8_t is_det, uint8_t mfg, uint8_t type, uint8_t cap,
                                                uint8_t status1) {
  std::vector<uint8_t> pkt(10);
  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  pkt[2] = 0x05;
  pkt[3] = is_det;
  pkt[4] = mfg;
  pkt[5] = type;
  pkt[6] = cap;
  pkt[7] = status1;
  uint16_t crc = crc16_ccitt(pkt.data() + 2, 6);
  pkt[8] = crc & 0xFF;
  pkt[9] = crc >> 8;
  return pkt;
}

void test_flash_info_packet_parsing(void) {
  auto pkt = make_flash_info_pkt(1, 0xEF, 0x40, 0x16, 0x00);
  g_comp->process_packet_(pkt.data(), pkt.size());

  TEST_ASSERT_TRUE(g_flash_s->has_state);
  TEST_ASSERT_NOT_NULL(strstr(g_flash_s->state.c_str(), "W25Q32 4MB"));
  TEST_ASSERT_NOT_NULL(strstr(g_flash_s->state.c_str(), "EF 40 16"));

  auto pkt_fail = make_flash_info_pkt(0, 0x00, 0x00, 0x00, 0x00);
  g_comp->process_packet_(pkt_fail.data(), pkt_fail.size());
  TEST_ASSERT_NOT_NULL(strstr(g_flash_s->state.c_str(), "Not detected"));
}

static std::vector<uint8_t> make_flash_ack_pkt(uint8_t cmd, uint8_t status, uint32_t addr) {
  std::vector<uint8_t> pkt(11);
  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  pkt[2] = 0x06;
  pkt[3] = cmd;
  pkt[4] = status;
  pkt[5] = addr & 0xFF;
  pkt[6] = (addr >> 8) & 0xFF;
  pkt[7] = (addr >> 16) & 0xFF;
  pkt[8] = (addr >> 24) & 0xFF;
  uint16_t crc = crc16_ccitt(pkt.data() + 2, 7);
  pkt[9] = crc & 0xFF;
  pkt[10] = crc >> 8;
  return pkt;
}

void test_flash_ack_packet_parsing(void) {
  auto pkt = make_flash_ack_pkt(0x21, 0x00, 0x00001000);
  g_comp->process_packet_(pkt.data(), pkt.size());

  TEST_ASSERT_EQUAL_HEX8(0x21, g_comp->last_flash_ack_cmd());
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->last_flash_ack_status());
  TEST_ASSERT_EQUAL_HEX32(0x00001000, g_comp->last_flash_ack_addr());
}

static std::vector<uint8_t> make_flash_data_pkt(uint8_t status, uint32_t addr, const std::vector<uint8_t>& payload) {
  std::vector<uint8_t> pkt(12 + payload.size());
  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  pkt[2] = 0x07;
  pkt[3] = status;
  pkt[4] = addr & 0xFF;
  pkt[5] = (addr >> 8) & 0xFF;
  pkt[6] = (addr >> 16) & 0xFF;
  pkt[7] = (addr >> 24) & 0xFF;
  uint16_t len = payload.size();
  pkt[8] = len & 0xFF;
  pkt[9] = (len >> 8) & 0xFF;
  std::copy(payload.begin(), payload.end(), pkt.begin() + 10);
  uint16_t crc = crc16_ccitt(pkt.data() + 2, 8 + len);
  pkt[10 + len] = crc & 0xFF;
  pkt[11 + len] = crc >> 8;
  return pkt;
}

void test_flash_data_packet_parsing(void) {
  std::vector<uint8_t> test_bytes = {0xDE, 0xAD, 0xBE, 0xEF, 0x42};
  auto pkt = make_flash_data_pkt(0x00, 0x00002000, test_bytes);
  g_comp->process_packet_(pkt.data(), pkt.size());

  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->last_flash_read_status());
  TEST_ASSERT_EQUAL_HEX32(0x00002000, g_comp->last_flash_read_addr());
  TEST_ASSERT_EQUAL(5, g_comp->last_flash_read_data().size());
  TEST_ASSERT_EQUAL_UINT8_ARRAY(test_bytes.data(), g_comp->last_flash_read_data().data(), 5);
}

// ---------------------------------------------------------------------------
// 6. Flow Control Packets
// ---------------------------------------------------------------------------
static std::vector<uint8_t> make_flow_pkt(uint8_t resume) {
  std::vector<uint8_t> pkt(6);
  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  pkt[2] = 0x04;
  pkt[3] = resume;
  uint16_t crc = crc16_ccitt(pkt.data() + 2, 2);
  pkt[4] = crc & 0xFF;
  pkt[5] = crc >> 8;
  return pkt;
}

void test_flow_control_packet(void) {
  TEST_ASSERT_FALSE(g_comp->flow_paused());

  auto pause_pkt = make_flow_pkt(0);
  g_comp->process_packet_(pause_pkt.data(), pause_pkt.size());
  TEST_ASSERT_TRUE(g_comp->flow_paused());

  auto resume_pkt = make_flow_pkt(1);
  g_comp->process_packet_(resume_pkt.data(), resume_pkt.size());
  TEST_ASSERT_FALSE(g_comp->flow_paused());
}

void test_wait_for_flow_unpauses_or_times_out(void) {
  g_comp->wait_for_flow(100);
  TEST_ASSERT_FALSE(g_comp->flow_paused());

  auto pause_pkt = make_flow_pkt(0);
  g_comp->process_packet_(pause_pkt.data(), pause_pkt.size());
  TEST_ASSERT_TRUE(g_comp->flow_paused());

  auto resume_pkt = make_flow_pkt(1);
  g_comp->mock_push_rx(resume_pkt.data(), resume_pkt.size());

  g_comp->wait_for_flow(100);
  TEST_ASSERT_FALSE(g_comp->flow_paused());

  g_comp->process_packet_(pause_pkt.data(), pause_pkt.size());
  TEST_ASSERT_TRUE(g_comp->flow_paused());
  g_comp->wait_for_flow(50);
  TEST_ASSERT_FALSE(g_comp->flow_paused());
}

// ---------------------------------------------------------------------------
// 7. Button Events State Machine
// ---------------------------------------------------------------------------
static std::vector<uint8_t> make_btn_pkt(uint8_t state, uint16_t dur_ms) {
  std::vector<uint8_t> pkt(8);
  pkt[0] = 0xAA;
  pkt[1] = 0x55;
  pkt[2] = 0x03;
  pkt[3] = state;
  pkt[4] = dur_ms & 0xFF;
  pkt[5] = dur_ms >> 8;
  uint16_t crc = crc16_ccitt(pkt.data() + 2, 4);
  pkt[6] = crc & 0xFF;
  pkt[7] = crc >> 8;
  return pkt;
}

void test_button_pressed_and_long_press(void) {
  auto p_down = make_btn_pkt(1, 0);
  g_comp->process_packet_(p_down.data(), p_down.size());
  TEST_ASSERT_TRUE(g_btn_s->has_state);
  TEST_ASSERT_TRUE(g_btn_s->state);

  auto p_up = make_btn_pkt(0, 1200);
  g_comp->process_packet_(p_up.data(), p_up.size());
  TEST_ASSERT_FALSE(g_btn_s->state);
  TEST_ASSERT_EQUAL_STRING("long", g_btn_act_s->state.c_str());

  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_clear"));
  TEST_ASSERT_EQUAL_STRING("", g_btn_act_s->state.c_str());
}

void test_button_click_sequences(void) {
  auto p_click = make_btn_pkt(0, 150);
  g_comp->process_packet_(p_click.data(), p_click.size());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_click"));
  TEST_ASSERT_EQUAL_STRING("single", g_btn_act_s->state.c_str());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_clear"));
  TEST_ASSERT_EQUAL_STRING("", g_btn_act_s->state.c_str());

  g_comp->process_packet_(p_click.data(), p_click.size());
  g_comp->process_packet_(p_click.data(), p_click.size());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_click"));
  TEST_ASSERT_EQUAL_STRING("double", g_btn_act_s->state.c_str());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_clear"));

  g_comp->process_packet_(p_click.data(), p_click.size());
  g_comp->process_packet_(p_click.data(), p_click.size());
  g_comp->process_packet_(p_click.data(), p_click.size());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_click"));
  TEST_ASSERT_EQUAL_STRING("triple", g_btn_act_s->state.c_str());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_clear"));

  for (int i = 0; i < 4; i++)
    g_comp->process_packet_(p_click.data(), p_click.size());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_click"));
  TEST_ASSERT_EQUAL_STRING("quadruple", g_btn_act_s->state.c_str());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_clear"));

  for (int i = 0; i < 5; i++)
    g_comp->process_packet_(p_click.data(), p_click.size());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_click"));
  TEST_ASSERT_EQUAL_STRING("many", g_btn_act_s->state.c_str());
  TEST_ASSERT_TRUE(g_comp->fire_timeout("button_clear"));

  auto p_glitch = make_btn_pkt(0, 15);
  g_btn_act_s->state = "init";
  g_comp->process_packet_(p_glitch.data(), p_glitch.size());
  TEST_ASSERT_FALSE(g_comp->has_timeout("button_click"));
  TEST_ASSERT_EQUAL_STRING("init", g_btn_act_s->state.c_str());
}

// ---------------------------------------------------------------------------
// 8. Rx Pump and Resync, loop, and ota_mode suppression
// ---------------------------------------------------------------------------
void test_pump_rx_resync_and_dispatch(void) {
  uint8_t garbage[] = {0x12, 0x34, 0xAA, 0x00, 0x99};
  auto telem = make_telemetry_pkt(950, 2100, 5000, 4000, 0x02);
  g_comp->mock_push_rx(garbage, sizeof(garbage));
  g_comp->mock_push_rx(telem.data(), telem.size());

  g_comp->loop();  // calls pump_rx_(false)

  TEST_ASSERT_TRUE(g_co2_s->has_state);
  TEST_ASSERT_FLOAT_WITHIN(0.1f, 950.0f, g_co2_s->state);

  // When ota_mode_ is true, pump_rx_ returns early
  g_comp->ota_mode_ = true;
  g_co2_s->has_state = false;
  g_comp->mock_push_rx(telem.data(), telem.size());
  g_comp->loop();
  TEST_ASSERT_FALSE(g_co2_s->has_state);
  g_comp->ota_mode_ = false;
}

// ---------------------------------------------------------------------------
// 9. Outgoing Command Packets
// ---------------------------------------------------------------------------
void test_outgoing_commands(void) {
  g_comp->mock_clear_tx();
  g_comp->send_beep(1000, 50);
  TEST_ASSERT_EQUAL(9, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0xAA, g_comp->mock_tx_bytes[0]);
  TEST_ASSERT_EQUAL_HEX8(0x55, g_comp->mock_tx_bytes[1]);
  TEST_ASSERT_EQUAL_HEX8(0x13, g_comp->mock_tx_bytes[2]);

  g_comp->mock_clear_tx();
  g_comp->send_backlight(80);
  TEST_ASSERT_EQUAL(6, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x11, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(80, g_comp->mock_tx_bytes[3]);

  g_comp->mock_clear_tx();
  g_comp->send_leds(1, 0, 1, 1);
  TEST_ASSERT_EQUAL(9, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x12, g_comp->mock_tx_bytes[2]);

  g_comp->mock_clear_tx();
  g_comp->set_led(0, true);
  TEST_ASSERT_TRUE(g_comp->led_state_[0]);
  TEST_ASSERT_EQUAL(9, g_comp->mock_tx_bytes.size());

  // Ignored out-of-range channel
  g_comp->mock_clear_tx();
  g_comp->set_led(5, true);
  TEST_ASSERT_EQUAL(0, g_comp->mock_tx_bytes.size());

  g_comp->mock_clear_tx();
  g_comp->send_stop();
  TEST_ASSERT_EQUAL(6, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x14, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[3]);

  g_comp->mock_clear_tx();
  g_comp->send_get_flash_info();
  TEST_ASSERT_EQUAL(5, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x20, g_comp->mock_tx_bytes[2]);

  g_comp->mock_clear_tx();
  g_comp->send_enter_bootloader();
  TEST_ASSERT_EQUAL(9, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x1F, g_comp->mock_tx_bytes[2]);

  g_comp->mock_clear_tx();
  uint8_t pix[4] = {0x11, 0x22, 0x33, 0x44};
  g_comp->send_draw_rect(10, 20, 2, 1, pix, 4);
  TEST_ASSERT_EQUAL(15, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x10, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL(10, g_comp->mock_tx_bytes[3]);
  TEST_ASSERT_EQUAL(20, g_comp->mock_tx_bytes[4]);

  g_comp->mock_clear_tx();
  g_comp->send_flash_erase_sector(0x00001000);
  TEST_ASSERT_EQUAL(9, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0xAA, g_comp->mock_tx_bytes[0]);
  TEST_ASSERT_EQUAL_HEX8(0x55, g_comp->mock_tx_bytes[1]);
  TEST_ASSERT_EQUAL_HEX8(0x21, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[3]);
  TEST_ASSERT_EQUAL_HEX8(0x10, g_comp->mock_tx_bytes[4]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[5]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[6]);

  g_comp->mock_clear_tx();
  g_comp->send_flash_erase_block(0x00010000);
  TEST_ASSERT_EQUAL(9, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x24, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[3]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[4]);
  TEST_ASSERT_EQUAL_HEX8(0x01, g_comp->mock_tx_bytes[5]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[6]);

  g_comp->mock_clear_tx();
  uint8_t wdata[4] = {1, 2, 3, 4};
  g_comp->send_flash_write_chunk(0x00001000, wdata, 4);
  TEST_ASSERT_EQUAL(15, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x22, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[3]);
  TEST_ASSERT_EQUAL_HEX8(0x10, g_comp->mock_tx_bytes[4]);
  TEST_ASSERT_EQUAL_HEX8(4, g_comp->mock_tx_bytes[7]);
  TEST_ASSERT_EQUAL_HEX8(0, g_comp->mock_tx_bytes[8]);
  TEST_ASSERT_EQUAL_HEX8(1, g_comp->mock_tx_bytes[9]);
  TEST_ASSERT_EQUAL_HEX8(4, g_comp->mock_tx_bytes[12]);

  // Zero-length or oversized write chunk ignored
  g_comp->mock_clear_tx();
  g_comp->send_flash_write_chunk(0x00001000, wdata, 0);
  TEST_ASSERT_EQUAL(0, g_comp->mock_tx_bytes.size());
  uint8_t big_chunk[257];
  g_comp->send_flash_write_chunk(0x00001000, big_chunk, 257);
  TEST_ASSERT_EQUAL(0, g_comp->mock_tx_bytes.size());

  g_comp->mock_clear_tx();
  g_comp->send_flash_verify_crc(0x00001000, 256, 0x12345678);
  TEST_ASSERT_EQUAL(17, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x23, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[3]);
  TEST_ASSERT_EQUAL_HEX8(0x10, g_comp->mock_tx_bytes[4]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[7]);
  TEST_ASSERT_EQUAL_HEX8(0x01, g_comp->mock_tx_bytes[8]);
  TEST_ASSERT_EQUAL_HEX8(0x78, g_comp->mock_tx_bytes[11]);
  TEST_ASSERT_EQUAL_HEX8(0x56, g_comp->mock_tx_bytes[12]);
  TEST_ASSERT_EQUAL_HEX8(0x34, g_comp->mock_tx_bytes[13]);
  TEST_ASSERT_EQUAL_HEX8(0x12, g_comp->mock_tx_bytes[14]);

  g_comp->mock_clear_tx();
  g_comp->send_flash_read(0x00001000, 64);
  TEST_ASSERT_EQUAL(11, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x25, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(0x00, g_comp->mock_tx_bytes[3]);
  TEST_ASSERT_EQUAL_HEX8(0x10, g_comp->mock_tx_bytes[4]);
  TEST_ASSERT_EQUAL_HEX8(64, g_comp->mock_tx_bytes[7]);
  TEST_ASSERT_EQUAL_HEX8(0, g_comp->mock_tx_bytes[8]);

  g_comp->mock_clear_tx();
  g_comp->send_flash_backup_fw(1);
  TEST_ASSERT_EQUAL(6, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x26, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(0x01, g_comp->mock_tx_bytes[3]);

  g_comp->mock_clear_tx();
  g_comp->send_flash_confirm_boot();
  TEST_ASSERT_EQUAL(5, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x27, g_comp->mock_tx_bytes[2]);

  g_comp->mock_clear_tx();
  g_comp->send_flash_restore_fw(1);
  TEST_ASSERT_EQUAL(10, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x28, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL_HEX8(0x01, g_comp->mock_tx_bytes[3]);
  TEST_ASSERT_EQUAL_HEX8(0xEF, g_comp->mock_tx_bytes[4]);
  TEST_ASSERT_EQUAL_HEX8(0xBE, g_comp->mock_tx_bytes[5]);
  TEST_ASSERT_EQUAL_HEX8(0xAD, g_comp->mock_tx_bytes[6]);
  TEST_ASSERT_EQUAL_HEX8(0xDE, g_comp->mock_tx_bytes[7]);

  class TestableLedSwitch : public HtramLedSwitch {
   public:
    using HtramLedSwitch::write_state;
  };
  TestableLedSwitch led_sw;
  led_sw.set_parent(g_comp);
  led_sw.set_channel(1);
  led_sw.write_state(true);
  TEST_ASSERT_TRUE(led_sw.state);
}

// ---------------------------------------------------------------------------
// 10. RTTTL Parser
// ---------------------------------------------------------------------------
void test_rtttl_parser_notes_and_durations(void) {
  g_comp->mock_clear_tx();
  g_comp->play_rtttl("Scale:d=4,o=5,b=120:c,d,e,f,g,a,b,c6");
  TEST_ASSERT_GREATER_THAN(0, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x14, g_comp->mock_tx_bytes[2]);
  TEST_ASSERT_EQUAL(8, g_comp->mock_tx_bytes[3]);

  g_comp->mock_clear_tx();
  g_comp->play_rtttl("Tune:d=8,o=4,b=100:c#,d.,p,16f#,@");
  TEST_ASSERT_GREATER_THAN(0, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL(4, g_comp->mock_tx_bytes[3]);

  // Frequency boundary shifting
  g_comp->mock_clear_tx();
  g_comp->play_rtttl("Extremes:d=4,o=1,b=60:c,c8");
  TEST_ASSERT_GREATER_THAN(0, g_comp->mock_tx_bytes.size());

  // Bad syntax
  g_comp->mock_clear_tx();
  g_comp->play_rtttl("NoColons");
  TEST_ASSERT_EQUAL(0, g_comp->mock_tx_bytes.size());

  g_comp->play_rtttl("OneColon:d=4");
  TEST_ASSERT_EQUAL(0, g_comp->mock_tx_bytes.size());

  g_comp->play_rtttl("EmptyNotes:d=4,o=5,b=120:");
  TEST_ASSERT_EQUAL(0, g_comp->mock_tx_bytes.size());
}

// ---------------------------------------------------------------------------
// 11. ROM Bootloader primitives
// ---------------------------------------------------------------------------
void test_rom_bootloader_primitives(void) {
  // rom_sync: 0x79 -> true, 0x1F -> true, other -> false
  g_comp->mock_clear_rx();
  g_comp->on_write = [](const uint8_t* data, size_t len) {
    if (len == 1 && data[0] == 0x7F) {
      g_comp->mock_push_rx_byte(0x79);
    }
  };
  TEST_ASSERT_TRUE(g_comp->rom_sync(1));

  g_comp->mock_clear_rx();
  g_comp->on_write = [](const uint8_t* data, size_t len) {
    if (len == 1 && data[0] == 0x7F) {
      g_comp->mock_push_rx_byte(0x1F);
    }
  };
  TEST_ASSERT_TRUE(g_comp->rom_sync(2));

  g_comp->mock_clear_rx();
  g_comp->on_write = [](const uint8_t* data, size_t len) {
    if (len == 1 && data[0] == 0x7F) {
      g_comp->mock_push_rx_byte(0x00);
    }
  };
  TEST_ASSERT_FALSE(g_comp->rom_sync(3));

  g_comp->mock_clear_rx();
  g_comp->on_write = nullptr;
  TEST_ASSERT_FALSE(g_comp->rom_sync(4));  // timeout

  // rom_send_command: 0x79 -> true, other -> false
  g_comp->mock_clear_rx();
  g_comp->mock_push_rx_byte(0x79);
  TEST_ASSERT_TRUE(g_comp->rom_send_command(0x43));

  g_comp->mock_clear_rx();
  g_comp->mock_push_rx_byte(0x1F);
  TEST_ASSERT_FALSE(g_comp->rom_send_command(0x43));

  // rom_erase: command 0x43 ACKed + mass erase ACKed
  std::string err;
  g_comp->mock_clear_rx();
  g_comp->mock_push_rx_byte(0x79);  // ACK for 0x43
  g_comp->mock_push_rx_byte(0x79);  // ACK for mass erase
  TEST_ASSERT_TRUE(g_comp->rom_erase(err));

  g_comp->mock_clear_rx();
  g_comp->mock_push_rx_byte(0x79);  // ACK for 0x43
  g_comp->mock_push_rx_byte(0x1F);  // NACK for mass erase
  TEST_ASSERT_FALSE(g_comp->rom_erase(err));

  // rom_write_memory: invalid length
  uint8_t buf[260] = {0};
  TEST_ASSERT_FALSE(g_comp->rom_write_memory(0x08000000, buf, 0, err));
  TEST_ASSERT_FALSE(g_comp->rom_write_memory(0x08000000, buf, 3, err));
  TEST_ASSERT_FALSE(g_comp->rom_write_memory(0x08000000, buf, 260, err));

  // Valid length 4, all ACKed
  g_comp->mock_clear_rx();
  g_comp->mock_push_rx_byte(0x79);  // cmd 0x31
  g_comp->mock_push_rx_byte(0x79);  // addr
  g_comp->mock_push_rx_byte(0x79);  // data
  TEST_ASSERT_TRUE(g_comp->rom_write_memory(0x08000000, buf, 4, err));

  // Address rejected
  g_comp->mock_clear_rx();
  g_comp->mock_push_rx_byte(0x79);  // cmd 0x31
  g_comp->mock_push_rx_byte(0x1F);  // addr NACK
  TEST_ASSERT_FALSE(g_comp->rom_write_memory(0x08000000, buf, 4, err));

  // rom_go: cmd 0x21 + addr ACKed
  g_comp->mock_clear_rx();
  g_comp->mock_push_rx_byte(0x79);
  g_comp->mock_push_rx_byte(0x79);
  TEST_ASSERT_TRUE(g_comp->rom_go(0x08000000));

  g_comp->mock_clear_rx();
  g_comp->mock_push_rx_byte(0x79);
  g_comp->mock_push_rx_byte(0x1F);  // addr rejected
  TEST_ASSERT_FALSE(g_comp->rom_go(0x08000000));
}

// ---------------------------------------------------------------------------
// 12. OTA Safety Gates and Full Simulated Execution
// ---------------------------------------------------------------------------
void test_execute_ota_safety_gates(void) {
  std::vector<uint8_t> fw(128, 0xAA);

  // 1. Battery too low (< 3500 mV)
  g_comp->last_batt_mv_ = 3400;
  g_comp->last_status_ = 0x02;  // USB present
  std::string res1 = g_comp->execute_ota(fw, false);
  TEST_ASSERT_NOT_NULL(strstr(res1.c_str(), "battery too low"));

  // 2. On battery and allow_on_battery == false
  g_comp->last_batt_mv_ = 3900;
  g_comp->last_status_ = 0x00;  // No USB
  std::string res2 = g_comp->execute_ota(fw, false);
  TEST_ASSERT_NOT_NULL(strstr(res2.c_str(), "no USB power"));

  // 3. Invalid image size (0 or > 65536)
  std::vector<uint8_t> empty_fw;
  g_comp->last_status_ = 0x02;  // USB present
  std::string res3 = g_comp->execute_ota(empty_fw, false);
  TEST_ASSERT_NOT_NULL(strstr(res3.c_str(), "invalid firmware size"));

  std::vector<uint8_t> huge_fw(70000, 0x00);
  std::string res4 = g_comp->execute_ota(huge_fw, false);
  TEST_ASSERT_NOT_NULL(strstr(res4.c_str(), "invalid firmware size"));

  // 4. Allowed on battery: proceeds past safety gate to rom_sync, then fails sync cleanly
  std::string res5 = g_comp->execute_ota(fw, true);
  TEST_ASSERT_NOT_NULL(strstr(res5.c_str(), "rom_sync"));
  TEST_ASSERT_FALSE(g_comp->ota_mode_);

  // 5. Full successful OTA flash simulation
  g_comp->last_batt_mv_ = 4000;
  g_comp->last_status_ = 0x02;  // USB present
  g_comp->mock_clear_rx();
  g_comp->on_write = [](const uint8_t* data, size_t len) {
    if (len == 9 && data[2] == 0x1F) {
      uint8_t ack[] = {0xAA, 0x55, 0x1F, 0x79};
      g_comp->mock_push_rx(ack, 4);
    } else {
      g_comp->mock_push_rx_byte(0x79);
    }
  };

  std::string res6 = g_comp->execute_ota(fw, true);
  TEST_ASSERT_NOT_NULL(strstr(res6.c_str(), "\"result\":\"ok\""));
  TEST_ASSERT_FALSE(g_comp->ota_mode_);
  g_comp->on_write = nullptr;
}

void test_execute_ota_with_spi_flash_success(void) {
  std::vector<uint8_t> fw(256, 0x5A);
  g_comp->last_batt_mv_ = 4000;
  g_comp->last_status_ = 0x02;  // USB present
  g_comp->mock_clear_rx();

  // Set SPI flash as detected
  auto info_pkt = make_flash_info_pkt(1, 0xEF, 0x40, 0x16, 0x00);
  g_comp->process_packet_(info_pkt.data(), info_pkt.size());

  g_comp->on_write = [](const uint8_t* data, size_t len) {
    if (len >= 3 && data[2] == 0x26) {
      // Flash backup fw command ack
      auto ack = make_flash_ack_pkt(0x26, 0x00, 0x11223344);
      g_comp->mock_push_rx(ack.data(), ack.size());
    } else if (len >= 3 && data[2] == 0x23) {
      // Flash verify crc command ack
      auto ack = make_flash_ack_pkt(0x23, 0x00, 0x00030000);
      g_comp->mock_push_rx(ack.data(), ack.size());
    } else if (len == 9 && data[2] == 0x1F) {
      uint8_t ack[] = {0xAA, 0x55, 0x1F, 0x79};
      g_comp->mock_push_rx(ack, 4);
    } else {
      g_comp->mock_push_rx_byte(0x79);
    }
  };

  std::string res = g_comp->execute_ota(fw, true);
  TEST_ASSERT_NOT_NULL(strstr(res.c_str(), "\"result\":\"ok\""));
  TEST_ASSERT_FALSE(g_comp->ota_mode_);
  g_comp->on_write = nullptr;

  auto info_reset = make_flash_info_pkt(0, 0x00, 0x00, 0x00, 0x00);
  g_comp->process_packet_(info_reset.data(), info_reset.size());
}

void test_execute_ota_with_spi_flash_staging_failure(void) {
  std::vector<uint8_t> fw(256, 0x5A);
  g_comp->last_batt_mv_ = 4000;
  g_comp->last_status_ = 0x02;  // USB present
  g_comp->mock_clear_rx();

  // Set SPI flash as detected
  auto info_pkt = make_flash_info_pkt(1, 0xEF, 0x40, 0x16, 0x00);
  g_comp->process_packet_(info_pkt.data(), info_pkt.size());

  g_comp->on_write = [](const uint8_t* data, size_t len) {
    if (len >= 3 && data[2] == 0x26) {
      auto ack = make_flash_ack_pkt(0x26, 0x00, 0x11223344);
      g_comp->mock_push_rx(ack.data(), ack.size());
    } else if (len >= 3 && data[2] == 0x23) {
      // Staging CRC verify fails!
      auto ack = make_flash_ack_pkt(0x23, 0x03, 0x00030000);
      g_comp->mock_push_rx(ack.data(), ack.size());
    }
  };

  std::string res = g_comp->execute_ota(fw, true);
  TEST_ASSERT_NOT_NULL(strstr(res.c_str(), "\"stage\":\"staging_verify\""));
  TEST_ASSERT_NOT_NULL(strstr(res.c_str(), "\"result\":\"error\""));
  TEST_ASSERT_FALSE(g_comp->ota_mode_);
  g_comp->on_write = nullptr;

  auto info_reset = make_flash_info_pkt(0, 0x00, 0x00, 0x00, 0x00);
  g_comp->process_packet_(info_reset.data(), info_reset.size());
}

// ---------------------------------------------------------------------------
// 13. Display Methods
// ---------------------------------------------------------------------------
void test_display_pixel_drawing(void) {
  HtramGd32Display disp;
  disp.set_parent(g_comp);
  disp.update();
  TEST_ASSERT_EQUAL(display::DISPLAY_TYPE_COLOR, disp.get_display_type());

  g_comp->mock_clear_tx();
  disp.draw_pixel_at(-1, 0, Color(255, 0, 0));
  disp.draw_pixel_at(240, 10, Color(255, 0, 0));
  TEST_ASSERT_EQUAL(0, g_comp->mock_tx_bytes.size());

  disp.draw_pixel_at(10, 20, Color(255, 255, 255));
  TEST_ASSERT_GREATER_THAN(0, g_comp->mock_tx_bytes.size());
  TEST_ASSERT_EQUAL_HEX8(0x10, g_comp->mock_tx_bytes[2]);

  // draw_pixels_at with big_endian = true
  g_comp->mock_clear_tx();
  uint8_t test_pixels[16] = {0};
  disp.draw_pixels_at(0, 0, 2, 2, test_pixels, display::COLOR_ORDER_RGB, display::COLOR_BITNESS_565, true, 0, 0, 0);
  TEST_ASSERT_GREATER_THAN(0, g_comp->mock_tx_bytes.size());

  // draw_pixels_at with big_endian = false (exercises little-endian byte swapping)
  g_comp->mock_clear_tx();
  disp.draw_pixels_at(0, 0, 2, 2, test_pixels, display::COLOR_ORDER_RGB, display::COLOR_BITNESS_565, false, 0, 0, 0);
  TEST_ASSERT_GREATER_THAN(0, g_comp->mock_tx_bytes.size());
}

// ---------------------------------------------------------------------------
// 14. OTA Web Handler
// ---------------------------------------------------------------------------
void test_ota_web_handler(void) {
  Gd32OtaHandler handler(g_comp);
  AsyncWebServerRequest req;

  TEST_ASSERT_TRUE(handler.canHandle(&req));

  // Upload simulation
  uint8_t chunk[64] = {0xAA};
  handler.handleUpload(&req, "firmware.bin", 0, chunk, sizeof(chunk), false);
  handler.handleUpload(&req, "firmware.bin", 64, chunk, sizeof(chunk), true);

  handler.handleRequest(&req);

  // Empty firmware request error handling
  Gd32OtaHandler empty_handler(g_comp);
  empty_handler.handleRequest(&req);
}

// ---------------------------------------------------------------------------
// 15. Setup and Dump Config
// ---------------------------------------------------------------------------
void test_setup_and_dump_config(void) {
  g_comp->dump_config();
  HtramGd32Display disp;
  disp.dump_config();

  esphome::web_server_base::global_web_server_base = nullptr;
  g_comp->setup();

  esphome::web_server_base::WebServerBase srv;
  esphome::web_server_base::global_web_server_base = &srv;
  g_comp->setup();
  TEST_ASSERT_EQUAL(1, srv.handlers.size());
}

int main(void) {
  UNITY_BEGIN();
  RUN_TEST(test_batt_mv_to_pct_logic);
  RUN_TEST(test_crc16_ccitt_vector);
  RUN_TEST(test_crc32_ieee_vector);
  RUN_TEST(test_head_packet_len_cases);
  RUN_TEST(test_telemetry_packet_parsing_normal);
  RUN_TEST(test_telemetry_packet_corrupt_crc);
  RUN_TEST(test_telemetry_packet_flags_suppression);
  RUN_TEST(test_hello_packet_parsing);
  RUN_TEST(test_flash_info_packet_parsing);
  RUN_TEST(test_flash_ack_packet_parsing);
  RUN_TEST(test_flash_data_packet_parsing);
  RUN_TEST(test_flow_control_packet);
  RUN_TEST(test_wait_for_flow_unpauses_or_times_out);
  RUN_TEST(test_button_pressed_and_long_press);
  RUN_TEST(test_button_click_sequences);
  RUN_TEST(test_pump_rx_resync_and_dispatch);
  RUN_TEST(test_outgoing_commands);
  RUN_TEST(test_rtttl_parser_notes_and_durations);
  RUN_TEST(test_rom_bootloader_primitives);
  RUN_TEST(test_execute_ota_safety_gates);
  RUN_TEST(test_execute_ota_with_spi_flash_success);
  RUN_TEST(test_execute_ota_with_spi_flash_staging_failure);
  RUN_TEST(test_display_pixel_drawing);
  RUN_TEST(test_ota_web_handler);
  RUN_TEST(test_setup_and_dump_config);
  return UNITY_END();
}
