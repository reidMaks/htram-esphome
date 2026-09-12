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
TEST_BIN_SPI_FLASH:= $(TEST_DIR)/test_spi_flash_bin
TEST_BIN_ESPHOME  := $(TEST_DIR)/test_htram_gd32_bin

.PHONY: all test test-gd32 test-esphome test-tools test-configs \
        lint lint-c lint-py lint-yaml format format-check \
        coverage coverage-html build-gd32 ota-gd32 pack-assets validate-assets flash-assets \
        status build-esp install-hooks clean help \
        device device-silence device-status device-beep \
        container-build container-run container-stop

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
	@echo "  make ota-gd32      - Flash GD32 firmware via OTA (Usage: make ota-gd32 DEVICE=<alias|ip>)"
	@echo "  make pack-assets   - Pack and validate UI monochrome bitmaps into flash_assets.bin"
	@echo "  make validate-assets- Validate graphic assets container for geometry and memory safety"
	@echo "  make flash-assets  - Pack, validate, and upload graphic assets to SPI Flash: make flash-assets DEVICE=<alias|ip>"
	@echo "  make build-esp     - Compile ESPHome ESP32 firmware"
	@echo "  make device        - Control device API: make device DEVICE=<alias|ip> CMD=<cmd>"
	@echo "  make device-status - Show device sensors/status: make device-status DEVICE=<alias|ip>"
	@echo "  make device-silence- Trigger minute of silence test: make device-silence DEVICE=<alias|ip>"
	@echo "  make container-build- Build dev container Docker image"
	@echo "  make container-run  - Launch dev container shell (Docker)"
	@echo "  make container-stop - Stop and remove dev container"
	@echo "  make clean         - Remove test binaries, coverage counters, and build artifacts"

# ── Test Suite ───────────────────────────────────────────────────────────────
test: test-gd32 test-esphome test-tools test-configs
	@echo "========================================================"
	@echo "  ALL TEST SUITES PASSED SUCCESSFULLY!"
	@echo "========================================================"

# ── GD32 Firmware Tests ─────────────────────────────────────────────────────
test-gd32: $(TEST_BIN_PROTOCOL) $(TEST_BIN_SENSORS) $(TEST_BIN_PERIPH) $(TEST_BIN_SPI_FLASH)
	@echo "==> Running GD32 Firmware Protocol Engine Tests..."
	./$(TEST_BIN_PROTOCOL)
	@echo "==> Running GD32 Firmware Sensor Drivers Tests..."
	./$(TEST_BIN_SENSORS)
	@echo "==> Running GD32 Firmware Peripheral & HAL Tests..."
	./$(TEST_BIN_PERIPH)
	@echo "==> Running GD32 Firmware SPI Flash Driver Tests..."
	./$(TEST_BIN_SPI_FLASH)

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

$(TEST_BIN_SPI_FLASH): $(TEST_DIR)/firmware_gd32/test_spi_flash.c \
                      $(GD32_SRC)/spi_flash.c \
                      $(MOCKS_DIR)/mock_gd32.c \
                      $(MOCKS_DIR)/mock_periph_display.c \
                      $(UNITY_DIR)/unity.c
	$(CC) $(CFLAGS) $^ -o $@

# ── ESPHome Component Tests ─────────────────────────────────────────────────
test-esphome: $(TEST_BIN_ESPHOME)
	@echo "==> Running ESPHome C++ Component Tests..."
	./$(TEST_BIN_ESPHOME)

$(TEST_BIN_ESPHOME): $(TEST_DIR)/esphome_component/test_htram_gd32.cpp \
                     $(MOCKS_DIR)/mock_esphome.cpp \
                     $(UNITY_DIR)/unity.c \
                     esphome/custom_components/htram_gd32/htram_gd32.cpp \
                     esphome/custom_components/htram_gd32/htram_gd32.h
	$(CXX) $(CXXFLAGS) $(TEST_DIR)/esphome_component/test_htram_gd32.cpp $(MOCKS_DIR)/mock_esphome.cpp $(UNITY_DIR)/unity.c -o $@

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
	$(CC) -fanalyzer -Wall -Wextra -Wpedantic -fsyntax-only -I$(MOCKS_DIR) -I$(GD32_INC) $(GD32_SRC)/spi_flash.c
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
coverage: clean $(TEST_BIN_PROTOCOL) $(TEST_BIN_SENSORS) $(TEST_BIN_PERIPH) $(TEST_BIN_SPI_FLASH) $(TEST_BIN_ESPHOME)
	@echo "==> Running test binaries for coverage collection..."
	./$(TEST_BIN_PROTOCOL) > /dev/null
	./$(TEST_BIN_SENSORS) > /dev/null
	./$(TEST_BIN_PERIPH) > /dev/null
	./$(TEST_BIN_SPI_FLASH) > /dev/null
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

TARGET_DEVICE := $(strip $(if $(DEVICE),$(DEVICE),$(if $(HOST),$(HOST),$(IP))))
ifeq ($(TARGET_DEVICE),office)
  override TARGET_DEVICE := 192.168.0.78
endif
ifeq ($(TARGET_DEVICE),кабінет)
  override TARGET_DEVICE := 192.168.0.78
endif
ifeq ($(TARGET_DEVICE),cabinet)
  override TARGET_DEVICE := 192.168.0.78
endif
ifeq ($(TARGET_DEVICE),bedroom)
  override TARGET_DEVICE := 192.168.0.159
endif
ifeq ($(TARGET_DEVICE),спальня)
  override TARGET_DEVICE := 192.168.0.159
endif
ifeq ($(TARGET_DEVICE),living)
  override TARGET_DEVICE := 192.168.0.185
endif
ifeq ($(TARGET_DEVICE),livingroom)
  override TARGET_DEVICE := 192.168.0.185
endif
ifeq ($(TARGET_DEVICE),вітальня)
  override TARGET_DEVICE := 192.168.0.185
endif

ota-gd32: build-gd32
ifeq ($(strip $(TARGET_DEVICE)),)
	$(error TARGET_DEVICE is not set. Usage: make ota-gd32 DEVICE=<alias|ip>, e.g. make ota-gd32 DEVICE=office)
endif
	@echo "==> Flashing GD32 firmware via OTA to $(TARGET_DEVICE)..."
	$(PYTHON) tools/swd/flash.py --ota $(TARGET_DEVICE)

pack-assets:
	@echo "==> Packing and validating graphic assets into flash_assets.bin..."
	$(PYTHON) tools/pack_flash_assets.py

validate-assets:
	@echo "==> Validating graphic assets binary container..."
	$(PYTHON) tools/pack_flash_assets.py --validate

flash-assets: pack-assets validate-assets
ifeq ($(strip $(TARGET_DEVICE)),)
	$(error TARGET_DEVICE is not set. Usage: make flash-assets DEVICE=<alias|ip>, e.g. make flash-assets DEVICE=office)
endif
	@echo "==> Uploading validated graphic assets to $(TARGET_DEVICE)..."
	$(PYTHON) tools/flash_assets.py $(TARGET_DEVICE)

status:
ifeq ($(strip $(TARGET_DEVICE)),)
	$(error TARGET_DEVICE is not set. Usage: make status DEVICE=<alias|ip>, e.g. make status DEVICE=office)
endif
	@$(PYTHON) tools/swd/flash.py --status $(TARGET_DEVICE)

build-esp:
	@echo "==> Compiling ESPHome ESP32 firmware..."
	$(ESPHOME) compile esphome/htram.yaml

# ── Device API Management ───────────────────────────────────────────────────
device:
	$(PYTHON) tools/device.py $(or $(DEVICE),office) $(or $(CMD),status) $(ARGS)

device-silence:
	$(PYTHON) tools/device.py $(or $(DEVICE),office) silence

device-status:
	$(PYTHON) tools/device.py $(or $(DEVICE),office) status

device-beep:
	$(PYTHON) tools/device.py $(or $(DEVICE),office) beep

# ── Dev Container ────────────────────────────────────────────────────────────
container-build:
	./tools/devcontainer.sh build

container-run:
	./tools/devcontainer.sh run

container-stop:
	./tools/devcontainer.sh stop

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
