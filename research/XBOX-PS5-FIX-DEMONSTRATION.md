# Xbox, PC and arcade reuse: bounded fix demonstration

November6,2026. Scope: public source inspection, isolated Windows fixtures and
an opt-in link candidate. No console writes, launches or migration. Native
PS5 qsort_s callback order and the cause of SC2's failures remain unproven.

## Demonstrated conditional sort hazard

The current SDK qsort_r adapter delegates to qsort_s and expects its callback
context as the third argument. The FreeBSD caller contract itself is valid.
Exact static SC2 call sites include a Mesa shader compare_scalar route; this
establishes reachability, not that the failing attempt reached it.

The pinned public ps5_qsort_r instead uses ordinary qsort and a nested TLS
context. The working PE link recipe already selects that public route.

An agent extracted both actual helper bodies, preserving the functions except
renaming the baseline export for coexistence, and ran five Windows fixture
checks. Independent review reran them successfully:

1. SDK adapter sorts correctly with an injected context-last provider.
2. An injected context-first provider makes the SDK adapter call a valid but
   deliberately wrong comparator. This safely demonstrates the conditional
   failure without dereferencing an invalid pointer or crashing the fixture.
3. Public adapter sorts correctly with that context-last fixture.
4. Public adapter also sorts correctly with context-first injected; it never
   enters qsort_s, so its callback order is irrelevant.
5. Nested calls restore the outer context correctly.

Private receipts/source hashes: private/xbox-ps5-fix-review/PROVENANCE.json.
The fixture mocks TLS for one host thread. It does not establish real PS5 TLS,
OS-thread concurrency, native callback order or an SC2 gameplay correction.

## Minimal candidate and prediction

The sort candidate was linked and independently inspected, but remains parked
and uninstalled while the stronger TLS cleanup finding below is assessed. No
sort-routing change is included in the TLS-only experiment.

tools/ps5_link_gpu.py now offers opt-in --platform-qsort, requiring application
mode and the existing verified public title-heap archive. It forces extraction
of ps5_qsort_r, binds qsort_r to it, and checks a real executable provider plus
matching alias address. Default builds remain unchanged.

Keep renderer, shader compiler, allocator, thread wrappers, FP policy and game
objects unchanged. Verify the final ELF's actual call route; compilation alone
does not prove it. A console result would test whether avoiding this callback
dependency changes repeated SIGSEGV/XO behavior, not establish every other
requested feature. Failure must be recorded honestly; do not blend unrelated
ring, optimizer, scheduler or stack-size changes into the same experiment.

## Demonstrated TLS cleanup-order correction

SpeedBreaker's pinned port/ps5/compat/emutls.c adds PS5 to LLVM's one-round
cleanup delay. Independent inspection of the exact installed SC2 r2 binary
confirms its selected SDK emutls implementation initializes that delay to zero.
The linked glslang also has a nontrivial thread-local pool allocator, so C++
TLS destructor support is relevant, not merely an unused runtime symbol.

The local fixture exercises actual extracted SDK cleanup, shutdown and address
array helpers. With emutls cleanup injected first, the baseline frees storage
before a later callback and a fallback-style reaccess creates fresh zeroed
state instead of retaining the original callback state. Both reverse-order
controls pass. The one-round-delay candidate passes all four scenarios and
frees storage once after dependent cleanup. Independent review reran both:
baseline exit1, candidate exit0. Logical allocator ownership and pthread-key
ordering are modeled; actual libc++abi run_dtors and PS5 ordering are not run.

SC2 uses libc++abi's own pthread-key fallback, not the donor's public platform
C++ destructor alias. Therefore do not claim the donor's precise mspace_free
crash is reproduced in SC2. The current console crash cause remains unproven.

Private evidence: TLS-CLEANUP-PROVENANCE.json and TLS-DEMONSTRATION.txt under
private/xbox-ps5-fix-review. The original aligned-malloc policy is preserved;
do not enable EMUTLS_USE_POSIX_MEMALIGN or blend qsort/C++ destructor aliases,
stack resizing, scheduler changes or optimizer changes into this candidate.

Source and full Apache-2.0 WITH LLVM-exception license are retained under
platform/ps5/tls. The explicit tls-cleanup compile group creates a separately
receipted object; it is only used if deliberately selected as an extra object.
Final qualification must inspect the linked implementation for delay1, the
original manual allocation policy and unchanged C++ destructor fallback.

## Other PC/PS5 findings

- [Def Jam PS5](https://github.com/elripalda/defjam-ps5/tree/572bcab1710e5e5273d0fe09e3192c9001fa9be4): its direct glslang adapter disables SPIRV-Tools optimization, but lacks SC2's required macro API. A contract-complete reduced-optimization experiment requires exact shader replay/validation first; no wholesale compiler substitution.
- [SpeedBreaker PS5](https://github.com/bystritskiy/speedbreaker-ps5/tree/5d269f62041a0dc5528d0652ee8edc31fdf02c2e): Xbox360/PPC, useful platform reference, not an original-Xbox loader/backend replacement. Missing inspected top-level license path must be resolved before copying its code.
- Current SC2 SDL_GPU presenter already derives from a native PC backend. Windows D3D11 needs APIs/DXBC support PS5 does not expose; changing to it does not avoid native Vulkan/platform issues automatically.
- Latest upstream SC2 HEAD4ee67b5 was fetched read-only. Compared with8a914a8, inspected changes are Link hair/winding and launcher notices, not a new renderer fix. No merge, guest rebuild or asset rewrite occurred.

## Arcade findings

[MAME's Namco driver](https://github.com/mamedev/mame/blob/master/src/mame/namco/namcops2.cpp)
identifies Soulcalibur II arcade as System246, PS2-based, not NAOMI. This finite
search found unpackers, Conquest-card work and emulators, but no verified
direct SC2 arcade static-recomp project. This is not a claim none exists.

A real arcade recomp is [sys3xx-recomp](https://github.com/tonykastaneda/sys3xx-recomp/tree/c1334a12b33fa0183f45c89951940c8ee016932b),
Tekken6/BR for PS3-based System357/369. Useful source lessons include decoder
decode/close serialization, dispatching callbacks outside locks, fault thread
and module attribution, and scheduler-state watchdogs. Its decoder deferred
queue needs its own reentrancy review: it clears the queue only after invoking
callbacks, so it must not be copied wholesale.

The arcade root code's GPLv2 terms lack an inspected explicit or-later grant;
its vendored toolkit retains MIT. Resolve licenses per file before reuse.
Author-reported desktop fights are not PS5 qualification. An SC2 arcade base
would still require PS2 EE/IOP/VU/GS support and integration of home-version
guests/modes. Historical ports are not multiple runtime conversions executing
in series. No evidence currently supports a base migration as the fix.
