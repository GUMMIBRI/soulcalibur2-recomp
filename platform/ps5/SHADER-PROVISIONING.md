# PS5 shader provisioning

The PS5 build can read precompiled SPIR-V without a target shaderc library.
This is a cache/provisioning path, not full on-console shader compilation.
Unknown dynamic guest materials still need compilation. Until enough shaders
are provisioned or a target compiler is linked, missing shaders block rendering.

The game searches shader-cache/ under the same USB/installed/read-only content
roots used for textures. It reads only that cache. Missing/invalid entries fail
with their SHA-256 identifier and capture the exact request to shader-requests/
beside writable settings.ini. No generic RECOMP_SHADER_CACHE writes occur on
PS5. No Linux shaderc dynamic-library names are tried. Static shaderc remains
an optional future RECOMP_SHADERC_LINKED configuration.

Capture is limited to 128 requests per process, 256 directory entries and
64 MiB total disk contents. Source is limited to 2 MiB, macros to 128 entries of
4096 bytes, entry names to 256 bytes, and SPIR-V to 4 MiB. These are limits,
not claims that every game material has been inventoried. Requests/cache
are derived from the user's game; keep them private and out of Git/releases.

## Host operation

Copy requests from the writable content folder into private/ locally, then:

```powershell
python tools/ps5_provision_shaders.py private/shader-requests private/shader-cache --glslang PATH/TO/glslang.exe
```

Copy the resulting *.spv files into the content folder's shader-cache/.
This tool does not contact or write to the console. It rejects mismatched
request filenames and malformed requests. It invokes the caller-supplied
public compiler with argument arrays, no shell. A failed compile produces no
new payload. A private receipt records compiler executable hash/version,
source hash, output hash and diagnostics. No compiler/tool download is needed
with the existing PE glslang installation.

## SC2REQ01 request format

All integers are unsigned 32-bit little-endian. Text is UTF-8 preceded by its
byte length. No trailing bytes are permitted by the host tool.

1. Eight bytes: SC2REQ01.
2. Stage: 0 vertex, 4 fragment (SPIR-V execution-model numbers).
3. Language: 0 HLSL, 1 GLSL.
4. Entry-point text.
5. Define count, then each ordered define text (NAME or NAME=VALUE).
6. Exact source text.

Filename/key is SHA-256 of the entire request, including the version. Profile
01 uses Vulkan 1.0 / SPIR-V 1.0, automatic location mapping, uniform set 1 for
vertex and 3 for fragment, RECOMP_SAMPLE_COUNT=4 unless supplied, and HLSL
offsets. Host HLSL uses glslang -Os; GLSL is left unoptimized to preserve names.
This provisions the same binding policy as upstream; it is not a claim of
byte-identical output to a different shaderc/glslang version. Bump the request
version for any profile/serialization change. Source, ordered defines, language,
stage and entry point all participate in identity.

## SC2SPV01 payload format

ASCII lines SC2SPV01, 64-character lowercase request hash, entry-point name,
each terminated by LF, then raw SPIR-V bytes. Runtime header reads are bounded.
Before use, both implementations check size, word alignment, SPIR-V 1.0 magic,
reserved header word, nonzero ID bound, instruction word-count boundaries and
an OpEntryPoint with the expected name/execution model. This is structural
validation, not a replacement for the driver's SPIR-V semantic validation.

## Evidence

The modified compiler and real host units cross-compile with the public PS5
SDK. Two synthetic requests (HLSL vertex and GLSL fragment) were compiled with
the existing glslang and passed payload validation; a truncated request was
rejected. No guest/game-derived shader collection, console run or playable
output is claimed. Existing desktop shaderc/cache behavior is retained.
