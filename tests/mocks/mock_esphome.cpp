#include "esphome/components/web_server_base/web_server_base.h"
#include "esphome/core/application.h"
#include "esphome/core/component.h"

uint32_t esphome::mock_esphome_millis = 0;
esphome::Application esphome::App;
esphome::web_server_base::WebServerBase* esphome::web_server_base::global_web_server_base = nullptr;
