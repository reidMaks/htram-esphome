#ifndef FLASHER_H
#define FLASHER_H

#ifdef __cplusplus
extern "C" {
#endif

void flasher_run(void);
int flasher_restore_from_slot(uint32_t slot_addr, uint32_t size);
void flasher_restore_and_reboot(uint32_t slot_addr, uint32_t size);

#ifdef __cplusplus
}
#endif

#endif /* FLASHER_H */
