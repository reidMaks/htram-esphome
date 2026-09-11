#ifndef MOCK_FLASHER_H
#define MOCK_FLASHER_H

#ifdef __cplusplus
extern "C" {
#endif

extern int mock_flasher_run_called;
void flasher_run(void);
void mock_flasher_reset(void);

#ifdef __cplusplus
}
#endif

#endif /* MOCK_FLASHER_H */
