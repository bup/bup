#pragma once

#include <stdio.h>

void msg(FILE* f, const char * const msg, ...);
void die(int exit_status, const char * const msg, ...);
