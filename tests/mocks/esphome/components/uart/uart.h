#pragma once
#include <vector>
#include <cstdint>
#include <cstddef>
#include <functional>

namespace esphome {
namespace uart {

class UARTDevice {
 public:
  virtual ~UARTDevice() = default;

  std::vector<uint8_t> mock_rx_bytes;
  size_t mock_rx_pos{0};
  std::vector<uint8_t> mock_tx_bytes;
  std::function<void(const uint8_t *data, size_t len)> on_write;

  void mock_push_rx(const uint8_t *data, size_t len) {
    mock_rx_bytes.insert(mock_rx_bytes.end(), data, data + len);
  }
  void mock_push_rx_byte(uint8_t b) {
    mock_rx_bytes.push_back(b);
  }
  void mock_clear_rx() {
    mock_rx_bytes.clear();
    mock_rx_pos = 0;
  }
  void mock_clear_tx() {
    mock_tx_bytes.clear();
  }

  bool available() {
    return mock_rx_pos < mock_rx_bytes.size();
  }
  bool read_byte(uint8_t *c) {
    if (mock_rx_pos < mock_rx_bytes.size()) {
      *c = mock_rx_bytes[mock_rx_pos++];
      return true;
    }
    return false;
  }
  void write_array(const uint8_t *data, size_t len) {
    mock_tx_bytes.insert(mock_tx_bytes.end(), data, data + len);
    if (on_write) on_write(data, len);
  }
  void write_byte(uint8_t b) {
    mock_tx_bytes.push_back(b);
    if (on_write) on_write(&b, 1);
  }
  void flush() {}
};

}  // namespace uart
}  // namespace esphome
