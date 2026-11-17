#include <stdio.h>

extern const char* BZ2_bzlibVersion(void);
extern int modern_value(void);

int main(void)
{
  if (BZ2_bzlibVersion()[0] == '\0') return 1;
  const int result = modern_value() + 2;
  printf("%d\n", result);
  return result != 42;
}
