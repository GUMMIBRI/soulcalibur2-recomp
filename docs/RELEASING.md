# Releasing

A release's archives hold the game's program, translated from the player's own `Default.xbe`, so they are
built on a contributor's Mac, never by CI. CI (`.github/workflows/ci.yml`) proves on every push that the rest
builds; a tag makes a draft release with its text and no files (`release.yml`).

1. **The version.** Set `VERSION` (for example `0.2.0`, or `0.2.0-beta.1` for a pre-release; online play tells
   the other side this, so both players need the same) and give `CHANGELOG.md` a section `## <version>`: a
   paragraph saying what is in it (the top of the release's page), then the list. `tools/release/notes.sh
   <version>` shows the release's text.
2. **Commit and push** to main, and wait for CI.
3. **The archives**, on the Mac with the lift done (`private/program`):
   - `tools/release/macos.sh`: `build/Soulcalibur2Recomp-macOS.zip` (Homebrew's SDL3 and shaderc inside the app;
     it asks for the macOS it was built on).
   - Linux, in Docker: `docker run --rm --platform linux/amd64 -v "$PWD":"$PWD" -w "$PWD" doaxvb-build
     tools/release/linux.sh`: `build/Soulcalibur2Recomp-linux-x86_64.tar.gz`.
   - Windows, in Docker (llvm-mingw in `private/toolchains`, shaderc from `tools/release/fetch_shaderc_windows.sh`):
     `docker run --rm -v "$PWD":"$PWD" -w "$PWD" cps2recomp-build-arm64 tools/release/windows.sh`:
     `build/Soulcalibur2Recomp-windows-x64.zip`.

   - Android: `RELEASE=1 tools/release/android.sh`: `build/Soulcalibur2Recomp-android.apk`, signed with the release
     key (`~/.config/soulcalibur2-recomp/android-signing.env`, outside the repository: KEYSTORE, KEYSTORE_PASSWORD,
     KEY_ALIAS, KEY_PASSWORD). A published APK must carry the same key every time or it won't install over the one
     before. It has no update manifest: the launcher sends Android's installer the newest release's APK.

   Each of the others writes its `build/update-<system>.txt`, what the launcher updates itself from. Play each before
   uploading.
4. **Tag**: `git tag v<version> && git push origin v<version>`. The Release workflow checks the tag is `VERSION`,
   runs CI and makes the draft.
5. **Upload** to the draft the three archives, the APK, the three `update-*.txt` and `SHA256SUMS.txt`
   (`cd build && shasum -a 256 Soulcalibur2Recomp-* > SHA256SUMS.txt`), and nothing else:
   `gh release upload v<version> build/Soulcalibur2Recomp-* build/update-*.txt build/SHA256SUMS.txt`.
6. **Publish** the draft. The launcher's update looks at published releases only (pre-releases to pre-release
   versions), and only when the repository is public.
