extern const char* BZ2_bzlibVersion(void);
extern int modern_value(void);

int main(void)
{
  return modern_value() != 42 || BZ2_bzlibVersion()[0] == '\0';
}
