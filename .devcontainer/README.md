# HTRAM-ESPHome Dev Container

Ізольоване середовище для розробки, компіляції прошивок GD32 / ESPHome, запуску тестів та безпечної роботи з AI-агентами (`agy cli`).

---

## Чому Dev Container?

1. **Безпека хоста для AI-агентів:**
   - Всередині контейнера агенту можна дати повний доступ до терміналу (`agy --dangerously-skip-permissions` або без пісочниці), не хвилюючись за приватні ключі (`~/.ssh`, Bitwarden), особисті файли чи інші проєкти на хості.
2. **Усі необхідні тулчейни з коробки:**
   - `arm-none-eabi-gcc` для Cortex-M3 (GD32F150 bare-metal).
   - `gcc` / `g++` з `-fanalyzer` для Unity тестів.
   - `clang-format-19` та `clang-tidy-19`.
   - `uv` + Python 3.12 для інструментів і тестів.
   - Бібліотеки `libcairo2-dev`, `libusb-1.0-0-dev`.
3. **Мережа та апаратура:**
   - Прапорець `--network=host` забезпечує нативний mDNS (`*.local`) та зв'язок із пристроями (`192.168.0.x`).
   - Прапорці `--privileged` та маппінг `/dev` надають доступ до USB SWD-програматора (Raspberry Pi Pico) та UART-портів.

---

## Способи використання

### Спосіб 1: Через VS Code або Antigravity IDE
1. Встановіть розширення **Dev Containers** (`ms-vscode-remote.remote-containers`).
2. Відкрийте проєкт і натисніть **Reopen in Container** (або через `Ctrl+Shift+P` -> `Dev Containers: Reopen in Container`).

### Спосіб 2: Через термінал (без VS Code)
Використовуйте підготовлений скрипт:

```bash
# Збірка образу
./tools/devcontainer.sh build

# Запуск інтерактивного shell
./tools/devcontainer.sh run

# Запуск окремої команди
./tools/devcontainer.sh exec make test
```

---

## Віддалене підключення з телефона

Оскільки в домашній мережі налаштовано WireGuard:

1. **Запуск фонової сесії в контейнері:**
   ```bash
   ./tools/devcontainer.sh run
   tmux new -s agent
   agy --dangerously-skip-permissions
   ```
2. **Підключення з телефона (Termius / Blink / Prompt):**
   Підключіться по SSH до вашого хоста та приєднайтесь до сесії:
   ```bash
   ssh max@<host-ip> -t "docker exec -it htram-dev tmux attach -t agent"
   ```
   Це дає стабільну роботу навіть при розривах мобільного інтернету.
