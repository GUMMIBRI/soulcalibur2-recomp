# Optional public FreeBSD sort adapter

The experimental application link option --platform-qsort binds qsort_r to
ps5_qsort_r from the already pinned public platform archive. It is not enabled
by default and is not a claim that native qsort_s has an incompatible ABI.

Provider: mihawk-99/PS5_PayloadSDK, revision
b83202be73e930050e00de0f1b4d9ec46c0391bf, platform/src/posix.c,
Copyright2026 Mihawk, GPL-3.0-or-later. Source SHA256:
fc85962dd36921250a2bc2c6e2a28dc07451a850d0a2452b6420fc8059341f54.

Source: https://github.com/mihawk-99/PS5_PayloadSDK/blob/b83202be73e930050e00de0f1b4d9ec46c0391bf/platform/src/posix.c

The public helper preserves the SDK's FreeBSD thunk-first comparator contract
using a nested thread-local context and ordinary qsort. It avoids delegating
that adaptation to qsort_s. Existing GPL notices/public platform attribution
remain required. The full archive is verified through the existing title-heap
provider pin; see ../memory/SOURCE.json. No new proprietary module is used.

Admission requires an actual executable STT_FUNC provider and an exact address
match for the qsort_r alias. Final disassembly must confirm the plain-qsort
route before a candidate is called ready. Native TLS/concurrency and gameplay
remain separate console qualifications; a mocked callback-order test is not
evidence of a fixed console crash.
