// SPDX-License-Identifier: GPL-3.0-or-later
// Android: the game is a library (libsoulcalibur2.so) that its activity (android/, GameActivity.java) loads in a
// process of its own and calls the main of, with the launcher's arguments. What a program started elsewhere gets from
// the launcher, the activity gives as variables: RECOMP_FOLDER, the player's folder for the game (the current folder
// elsewhere), and RECOMP_LOG, the file its output goes to (logs/game.log). Without a log the output goes to the
// system's log (adb logcat -s soulcalibur2). Taken from cps2recomp's port/android.cpp.
#ifdef __ANDROID__
#include "sc2_android.h"
#include "sc2_settings.h"
#include "sc2_touch.h"

#include <SDL3/SDL.h>
#include <android/log.h>
#include <fcntl.h>
#include <jni.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>

namespace {

// The standard output and error, a line at a time to the system's log
void toSystemLog()
{
    static int pipes[2];
    if (pipe(pipes) != 0) return;
    setvbuf(stdout, nullptr, _IOLBF, 0);
    setvbuf(stderr, nullptr, _IONBF, 0);
    dup2(pipes[1], 1);
    dup2(pipes[1], 2);
    std::thread([] {
        std::string line;
        char buffer[512];
        ssize_t got;
        while ((got = read(pipes[0], buffer, sizeof buffer)) > 0) {
            for (ssize_t i = 0; i < got; i++) {
                if (buffer[i] == '\n') {
                    __android_log_write(ANDROID_LOG_INFO, "soulcalibur2", line.c_str());
                    line.clear();
                } else {
                    line += buffer[i];
                }
            }
        }
    }).detach();
}

} // namespace

void sc2_android_start()
{
    // Landscape either way up, as the launcher (the manifest's SDL_ENV values don't reach the game's process), and
    // the back button for the game (it opens the menu) instead of closing it
    SDL_SetHint(SDL_HINT_ORIENTATIONS, "LandscapeLeft LandscapeRight");
    SDL_SetHint(SDL_HINT_ANDROID_TRAP_BACK_BUTTON, "1");
    // SDL's systems that reach Java start here, on the activity's own thread's stack (host_call.h has the rest),
    // and the touch screen's controls with them
    if (!SDL_InitSubSystem(SDL_INIT_VIDEO | SDL_INIT_GAMEPAD | SDL_INIT_HAPTIC))
        __android_log_print(ANDROID_LOG_WARN, "soulcalibur2", "SDL: %s", SDL_GetError());
    sc2_touch_init();
    if (const char *folder = getenv("RECOMP_FOLDER"); folder && *folder) {
        if (chdir(folder) != 0) __android_log_print(ANDROID_LOG_WARN, "soulcalibur2", "no folder %s", folder);
    }
    // (not freopen: the standard output's descriptor is the system's, and fdsan stops a process that closes it)
    const char *log = getenv("RECOMP_LOG");
    const int file = log && *log ? open(log, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644) : -1;
    if (file >= 0) {
        dup2(file, 1);
        dup2(file, 2);
        close(file);
        setvbuf(stdout, nullptr, _IOLBF, 0);
        setvbuf(stderr, nullptr, _IONBF, 0);
    } else {
        toSystemLog();
    }
}

bool sc2_android_start_again(const std::vector<std::string> &args)
{
    // GameActivity.startAgain(String[]): the game in a new process with these arguments, its result the launcher's
    JNIEnv *env = static_cast<JNIEnv *>(SDL_GetAndroidJNIEnv());
    jobject activity = static_cast<jobject>(SDL_GetAndroidActivity());
    if (!env || !activity) return false;
    jclass activity_class = env->GetObjectClass(activity);
    jmethodID start_again = env->GetMethodID(activity_class, "startAgain", "([Ljava/lang/String;)Z");
    if (!start_again) {
        env->ExceptionClear();
        return false;
    }
    jclass string_class = env->FindClass("java/lang/String");
    jobjectArray arguments = env->NewObjectArray(static_cast<jsize>(args.size()), string_class, nullptr);
    for (size_t i = 0; i < args.size(); i++) {
        jstring arg = env->NewStringUTF(args[i].c_str());
        env->SetObjectArrayElement(arguments, static_cast<jsize>(i), arg);
        env->DeleteLocalRef(arg);
    }
    const bool started = env->CallBooleanMethod(activity, start_again, arguments);
    env->DeleteLocalRef(arguments);
    env->DeleteLocalRef(activity_class);
    env->DeleteLocalRef(activity);
    return started;
}

// For the launcher, which has no game program to run with --list-features: it opens the game's library and asks it
// (recomp-common/launcher/src/game_process.cpp). The text is the caller's to free.
extern "C" __attribute__((visibility("default"))) char *RecompListFeatures()
{
    return strdup(recomp::FeatureListText(sc2::Features()).c_str());
}
#endif
