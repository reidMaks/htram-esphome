#pragma once
#include <string>
#include <vector>
#include <cstdint>

#define HTTP_POST 1
using PlatformString = std::string;

class AsyncWebServerRequest {
 public:
  virtual ~AsyncWebServerRequest() = default;
  virtual std::string url() const { return "/gd32_ota"; }
  virtual int method() const { return HTTP_POST; }
  virtual bool hasParam(const std::string &param) const { (void)param; return false; }
  virtual size_t contentLength() const { return 1024; }
  virtual void send(int code, const char *contentType, const char *content) {
    (void)code; (void)contentType; (void)content;
  }
};

class AsyncWebHandler {
 public:
  virtual ~AsyncWebHandler() = default;
  virtual bool canHandle(AsyncWebServerRequest *request) const = 0;
  virtual void handleRequest(AsyncWebServerRequest *request) = 0;
  virtual void handleUpload(AsyncWebServerRequest *request, const PlatformString &filename,
                            size_t index, uint8_t *data, size_t len, bool final) = 0;
};

namespace esphome {
namespace web_server_base {

class WebServerBase {
 public:
  std::vector<AsyncWebHandler *> handlers;
  void add_handler(AsyncWebHandler *handler) {
    handlers.push_back(handler);
  }
};

extern WebServerBase *global_web_server_base;

}  // namespace web_server_base
}  // namespace esphome
