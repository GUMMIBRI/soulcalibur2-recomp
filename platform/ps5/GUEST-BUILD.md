# Authenticated guest compilation

`tools/ps5_compile_guest.py` implements the generated-program part of the PS5
build. It is separate from the already compiled host/renderer/adapter units.
It does not lift unknown executables, invent missing guest functions, link a
payload, upload files or run the game.

The tool requires the actual supported media-patched USA XBE SHA-256
`7ce12851850ab46766f77c612b251afe7c8bd81f879e11b4836bdf766be542c6`, read in
place through `--xbe`. The retail hash is accepted by the existing runner,
but this build helper specifically compiles the patched-input lift described
by `tools/build_game.py`. There is no caller-supplied hash override.

Before writing build output it validates the lift receipt, pinned lifter commit
`653782777dee86b70030622a64efb53d6d06cc0b`, clean tracked lifter sources,
contiguous generated chunk sequence, exact manifest, zero uninitialized EBP
prologues, and the current runtime's manual-function binding hash. The supplied
HDD-ready extraction currently fails the executable hash check. A fabricated
receipt cannot bypass that check. Receipts establish local provenance, not a
cryptographic proof that a compiler generated every instruction correctly.

After a supported input has been lifted:

```powershell
python tools/ps5_compile_guest.py --xbe PATH/TO/Default.xbe --sdk C:/.pe/ps5-native/gpu-platform-20261030/deps/ps5-payload-sdk --llvm C:/.pe/ps5-native/gpu-platform-20261030/deps/llvm/bin
```

Use `--program private/program` to select the lift receipt directory explicitly.
Only USA source is accepted; PAL needs its rewritten runtime and separate
provenance handling before being supported here.

The isolated source directory contains hardlinks only to authenticated chunks,
dispatch and declarations. The lifter's generated `recomp_types.h` is deliberately
excluded, matching the shared runtime CMake's include isolation. Quoted includes
therefore select the merged runtime's actual compatibility header. Hardlinks
consume no second copy of the large generated C; the helper never writes to
them. A filesystem without hardlink support fails instead of copying silently.
Any unexpected staged file, including an injected sibling header, is rejected.

Compilation uses the PS5 SDK and LLVM with PIC, emulated TLS, strict implicit
function declarations, deterministic guest floating-point/aliasing/wrap flags,
and forced inclusion of SC2's `x87_math.h`. No fail-loud missing-body stubs are
generated; unresolved original functions remain a real linker failure.

Outputs are under `private/ps5-guest-objects/<manifest>/`. `receipt.json` records
actual source/object hashes, compiler identity, commands, diagnostics, SDK path,
runtime header hashes and the original lift identities. `compiled` is true only
when every real source compiles and reauthentication still passes. Linking must
revalidate these inputs and object hashes before consuming them. These are
private game-derived objects; never add them or their receipts to Git/releases.

Current evidence: helper syntax/help and rejection of the supplied unsupported
XBE were checked. No supported lift has been available, so positive guest
compilation and final guest/host linkage remain unclaimed.

## In-place lift input and final link

`tools/build_game.py lift` now accepts `SC2_XBE_PATH` pointing at an existing
extraction, avoiding a duplicate disc folder. It retains the exact existing
fingerprint gate. `SC2_PYTHON` selects an existing interpreter with capstone;
the default uses a platform-correct private venv or the invoking interpreter.
The lift receipt records the source path privately.

After an actual supported lift and successful guest compilation, the linker
accepts `--full-runner --guest-receipt PATH/receipt.json --xbe PATH/Default.xbe`.
It reauthenticates actual input/lift/source/manual hashes, every compiled object,
and the runtime headers before consuming guest objects. Add `--strict-shared`
for the shared-runner link, or `--payload` for a real SDK CRT1 PIE ELF with an
explicit `_start` entry and public SDK linker layout. The payload path verifies
its nonzero entry is inside executable ELF load memory and emits separate
payload receipts/logs. No executable/payload has been produced yet; the owner
input still fails the supported fingerprint gate. The CRT executable path is
implemented but cannot receive a positive full-game link check until then.

A payload ELF is not a PlayStation install package or a human-tested game.
No boot metadata, console installation, launch or game-success bodies are
invented by this tooling. `ps5_package.py` remains the separate private
owner-input packager.
