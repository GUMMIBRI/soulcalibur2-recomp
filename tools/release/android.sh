#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# The Android build (64-bit ARM, Android 10 and later): build/Soulcalibur2Recomp-android.apk, one app with the
# launcher and the game. The game is a library (libsoulcalibur2.so) that the app starts in a process of its own
# (android/: GameActivity.java); the launcher is recomp-common's, a library too. SDL 3 is built from source (its Java
# half is compiled into the app) and shaderc from the copy the NDK carries (tools/release/android-shaderc).
# On the Mac, after the lift (private/program):
#   brew install openjdk@17 android-commandlinetools ninja
#   sdkmanager "platforms;android-34" "build-tools;34.0.0" "ndk;27.2.12479018"
#   tools/release/android.sh
#
# Signing: with KEYSTORE, KEYSTORE_PASSWORD, KEY_ALIAS and KEY_PASSWORD the APK is signed with that key. They are also
# read from the file SIGNING names (default ~/.config/soulcalibur2-recomp/android-signing.env, outside the repository),
# as lines of NAME="value". Without either it is signed with the Android debug key, which is fine for sideloading your
# own build; RELEASE=1 refuses that, because a published APK has to carry the same key every time or it won't install
# over the one before.
set -eu
root=$(cd "$(dirname "$0")/../.." && pwd)
deps="$root/build/deps"
SDL_VERSION=3.4.16
SDL_SHA256=7322236cd12090c3eb40b9728be4d49c76f66ad17d04369584d4ecad5cf77c68
SIGNING="${SIGNING:-$HOME/.config/soulcalibur2-recomp/android-signing.env}"
if [ -z "${KEYSTORE:-}" ] && [ -f "$SIGNING" ]; then
    . "$SIGNING"
fi
if [ -n "${RELEASE:-}" ] && [ -z "${KEYSTORE:-}" ]; then
    echo "error: a release APK needs the signing key ($SIGNING)" >&2
    exit 1
fi

if [ -z "${ANDROID_HOME:-}" ]; then
    for candidate in /opt/homebrew/share/android-commandlinetools "$HOME/Library/Android/sdk" "$HOME/Android/Sdk"; do
        [ -d "$candidate/platforms" ] && ANDROID_HOME="$candidate" && break
    done
fi
[ -d "${ANDROID_HOME:-}" ] || { echo "error: no Android SDK found; set ANDROID_HOME" >&2; exit 1; }
export ANDROID_HOME
NDK="${ANDROID_NDK_HOME:-$ANDROID_HOME/ndk/27.2.12479018}"
[ -f "$NDK/build/cmake/android.toolchain.cmake" ] || { echo "error: no NDK 27.2 in $NDK" >&2; exit 1; }
if [ -z "${JAVA_HOME:-}" ] && [ -d /opt/homebrew/opt/openjdk@17 ]; then
    export JAVA_HOME=/opt/homebrew/opt/openjdk@17
fi
STRIP=$(ls -d "$NDK"/toolchains/llvm/prebuilt/*/bin/llvm-strip | head -1)
ANDROID="-DCMAKE_TOOLCHAIN_FILE=$NDK/build/cmake/android.toolchain.cmake -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-29 -DANDROID_STL=c++_static -Wno-deprecated"
mkdir -p "$deps"

# SDL 3 as a shared library (SDL's Java half loads libSDL3.so by name)
sdl="$deps/SDL3-$SDL_VERSION"
if [ ! -d "$sdl/src" ]; then
    curl -fsSL -o "$sdl.tar.gz" "https://github.com/libsdl-org/SDL/releases/download/release-$SDL_VERSION/SDL3-$SDL_VERSION.tar.gz"
    echo "$SDL_SHA256  $sdl.tar.gz" | shasum -a 256 -c - >/dev/null
    tar -xzf "$sdl.tar.gz" -C "$deps"
fi
if [ ! -f "$deps/sdl-android/lib/libSDL3.so" ]; then
    cmake -S "$sdl" -B "$deps/sdl-android-build" -G Ninja -DCMAKE_BUILD_TYPE=Release -DSDL_SHARED=ON -DSDL_STATIC=OFF \
        -DSDL_TEST_LIBRARY=OFF -DCMAKE_INSTALL_PREFIX="$deps/sdl-android" $ANDROID >/dev/null 2>&1
    cmake --build "$deps/sdl-android-build" --target install >/dev/null
fi
# shaderc with HLSL, from the NDK's copy (the SDL_GPU presenter compiles its shaders with it at run time)
shaderc="$root/build/android-shaderc"
if [ ! -f "$shaderc/libs/arm64-v8a/libshaderc_shared.so" ]; then
    echo "building shaderc for Android (a few minutes, once)"
    "$NDK/ndk-build" -C "$root/tools/release/android-shaderc" NDK_PROJECT_PATH=. NDK_OUT="$shaderc/obj" \
        NDK_LIBS_OUT="$shaderc/libs" -j"$(sysctl -n hw.ncpu 2>/dev/null || nproc)" > "$shaderc.log" 2>&1 ||
        { tail -20 "$shaderc.log" >&2; exit 1; }
fi

# The game and the launcher, each a library (CMake makes a program a library on Android)
export SC2_SRC_DIR=build/src-android SC2_RUNNER_DIR=build/android-runner SC2_LAUNCHER_DIR=build/android-launcher
export SC2_CMAKE_ARGS="$ANDROID -DSDL3_DIR=$deps/sdl-android/lib/cmake/SDL3"
python3 "$root/tools/build_game.py" build
python3 "$root/tools/build_game.py" launcher

# The app's libraries, SDL's Java half, the licenses and the Shader feature's presets, staged for Gradle
staged="$root/build/release-android"
libs="$staged/jniLibs/arm64-v8a"
rm -rf "$staged" && mkdir -p "$libs" "$staged/assets"
cp "$deps/sdl-android/lib/libSDL3.so" "$shaderc/libs/arm64-v8a/libshaderc_shared.so" "$libs/"
cp "$root/build/android-runner/librecomp_program_runner.so" "$libs/libsoulcalibur2.so"
cp "$root/build/android-launcher/libsoulcalibur2-launcher.so" "$libs/"
"$STRIP" --strip-unneeded "$libs"/*.so
mkdir -p "$staged/assets/licenses"
cp "$root/LICENSE" "$root/THIRD_PARTY_NOTICES.md" "$staged/assets/"
cp -R "$root/docs/licenses/." "$staged/assets/licenses/"
cp -R "$("$root/tools/shaders.sh")" "$staged/assets/shaders"

apk="$root/build/Soulcalibur2Recomp-android.apk"
set -- -PstagedDir="$staged" -PsdlDir="$sdl"
if [ -n "${KEYSTORE:-}" ]; then
    set -- "$@" -PkeyStore="$KEYSTORE" -PkeyStorePassword="$KEYSTORE_PASSWORD" -PkeyAlias="$KEY_ALIAS" -PkeyPassword="$KEY_PASSWORD"
fi
(cd "$root/android" && ./gradlew --console=plain -q assembleRelease "$@")
cp "$root/android/app/build/outputs/apk/release/app-release.apk" "$apk"
echo "built $apk ($(du -h "$apk" | cut -f1))"
