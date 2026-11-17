#include <iostream>

extern "C" int modern_value()
{
  std::cout.flush();
  return 40;
}
