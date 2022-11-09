#include <furi.h>

int32_t template_app(void* p) {
    UNUSED(p);
    FURI_LOG_I("TEST", "Hello world!");

    return 0;
}
