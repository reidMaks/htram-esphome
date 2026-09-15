#pragma once

// HTRAM Simulator: Deterministic Time Control
//
// This header is included EXCLUSIVELY in the native host simulator (htram-sim).
// It overrides POSIX and C library time functions (time, gettimeofday, clock_gettime)
// so that tests can freeze time or advance it deterministically.
//
// This ensures pixel-identical screenshots across test runs without Git diff noise.

#include <ctime>
#include <sys/time.h>
#include <dlfcn.h>
#include <cstdint>

namespace htram_sim {

static time_t s_mock_epoch = 0;       // If > 0, mock time is active
static bool s_freeze = true;          // If true, time is frozen at s_mock_epoch
static uint64_t s_base_mono_ms = 0;   // Monotonic reference timestamp in ms

typedef time_t (*real_time_fn)(time_t *);
typedef int (*real_gettimeofday_fn)(struct timeval *, void *);
typedef int (*real_clock_gettime_fn)(clockid_t, struct timespec *);

static real_time_fn real_time = nullptr;
static real_gettimeofday_fn real_gettimeofday = nullptr;
static real_clock_gettime_fn real_clock_gettime = nullptr;

inline uint64_t get_monotonic_ms() {
  struct timespec ts;
  if (!real_clock_gettime) {
    real_clock_gettime = (real_clock_gettime_fn) dlsym(RTLD_NEXT, "clock_gettime");
  }
  if (real_clock_gettime) {
    real_clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t) ts.tv_sec * 1000ULL + (uint64_t) (ts.tv_nsec / 1000000);
  }
  return 0;
}

inline void set_time(time_t epoch, bool freeze = true) {
  s_mock_epoch = epoch;
  s_freeze = freeze;
  s_base_mono_ms = get_monotonic_ms();
}

inline void step_time(int32_t seconds) {
  if (s_mock_epoch > 0) {
    s_mock_epoch += seconds;
  }
}

inline void reset_time() {
  s_mock_epoch = 0;
  s_freeze = true;
}

inline bool is_mock_active() {
  return s_mock_epoch > 0;
}

inline time_t get_current_time() {
  if (s_mock_epoch <= 0) {
    if (!real_time) real_time = (real_time_fn) dlsym(RTLD_NEXT, "time");
    return real_time ? real_time(nullptr) : ::time(nullptr);
  }
  if (s_freeze) {
    return s_mock_epoch;
  }
  uint64_t elapsed_s = (get_monotonic_ms() - s_base_mono_ms) / 1000ULL;
  return s_mock_epoch + (time_t) elapsed_s;
}

inline int get_current_timeval(struct timeval *tv, void *tz) {
  if (s_mock_epoch <= 0) {
    if (!real_gettimeofday) real_gettimeofday = (real_gettimeofday_fn) dlsym(RTLD_NEXT, "gettimeofday");
    return real_gettimeofday ? real_gettimeofday(tv, tz) : 0;
  }
  if (tv) {
    if (s_freeze) {
      tv->tv_sec = s_mock_epoch;
      tv->tv_usec = 0;
    } else {
      uint64_t now_ms = get_monotonic_ms();
      uint64_t elapsed_ms = now_ms - s_base_mono_ms;
      tv->tv_sec = s_mock_epoch + (time_t) (elapsed_ms / 1000ULL);
      tv->tv_usec = (suseconds_t) ((elapsed_ms % 1000ULL) * 1000ULL);
    }
  }
  return 0;
}

}  // namespace htram_sim

extern "C" {

time_t time(time_t *tloc) {
  time_t t = htram_sim::get_current_time();
  if (tloc) *tloc = t;
  return t;
}

int gettimeofday(struct timeval *tv, void *tz) {
  return htram_sim::get_current_timeval(tv, tz);
}

int clock_gettime(clockid_t clk_id, struct timespec *tp) {
  if (clk_id == CLOCK_REALTIME && htram_sim::is_mock_active()) {
    if (tp) {
      struct timeval tv;
      htram_sim::get_current_timeval(&tv, nullptr);
      tp->tv_sec = tv.tv_sec;
      tp->tv_nsec = tv.tv_usec * 1000L;
    }
    return 0;
  }
  if (!htram_sim::real_clock_gettime) {
    htram_sim::real_clock_gettime =
        (htram_sim::real_clock_gettime_fn) dlsym(RTLD_NEXT, "clock_gettime");
  }
  return htram_sim::real_clock_gettime ? htram_sim::real_clock_gettime(clk_id, tp) : 0;
}

}
