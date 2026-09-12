#ifndef FLASH_ASSETS_H
#define FLASH_ASSETS_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "spi_flash.h"

#define FLASH_ASSETS_MAGIC      0x545353414D525448ULL /* "HTRMASST" in LE */
#define FLASH_ASSETS_VERSION    1
#define FLASH_ASSETS_MAX_NAME   32

/* Canonical Asset IDs across GD32 firmware, host tools, and ESPHome */
enum flash_asset_id_e {
    ASSET_ID_TRYZUB = 0,
    ASSET_ID_BELL,
    ASSET_ID_ALERT,
    ASSET_ID_ALERT_SMALL,
    ASSET_ID_THREAT_BALLISTIC,
    ASSET_ID_THREAT_KAB,
    ASSET_ID_THREAT_MISSILE,
    ASSET_ID_THREAT_DRONE,
    ASSET_ID_THREAT_RECON,
    ASSET_ID_WEATHER_SUNNY,
    ASSET_ID_WEATHER_PARTLYCLOUDY_SUN,
    ASSET_ID_WEATHER_PARTLYCLOUDY_CLOUD,
    ASSET_ID_WEATHER_CLOUDY,
    ASSET_ID_WEATHER_RAINY_CLOUD,
    ASSET_ID_WEATHER_RAINY_DROPS,
    ASSET_ID_WEATHER_LIGHTNING_CLOUD,
    ASSET_ID_WEATHER_LIGHTNING_BOLT,
    ASSET_ID_WEATHER_SNOWY_CLOUD,
    ASSET_ID_WEATHER_SNOWY_FLAKES,
    ASSET_ID_WEATHER_FOG,
    ASSET_ID_WEATHER_WINDY,
    ASSET_ID_WEATHER_RAINY,
    ASSET_ID_WEATHER_PARTLYCLOUDY,
    ASSET_ID_WEATHER_LIGHTNING,
    ASSET_ID_WEATHER_SNOWY,
    ASSET_ID_COUNT
};

#pragma pack(push, 1)

typedef struct {
    uint64_t magic;              /* "HTRMASST" (0x545353414D525448ULL) */
    uint16_t version;            /* 1 */
    uint16_t asset_count;        /* Total number of assets in directory */
    uint32_t total_size;         /* Total binary container size in bytes */
    uint32_t header_crc32;       /* IEEE CRC32 of preceding 16 bytes */
} flash_assets_header_t;

typedef struct {
    uint16_t asset_id;           /* Enum flash_asset_id_e */
    uint16_t width;              /* Width in pixels */
    uint16_t height;             /* Height in pixels */
    uint16_t stride;             /* Bytes per row = (width + 7) / 8 */
    uint32_t data_offset;        /* Offset of bitmap relative to SPI_FLASH_ASSETS_ADDR */
    uint32_t data_size;          /* Size of bitmap data = height * stride */
    uint32_t data_crc32;         /* IEEE CRC32 of this asset's bitmap data */
    char     name[FLASH_ASSETS_MAX_NAME]; /* e.g. "tryzub\0" */
} flash_asset_entry_t;

#pragma pack(pop)

#endif /* FLASH_ASSETS_H */
