# oneAPI runtime lookup failure

A C program links a cached Bzip2 library built with GCC 10 and a tiny C++
library built with oneAPI. Spack records the newer GCC runtime correctly,
but its linker paths select the older runtime instead.

## Run

Use Ubuntu 24.04 x86-64 with GCC 13, G++ 13, GFortran 13, Python 3, and Git.
The CPU must support x86-64-v3. This downloads oneAPI; no GCC build is needed.

```sh
mkdir -p .work
git clone https://github.com/spack/spack.git .work/spack
git -C .work/spack checkout --detach ab3f3ac5f48d4d636d82bb317e24dd59494f4d32
git clone https://github.com/spack/spack-packages.git .work/spack-packages
git -C .work/spack-packages checkout --detach 8933fbb6925be105d493d2eff0c0b375a2ac1cc8

export SPACK_DISABLE_LOCAL_CONFIG=1
.work/spack/bin/spack -C . install --fail-fast intel-oneapi-compilers@2025.3.2 %gcc@13
.work/spack/bin/spack -e . concretize
.work/spack/bin/spack -e . install --only dependencies --fail-fast
.work/spack/bin/spack -e . install --fail-fast --show-log-on-error
```

The C++ library builds, but linking the C program fails:

```text
undefined reference to std::ios_base_library_init()@GLIBCXX_3.4.32
```

The same failure was reproduced locally with GCC 15.2 and oneAPI 2025.3.2.
[reproduce.log](./reproduce.log) contains the captured concretization, successful
C++ library build, and C consumer link failure from that run on Ubuntu 26.04.
This example contains no fix. The complete comparison setup is preserved
in commit `7960808`.
