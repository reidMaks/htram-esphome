# =============================================================================
# HTRAM-ESPHome: Top-level Makefile for Tests, Linters, and Tools
# =============================================================================

CC           ?= gcc
CXX          ?= g++
VENV         ?= .venv
PYTHON       := $(VENV)/bin/python
PYTEST       := $(VENV)/bin/pytest
ESPHOME      := $(VENV)/bin/esphome
GCOVR        := $(VENV)/bin/gcovr
RUFF         := $(VENV)/bin/ruff
MYPY         := $(VENV)/bin/mypy
YAMLLINT     := $(VENV)/bin/yamllint
CLANG_FORMAT := $(VENV)/bin/clang-format
CLANG_TIDY   := $(VENV)/bin/clang-tidy

UNITY_DIR    := tests/vendor/unity
MOCKS_DIR    := tests/mocks
GD32_INC     := firmware/gd32/inc
GD32_SRC     := firmware/gd32/src
ESPHOME_COMP := esphome/custom_components/htram_gd32

CFLAGS   := -Wall -Wextra -g -O0 -fprofile-arcs -ftest-coverage \
            -I$(UNITY_DIR) -I$(MOCKS_DIR) -I$(GD32_INC)
CXXFLAGS := -Wall -Wextra -Wno-unused-parameter -Wno-unused-variable -g -O0 \
            -fprofile-arcs -ftest-coverage \
            -I. -I$(UNITY_DIR) -I$(MOCKS_DIR) -I$(MOCKS_DIR)/esphome -I$(ESPHOME_COMP)

TEST_DIR := tests
TEST_BIN_PROTOCOL := $(TEST_DIR)/test_protocol_engine_bin
TEST_BIN_SENSORS  := $(TEST_DIR)/test_sensors_bin
TEST_BIN_PERIPH   := $(TEST_DIR)/test_periph_bin
TEST_BIN_ESPHOME  := $(TEST_DIR)/test_htram_gd32_bin

.PHONY: all test test-gd32 test-esphome test-tools test-configs \
        lint lint-c lint-py lint-yaml format format-check \
        coverage coverage-html build-gd32 build-esp install-hooks clean help

all: test

help:
	@echo "HTRAM-ESPHome Targets:"
	@echo "  make test          - Run all test suites (GD32, ESPHome C++, Python tools & configs)"
	@echo "  make test-gd32     - Run GD32 bare-metal C99 firmware unit tests (Unity)"
	@echo "  make test-esphome  - Run ESP32 / ESPHome C++ unit tests (Unity)"
	@echo "  make test-tools    - Run Python tools tests via pytest (CRC, mask generator)"
	@echo "  make test-configs  - Validate ESPHome YAML device configurations"
	@echo "  make lint          - Run all linters and static analyzers (C/C++, Python, YAML)"
	@echo "  make lint-c        - Run GCC/G++ -fanalyzer static analysis on C/C++ source code"
	@echo "  make lint-py       - Run ruff and mypy on Python scripts and tests"
	@echo "  make lint-yaml     - Run yamllint on ESPHome YAML configurations"
	@echo "  make format-check  - Check code formatting (ruff and clang-format)"
	@echo "  make format        - Automatically format code (ruff format & fix)"
	@echo "  make coverage      - Generate terminal code coverage summary (gcovr + pytest-cov)"
	@echo "  make coverage-html - Generate HTML coverage report in coverage_html/"
	@echo "  make install-hooks - Configure git to use repository pre-commit hook"
	@echo "  make build-gd32    - Build GD32 target firmware via arm-none-eabi-gcc"
	@echo "  make build-esp     - Compile ESPHome ESP32 firmware"
	@echo "  make clean         - Remove test binaries, coverage counters, and build artifacts"

# ── Test Suite ───────────────────────────────────────────────────────────────
test: test-gd32 test-esphome test-tools test-configs
	@echo "========================================================"
	@echo "  ALL TEST SUITES PASSED SUCCESSFULLY!"
	@echo "========================================================"

# ── GD32 Firmware Tests ─────────────────────────────────────────────────────
test-gd32: $(TEST_BIN_PROTOCOL) $(TEST_BIN_SENSORS) $(TEST_BIN_PERIPH)
	@echo "==> Running GD32 Firmware Protocol Engine Tests..."
	./$(TEST_BIN_PROTOCOL)
	@echo "==> Running GD32 Firmware Sensor Drivers Tests..."
	./$(TEST_BIN_SENSORS)
	@echo "==> Running GD32 Firmware Peripheral & HAL Tests..."
	./$(TEST_BIN_PERIPH)

$(TEST_BIN_PROTOCOL): $(TEST_DIR)/firmware_gd32/test_protocol_engine.c \
                      $(GD32_SRC)/protocol_engine.c \
                      $(MOCKS_DIR)/mock_gd32.c \
                      $(MOCKS_DIR)/mock_periph_display.c \
                      $(UNITY_DIR)/unity.c
	$(CC) $(CFLAGS) $^ -o $@

$(TEST_BIN_SENSORS): $(TEST_DIR)/firmware_gd32/test_sensors.c \
                    $(MOCKS_DIR)/mock_gd32.c \
                    $(UNITY_DIR)/unity.c
	$(CC) $(CFLAGS) $^ -o $@

$(TEST_BIN_PERIPH): $(TEST_DIR)/firmware_gd32/test_periph.c \
                   $(GD32_SRC)/periph.c \
                   $(MOCKS_DIR)/mock_gd32.c \
                   $(UNITY_DIR)/unity.c
	$(CC) $(CFLAGS) $^ -o $@

# ── ESPHome Component Tests ─────────────────────────────────────────────────
test-esphome: $(TEST_BIN_ESPHOME)
	@echo "==> Running ESPHome C++ Component Tests..."
	./$(TEST_BIN_ESPHOME)

$(TEST_BIN_ESPHOME): $(TEST_DIR)/esphome_component/test_htram_gd32.cpp \
                     $(MOCKS_DIR)/mock_esphome.cpp \
                     $(UNITY_DIR)/unity.c
	$(CXX) $(CXXFLAGS) $^ -o $@

# ── Python Tools Tests ──────────────────────────────────────────────────────
test-tools:
	@echo "==> Running Python Tools Tests via pytest..."
	$(PYTEST) tests/tools -v

# ── ESPHome Config Validation ───────────────────────────────────────────────
test-configs:
	@echo "==> Validating ESPHome YAML Configurations..."
	$(PYTEST) tests/esphome_config -v

# ── Linters & Static Analysis ────────────────────────────────────────────────
lint: lint-c lint-yaml lint-py
	@echo "========================================================"
	@echo "  ALL LINTERS & STATIC ANALYZERS PASSED!"
	@echo "========================================================"

lint-c:
	@echo "==> Running GCC -fanalyzer on GD32 C firmware..."
	$(CC) -fanalyzer -Wall -Wextra -Wpedantic -fsyntax-only -I$(MOCKS_DIR) -I$(GD32_INC) $(GD32_SRC)/protocol_engine.c
	$(CC) -fanalyzer -Wall -Wextra -Wpedantic -fsyntax-only -I$(MOCKS_DIR) -I$(GD32_INC) $(GD32_SRC)/sensors.c
	$(CC) -fanalyzer -Wall -Wextra -Wpedantic -fsyntax-only -I$(MOCKS_DIR) -I$(GD32_INC) $(GD32_SRC)/periph.c
	@echo "==> Running G++ -fanalyzer on ESPHome C++ component..."
	$(CXX) -fanalyzer -Wall -Wextra -Wno-unused-parameter -Wno-unused-variable -fsyntax-only \
	      -I. -I$(UNITY_DIR) -I$(MOCKS_DIR) -I$(MOCKS_DIR)/esphome -I$(ESPHOME_COMP) \
	      $(ESPHOME_COMP)/htram_gd32.cpp

lint-yaml:
	@echo "==> Running yamllint on ESPHome configurations..."
	$(YAMLLINT) esphome/

lint-py:
	@echo "==> Running ruff check on tests/..."
	$(RUFF) check tests/
	@echo "==> Running mypy on tests/tools..."
	$(MYPY) tests/tools

format-check:
	@echo "==> Checking formatting with ruff..."
	$(RUFF) format --check tests/
	@echo "==> Checking formatting with clang-format..."
	$(CLANG_FORMAT) --dry-run --Werror tests/firmware_gd32/*.c tests/esphome_component/*.cpp tests/mocks/*.c tests/mocks/*.cpp

format:
	@echo "==> Auto-formatting Python tests and tools..."
	$(RUFF) format tests/
	$(RUFF) check --fix tests/
	@echo "==> Auto-formatting C/C++ test suites..."
	$(CLANG_FORMAT) -i tests/firmware_gd32/*.c tests/esphome_component/*.cpp tests/mocks/*.c tests/mocks/*.cpp

# ── Code Coverage ────────────────────────────────────────────────────────────
coverage: clean $(TEST_BIN_PROTOCOL) $(TEST_BIN_SENSORS) $(TEST_BIN_PERIPH) $(TEST_BIN_ESPHOME)
	@echo "==> Running test binaries for coverage collection..."
	./$(TEST_BIN_PROTOCOL) > /dev/null
	./$(TEST_BIN_SENSORS) > /dev/null
	./$(TEST_BIN_PERIPH) > /dev/null
	./$(TEST_BIN_ESPHOME) > /dev/null
	@echo "\n========================================================"
	@echo "  C / C++ FIRMWARE & COMPONENT COVERAGE (gcovr)"
	@echo "========================================================"
	$(GCOVR) --filter firmware/gd32/src/ --filter esphome/custom_components/htram_gd32/ --txt
	@echo "\n========================================================"
	@echo "  PYTHON TOOLS COVERAGE (pytest-cov)"
	@echo "========================================================"
	$(PYTEST) --cov=tools tests/tools -q

coverage-html: coverage
	@mkdir -p coverage_html
	$(GCOVR) --filter firmware/gd32/src/ --filter esphome/custom_components/htram_gd32/ \
	         --html --html-details -o coverage_html/coverage_cpp.html
	$(PYTEST) --cov=tools --cov-report=html:coverage_html/coverage_py tests/tools -q
	@echo "Coverage HTML reports generated in coverage_html/"

# ── Git Hooks ────────────────────────────────────────────────────────────────
install-hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit
	@echo "Git pre-commit hook installed successfully (pointing to .githooks/)."

# ── Hardware Firmware Builds ─────────────────────────────────────────────────
build-gd32:
	@echo "==> Building GD32 bare-metal firmware..."
	$(MAKE) -C firmware/gd32 flash

build-esp:
	@echo "==> Compiling ESPHome ESP32 firmware..."
	$(ESPHOME) compile esphome/htram.yaml

# ── Clean ────────────────────────────────────────────────────────────────────
clean:
	rm -f $(TEST_DIR)/*_bin
	rm -f $(TEST_DIR)/*.o
	rm -f $(TEST_DIR)/*.gcda $(TEST_DIR)/*.gcno
	rm -f $(TEST_DIR)/*.so
	rm -rf .pytest_cache
	rm -f .coverage
	rm -rf coverage_html
	$(MAKE) -C firmware/gd32 clean
