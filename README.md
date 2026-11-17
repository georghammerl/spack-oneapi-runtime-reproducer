# Minimal oneAPI / GCC runtime-path experiment

This is a local investigation for
[spack/spack#53357](https://github.com/spack/spack/pull/53357), not a proposed
replacement patch. It has no dependency on 4C, MPI, netCDF, or PnetCDF.
Nothing here has been published.

## The problem in brief

A small C program links an old cached C library and a newly built oneAPI C++
library. The C++ library needs a newer `libstdc++.so.6`.

In the local test, oneAPI correctly selects GCC 15, and Spack records the
matching GCC 15 runtime. But when preparing the C program's linker search paths,
Spack looks up `gcc-runtime` by name and selects the GCC 10 instance instead.
The GCC 15 runtime directory is omitted, and linking fails:

```text
undefined reference to std::ios_base_library_init()@GLIBCXX_3.4.32
```

Changing only Spack's dependency lookup makes the same program link and print
`42`. The compiler, lockfile, and installed dependency libraries are unchanged.

This reproduces the failure; it does not establish that the current patch is
the best API-level solution. Full evidence is under [Validation status](#validation-status).

## What it tests

The original failing lockfile contains a cached **linked** Bzip2 library built
with GCC 10, alongside a oneAPI runtime depending on GCC runtime 13. The old
runtime does not come exclusively from build-only tools.

This experiment keeps that Bzip2 binary and replaces the large application with:

- `runtime-repro-modern`: a tiny oneAPI-built C++ shared library using iostreams.
- `runtime-repro-consumer`: a C program linking both that library and Bzip2.

The resulting link graph should contain:

```text
C consumer (oneAPI)
|-- Bzip2 (cached GCC 10 build)
|   `-- gcc-runtime@10.5.0
|-- tiny C++ library (oneAPI)
|   `-- intel-oneapi-runtime
|       `-- gcc-runtime@13.x
`-- intel-oneapi-runtime
    `-- gcc-runtime@13.x
```

Dependencies are concretized and built normally: no hand-edited DAG, fake
compiler, patched library, or manually assigned query state.

The experiment distinguishes three questions:

1. Does a name lookup select a different runtime node from the link traversal?
2. Which GCC development library (`libstdc++.so`) does oneAPI select?
3. Which versioned runtime (`libstdc++.so.6`) does the consumer's linker find?

`gcc-runtime` is not used as a replacement for GCC's development files.
The diagnostics record compiler `.cfg` files, compiler `-###` output, wrapper
search paths, ELF dependencies/RPATHs, versioned C++ symbols, and linker tracing.

## Prerequisites

The intended full experiment is Linux x86-64 on Ubuntu 24.04 with GCC 13,
matching G++/GFortran, Python 3, Git, and binutils (`readelf`). The cached binary
requires an x86-64-v3-compatible CPU. Network access is needed for Spack
bootstrapping, the build cache, and the Intel compiler installer.

No GCC compiler is built from source. Intel oneAPI **will be downloaded and
installed** in the experiment's private output directory; allow several GB.
Do not run the experiment as root.

All Spack installations, configuration, stages, logs, and environments are
created under `--output`. Existing Spack/package checkouts are not modified,
and inherited Spack environment activation is ignored. Use a fresh output
directory for every run. Do not copy the GCC-13-specific setup into a general
package recipe.

## First check the source projects

This needs a native C/C++ toolchain and the system Bzip2 shared library, but
neither Spack nor oneAPI:

```sh
python3 reproduce.py --native-smoke --output .work/native
```

The executable should print `42`. **This does not reproduce or validate the
oneAPI/Spack failure.**

## Compare unpatched and proposed-patch Spack

Use the PR's parent and head so that the comparison changes only its patch.
The official package snapshot is the one used by the original failing CI run.

```sh
mkdir -p .work
git clone https://github.com/georghammerl/spack.git .work/spack-unpatched
git -C .work/spack-unpatched checkout --detach ab3f3ac5f48d4d636d82bb317e24dd59494f4d32
git clone https://github.com/georghammerl/spack.git .work/spack-patched
git -C .work/spack-patched checkout --detach fc955cd6fd66d94affacf005f831cd68418e20a6
git clone https://github.com/spack/spack-packages.git .work/spack-packages
git -C .work/spack-packages checkout --detach 8933fbb6925be105d493d2eff0c0b375a2ac1cc8

python3 reproduce.py --spack .work/spack-unpatched \
  --packages .work/spack-packages --output .work/unpatched

python3 reproduce.py --spack .work/spack-patched \
  --packages .work/spack-packages --output .work/patched
```

Run the second command even if the first exits unsuccessfully. For an existing
installation, supply its checkout paths instead. `--gcc /path/to/gcc-13` selects
the host GCC explicitly; matching `g++-13` and `gfortran-13` must be beside it.
Newer GCC versions are allowed for investigation, but are not the original
GCC-13 scenario and may not be supported by this oneAPI release.

The exact cached Bzip2 hash is
`uvnzqyaxcaq5r3l6mh46yow7dfbp5fnp`, taken from the failing CI lockfile.
It is installed in binary-only mode. If it disappears from the public cache,
the experiment stops explicitly rather than trying to build with absent GCC 10.

## Interpret results honestly

Inspect `commands.log`, `result.json`, and `environment/spack.lock` in each
output directory.

- A dependency/bootstrap/cache failure is **not** a reproduction.
- The diagnostic step must confirm both runtime versions in the link graph.
- A consumer link failure with the missing GCC-13 symbol on the unpatched
  revision, followed by a successful patched link and execution, would
  reproduce the original symptom.
- If both builds pass, the reduction did **not** reproduce that symptom.
  Keep the path/symbol evidence; do not describe the patch as validated.
- Wrong-node lookup or different wrapper paths alone establish neither the
  cause of a link failure nor the correctness of the proposed architecture.

The workflow in `.github/workflows/reproduce.yml` is manual-only and runs both
revisions independently. It uploads diagnostics even on failure. It can be
used after deciding to publish this directory as a standalone repository;
no repository creation or workflow dispatch is performed by these scripts.

## Validation status

Validated locally on 2026-11-17 with **oneAPI 2025.3.2 and host GCC 15.2.0**:

| Check | Result |
| --- | --- |
| Native source smoke test | Passed; executable printed `42` |
| Real Spack compiler/dependency installation and concretization | Passed |
| Unpatched consumer link | Failed with `std::ios_base_library_init()@GLIBCXX_3.4.32` |
| Proposed-patch consumer link, using the same lockfile and installed dependencies | Passed |
| Patched executable | Passed; printed `42` |

The local result is a GCC-15 variation of the original GCC-13 failure. The
Ubuntu/GCC-13 workflow has **not** been run.

The unpatched wrapper includes the GCC 10 runtime directory but omits the
GCC 15 runtime directory. The proposed patch includes both for linking and
selects the newer runtime for RPATH. The linker's symbol trace then identifies
the GCC 15 runtime's `libstdc++.so.6` as defining the missing symbol.
Separately, oneAPI's C++ link trace selects GCC 15's **development**
`libstdc++.so`; it is not replaced with a development file from `gcc-runtime`.
The copied GCC 15 runtime is byte-identical to the compiler-selected runtime.
Lockfile and dependency-library SHA256 values were unchanged across the
before/after comparison.

Local evidence is retained under `.work/unpatched-gcc15/`:
`diagnostics.log`, `consumer.log`, `patched-diagnostics.log`,
`patched-consumer.log`, `patched-execution.log`, and `comparison.json`.
These generated files and installed compilers are ignored by Git.

To repeat the same-store comparison after an unpatched run, use the patched
Spack checkout with the **existing** configuration and environment; do not
reconcretize. For example, from this directory:

```sh
(
export SPACK_DISABLE_LOCAL_CONFIG=1
patched=.work/spack-patched/bin/spack
config=.work/unpatched-gcc15/config
environment=.work/unpatched-gcc15/environment

"$patched" -C "$config" -e "$environment" python diagnose.py
"$patched" -C "$config" -e "$environment" install \
  --overwrite --yes-to-all --fail-fast --verbose --show-log-on-error \
  --use-buildcache package:never,dependencies:auto
prefix=$("$patched" -C "$config" -e "$environment" location -i runtime-repro-consumer)
readelf -d "$prefix/bin/runtime-repro"
ldd "$prefix/bin/runtime-repro"
"$prefix/bin/runtime-repro"
)
```

The overwrite option deliberately rebuilds the experiment's consumer even
if it is already installed. No dependency rebuild or PR modification is
needed. These results establish a reproducible symptom and a path-selection
difference, not that manually resetting query state is the right upstream
API design.
