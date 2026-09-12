FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install base utilities and toolchains:
# - build-essential, gcc, g++: native host testing (Unity, -fanalyzer, gcovr)
# - gcc-arm-none-eabi, binutils, newlib: GD32F150 Cortex-M3 bare-metal compilation
# - clang-format-19, clang-tidy-19: C/C++ formatting and linting
# - libcairo2-dev, libgirepository1.0-dev: SVG and font processing (cairosvg)
# - libusb-1.0-0-dev, udev: SWD debugging via Raspberry Pi Pico (pyocd)
# - avahi-utils: mDNS resolution for ESP32 (*.local)
# - tmux, screen, mosh: terminal session persistence for mobile / remote access
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    gcc-arm-none-eabi \
    binutils-arm-none-eabi \
    libnewlib-arm-none-eabi \
    clang-format-19 \
    clang-tidy-19 \
    libcairo2-dev \
    libgirepository1.0-dev \
    libusb-1.0-0-dev \
    udev \
    avahi-utils \
    git \
    curl \
    ca-certificates \
    sudo \
    tmux \
    screen \
    mosh \
    openssh-client \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Set default clang-format and clang-tidy to version 19
RUN ln -sf /usr/bin/clang-format-19 /usr/bin/clang-format && \
    ln -sf /usr/bin/clang-tidy-19 /usr/bin/clang-tidy

# Install uv (fast Python package and virtualenv manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Configure the ubuntu user (UID 1000) with passwordless sudo & dialout/plugdev groups for hardware access
RUN usermod -aG sudo,dialout,plugdev ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu && \
    chmod 0440 /etc/sudoers.d/ubuntu && \
    mkdir -p /home/ubuntu/.cache /home/ubuntu/.platformio /home/ubuntu/.local/share && \
    chown -R ubuntu:ubuntu /home/ubuntu

USER ubuntu
WORKDIR /workspace

ENV PATH="/home/ubuntu/.local/bin:/workspace/.venv/bin:${PATH}"

# Install Antigravity CLI (agy) if installer is reachable
RUN curl -fsSL https://antigravity.google/install.sh -o /tmp/install-agy.sh 2>/dev/null && \
    (bash /tmp/install-agy.sh || true) && rm -f /tmp/install-agy.sh || true

CMD ["/bin/bash"]
