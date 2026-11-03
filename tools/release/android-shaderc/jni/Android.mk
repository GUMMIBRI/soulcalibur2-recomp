# SPDX-License-Identifier: GPL-3.0-or-later
# libshaderc_shared.so for Android, from the shaderc sources the NDK carries (sources/third_party/shaderc), with
# HLSL: the SDL_GPU presenter compiles its shaders with it at run time and opens it by that name
# (doa2u-re recomp-runtime d3d_shader_compiler.cpp). Built by tools/release/android.sh with ndk-build.
LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := shaderc_shared
LOCAL_SRC_FILES := empty.c
LOCAL_WHOLE_STATIC_LIBRARIES := shaderc
LOCAL_LDLIBS := -latomic
include $(BUILD_SHARED_LIBRARY)
$(call import-module,third_party/shaderc)
