# PS5 target-native shader compiler

This optional dependency is built from public sources under ignored
`private/ps5-shaderc/`; no prebuilt Windows or Linux compiler library is linked
into the PS5 game. `sources.json` pins each exact commit and official source
archive SHA-256. Shaderc v2025.5 pins the glslang, SPIRV-Tools and SPIRV-Headers
revisions in its own DEPS file; tests/examples/executables are excluded, so
GoogleTest/RE2/Effcee/Abseil are not required or fetched.

`DEPENDENCY-LICENSES.txt` preserves all four source distributions' complete
license files, including glslang's multiple component notices. Shaderc and
SPIRV-Tools are Apache-2.0, SPIRV-Headers carries its Khronos notices, and
glslang has mixed permissive component licenses as described in its file.
These are compatible compiler dependencies, not console SDK or game code.
THIRD_PARTY_NOTICES.md also references these dependency notices.

## Build

Use the existing public SDK/LLVM/CMake/Ninja; this builds static target
libraries and never launches the game or any PS5 executable:

```powershell
python tools/ps5_build_shaderc.py --fetch --sdk C:/.pe/ps5-native/gpu-platform-20261030/deps/ps5-payload-sdk --llvm C:/.pe/ps5-native/gpu-platform-20261030/deps/llvm/bin --cmake C:/.pe/tools/cmake/cmake-4.4.4-windows-x86_64/bin/cmake.exe --ninja C:/.pe/tools/ninja/ninja.exe
```

`--fetch` is required only when a pinned archive is absent. Downloaded bytes
must match the lock before their final filename is created; interrupted
extraction is resumed only by comparing each existing source file to the
verified archive. A completion marker is written after the whole tree is read.
Source files are never modified by the builder. All outputs, commands, source
identities, logs and library hashes remain private. Jobs are limited to 1–8,
default 4. No dependency model or service is downloaded or started.

The public source has an install-export mismatch between shaderc's skipped
install and glslang's export validation with CMake 4.4. `CMAKE_SKIP_INSTALL_RULES`
is enabled because this dependency is consumed in place, not installed; no
compiler source patch or disabled shader optimization is needed.

## Parent integration contract

* Headers: `private/ps5-shaderc/source/libshaderc/include`.
* Combined static archive: `private/ps5-shaderc/build/libshaderc/libshaderc_combined.a`.
* Compile actual `runtime/d3d_shader_compiler.cpp` with
  `RECOMP_SHADERC_LINKED=1` and that include path, and link the archive with the
  actual PS5 SDK C++/pthread/math services already used by the runner.
* Keep provisioned-cache identity, byte validation, bounded capture and failure
  reporting. Target-native compilation covers exact previously unseen generated
  materials, but does not justify fallback or placeholder shader substitution.

The toolchain uses x86_64-sie-ps5, public SDK libc++, PIC, emulated TLS,
exceptions and RTTI, matching the existing SC2 native runtime ABI. Thread/API
runtime behavior and first-use compiler latency still require a future human
console test; successful compilation/linkage is not gameplay qualification.

## Compilation evidence

All 268 upstream build steps completed without compiler-source patches.
The combined archive is 25,794,914 bytes, SHA-256
`a6e31a6fc45ce4c32d7e7158fe87ff50b2346f2282ef517dacd5b26d04b7e2ea`.
The private receipt records all archives and component static-library hashes.
A second invocation of the completed recipe confirmed its cache/source markers
and required no compiler work. This establishes target compilation only; parent
strict linkage and future human console behavior are separate milestones.

Parent integration now cross-compiles the native runtime and strictly links the
actual kernel/GPU host module: all340 dynamic imports have SDK providers.
The full runner link reports only33 generated guest symbols. No target shader
compilation or gameplay has been exercised on PS5.
