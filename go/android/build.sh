#!/bin/sh
# Binds the Go game into app/libs/morse.aar, then runs Gradle.
#   ./build.sh            -> app/build/outputs/apk/debug/app-debug.apk
#   ./build.sh release    -> app/build/outputs/bundle/release/app-release.aab (for Play; needs keystore.properties)
# Needs ANDROID_HOME (default ~/Android/Sdk) with an NDK, and Gradle: GRADLE, else gradle on
# PATH, else ~/Android/gradle-8.11.1.
set -e
cd "$(dirname "$0")"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$(ls -d "$ANDROID_HOME"/ndk/* | sort -V | tail -1)}"
EBITENMOBILE="$(go env GOPATH)/bin/ebitenmobile"
[ -x "$EBITENMOBILE" ] || go install github.com/hajimehoshi/ebiten/v2/cmd/ebitenmobile@v2.10.5
# max-page-size: Play rejects native libs not aligned for 16 KB pages (NDK r27 still links at 4 KB)
"$EBITENMOBILE" bind -target android/arm64 -trimpath -ldflags="-s -w -extldflags=-Wl,-z,max-page-size=16384" -javapkg com.regiscamimura.morse -androidapi 23 \
    -o app/libs/morse.aar ../mobile
GRADLE="${GRADLE:-$(command -v gradle || echo "$HOME/Android/gradle-8.11.1/bin/gradle")}"
TASK=assembleDebug; [ "$1" = release ] && TASK=bundleRelease
"$GRADLE" clean $TASK # clean: incremental packaging leaves dead space in the APK
