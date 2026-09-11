#pragma once
#include <cstddef>
#include <cstdint>

#define MALLOC_CAP_8BIT 1

inline size_t heap_caps_get_largest_free_block(uint32_t caps) {
  (void)caps;
  return 65536;
}
