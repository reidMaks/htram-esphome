#ifndef MOCK_FLASHER_H
#define MOCK_FLASHER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

extern int mock_flasher_run_called;
extern int mock_flasher_restore_called;
extern uint32_t mock_flasher_restore_slot;
extern uint32_t mock_flasher_restore_size;
void flasher_run(void);
int flasher_restore_from_slot(uint32_t slot_addr, uint32_t size);
void flasher_restore_and_reboot(uint32_t slot_addr, uint32_t size);
void mock_flasher_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* MOCK_FLASHER_H */
