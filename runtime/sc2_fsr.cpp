/* SPDX-License-Identifier: GPL-3.0-or-later */
#if defined(SC2_PS5)
#include "sc2_fsr.h"
#include "sc2_fsr_shaders.h"
#include "d3d_shader_compiler.h"
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <new>
#include <string>

namespace {
enum Status { Off, Bypassed, Active, Fallback };
std::atomic<unsigned> options{0u}; // disabled; strong RCAS (zero stops)
std::atomic<unsigned> generation{1u};
std::atomic<Status> status{Off};
constexpr auto kFormat = SDL_GPU_TEXTUREFORMAT_R8G8B8A8_UNORM;
constexpr auto kUsage = SDL_GPU_TEXTUREUSAGE_SAMPLER | SDL_GPU_TEXTUREUSAGE_COLOR_TARGET;
}

struct Sc2Fsr {
    SDL_GPUDevice *device = nullptr;
    SDL_GPUGraphicsPipeline *easu = nullptr, *rcas = nullptr;
    SDL_GPUSampler *sampler = nullptr;
    SDL_GPUTexture *input = nullptr, *scaled = nullptr, *sharpened = nullptr;
    unsigned input_width = 0, input_height = 0, width = 0, height = 0;
    unsigned failed_generation = 0u;
    unsigned failed_input_width = 0u, failed_input_height = 0u;
    unsigned failed_width = 0u, failed_height = 0u;
};

extern "C" void sc2_fsr_set_options(int enabled, int sharpness)
{
    const unsigned setting = (enabled ? 1u : 0u) | (unsigned(std::clamp(sharpness, 0, 2)) << 1u);
    if (options.exchange(setting, std::memory_order_relaxed) != setting)
        generation.fetch_add(1u, std::memory_order_relaxed);
    if (!enabled) status.store(Off, std::memory_order_relaxed);
}
extern "C" const char *sc2_fsr_status(void)
{
    static const char *const names[] = {"Off", "Bypassed", "Active", "Fallback"};
    return names[status.load(std::memory_order_relaxed)];
}

namespace {
SDL_GPUShader *shader(Sc2Fsr &state, const char *source, bool vertex)
{
    RecompCompiledShader compiled;
    std::string error;
    if (!recomp_shader_compile(source, vertex ? "vs_main" : "ps_main", vertex,
            RecompShaderTarget::Spirv, {}, compiled, error)) {
        std::fprintf(stderr, "SC2 FSR1: shader provisioning/compile failed: %s\n", error.c_str());
        return nullptr;
    }
    SDL_GPUShaderCreateInfo info{};
    info.code = compiled.code.data(); info.code_size = compiled.code.size();
    info.entrypoint = compiled.entry_point.c_str(); info.format = SDL_GPU_SHADERFORMAT_SPIRV;
    info.stage = vertex ? SDL_GPU_SHADERSTAGE_VERTEX : SDL_GPU_SHADERSTAGE_FRAGMENT;
    info.num_samplers = vertex ? 0u : 1u; info.num_uniform_buffers = vertex ? 0u : 1u;
    return SDL_CreateGPUShader(state.device, &info);
}

SDL_GPUGraphicsPipeline *pipeline(Sc2Fsr &state, SDL_GPUShader *vertex, SDL_GPUShader *fragment)
{
    SDL_GPUColorTargetDescription color{}; color.format = kFormat;
    SDL_GPUGraphicsPipelineCreateInfo info{};
    info.vertex_shader = vertex; info.fragment_shader = fragment;
    info.primitive_type = SDL_GPU_PRIMITIVETYPE_TRIANGLELIST;
    info.multisample_state.sample_count = SDL_GPU_SAMPLECOUNT_1;
    info.target_info.color_target_descriptions = &color;
    info.target_info.num_color_targets = 1;
    return SDL_CreateGPUGraphicsPipeline(state.device, &info);
}

bool pipelines(Sc2Fsr &state)
{
    if (state.easu && state.rcas && state.sampler) return true;
    if (state.easu) SDL_ReleaseGPUGraphicsPipeline(state.device, state.easu);
    if (state.rcas) SDL_ReleaseGPUGraphicsPipeline(state.device, state.rcas);
    if (state.sampler) SDL_ReleaseGPUSampler(state.device, state.sampler);
    state.easu = state.rcas = nullptr; state.sampler = nullptr;
    if (!(SDL_GetGPUShaderFormats(state.device) & SDL_GPU_SHADERFORMAT_SPIRV)) return false;
    SDL_GPUShader *vertex = shader(state, kSc2Fsr_vertex, true);
    SDL_GPUShader *easu = vertex ? shader(state, kSc2Fsr_easu, false) : nullptr;
    SDL_GPUShader *rcas = easu ? shader(state, kSc2Fsr_rcas, false) : nullptr;
    if (rcas) {
        state.easu = pipeline(state, vertex, easu);
        state.rcas = pipeline(state, vertex, rcas);
        SDL_GPUSamplerCreateInfo sample{};
        sample.min_filter = SDL_GPU_FILTER_NEAREST; sample.mag_filter = SDL_GPU_FILTER_NEAREST;
        sample.mipmap_mode = SDL_GPU_SAMPLERMIPMAPMODE_NEAREST;
        sample.address_mode_u = sample.address_mode_v = sample.address_mode_w = SDL_GPU_SAMPLERADDRESSMODE_CLAMP_TO_EDGE;
        state.sampler = SDL_CreateGPUSampler(state.device, &sample);
    }
    if (vertex) SDL_ReleaseGPUShader(state.device, vertex);
    if (easu) SDL_ReleaseGPUShader(state.device, easu);
    if (rcas) SDL_ReleaseGPUShader(state.device, rcas);
    return state.easu && state.rcas && state.sampler;
}

void releaseTextures(Sc2Fsr &state)
{
    // SDL resource release is deferred until in-flight references finish.
    if (state.input) SDL_ReleaseGPUTexture(state.device, state.input);
    if (state.scaled) SDL_ReleaseGPUTexture(state.device, state.scaled);
    if (state.sharpened) SDL_ReleaseGPUTexture(state.device, state.sharpened);
    state.input = state.scaled = state.sharpened = nullptr;
}

SDL_GPUTexture *texture(Sc2Fsr &state, unsigned width, unsigned height)
{
    SDL_GPUTextureCreateInfo info{};
    info.type = SDL_GPU_TEXTURETYPE_2D; info.format = kFormat; info.usage = kUsage;
    info.width = width; info.height = height; info.layer_count_or_depth = 1;
    info.num_levels = 1; info.sample_count = SDL_GPU_SAMPLECOUNT_1;
    return SDL_CreateGPUTexture(state.device, &info);
}

bool drawPass(Sc2Fsr &state, SDL_GPUCommandBuffer *commands, SDL_GPUGraphicsPipeline *pipeline,
    SDL_GPUTexture *input, SDL_GPUTexture *output, const float (&parameters)[8])
{
    SDL_GPUColorTargetInfo target{};
    target.texture = output; target.load_op = SDL_GPU_LOADOP_DONT_CARE; target.store_op = SDL_GPU_STOREOP_STORE;
    SDL_GPURenderPass *pass = SDL_BeginGPURenderPass(commands, &target, 1, nullptr);
    if (!pass) return false;
    SDL_BindGPUGraphicsPipeline(pass, pipeline);
    const SDL_GPUTextureSamplerBinding binding{input, state.sampler};
    SDL_BindGPUFragmentSamplers(pass, 0, &binding, 1);
    SDL_PushGPUFragmentUniformData(commands, 0, parameters, sizeof parameters);
    SDL_DrawGPUPrimitives(pass, 3, 1, 0, 0);
    SDL_EndGPURenderPass(pass);
    return true;
}
} // namespace

void sc2_fsr_destroy(Sc2Fsr *&state)
{
    if (!state) return;
    releaseTextures(*state);
    if (state->easu) SDL_ReleaseGPUGraphicsPipeline(state->device, state->easu);
    if (state->rcas) SDL_ReleaseGPUGraphicsPipeline(state->device, state->rcas);
    if (state->sampler) SDL_ReleaseGPUSampler(state->device, state->sampler);
    delete state; state = nullptr;
    status.store(Off, std::memory_order_relaxed);
}

SDL_GPUTexture *sc2_fsr_draw(Sc2Fsr *&state, SDL_GPUDevice *device, SDL_GPUCommandBuffer *commands,
    const SDL_GPUBlitRegion &source, unsigned width, unsigned height)
{
    const unsigned setting = options.load(std::memory_order_relaxed);
    const unsigned current_generation = generation.load(std::memory_order_relaxed);
    if (!(setting & 1u)) { status.store(Off); return nullptr; }
    if (!source.w || !source.h || !width || !height) { status.store(Fallback); return nullptr; }
    if (source.w > width || source.h > height || (source.w == width && source.h == height)) {
        status.store(Bypassed); return nullptr;
    }
    if (!device || !commands || !source.texture || width > 8192 || height > 8192 ||
        uint64_t(width) * height > 16u * 1024u * 1024u) {
        status.store(Fallback); return nullptr;
    }
    if (!state) state = new (std::nothrow) Sc2Fsr;
    if (!state) { status.store(Fallback); return nullptr; }
    if (state->device && state->device != device) { sc2_fsr_destroy(state); state = new (std::nothrow) Sc2Fsr; }
    if (!state) { status.store(Fallback); return nullptr; }
    state->device = device;
    if (state->failed_generation == current_generation && state->failed_input_width == source.w &&
        state->failed_input_height == source.h && state->failed_width == width && state->failed_height == height) {
        status.store(Fallback); return nullptr;
    }
    const auto fail = [&]() -> SDL_GPUTexture * {
        state->failed_generation = current_generation;
        state->failed_input_width = source.w; state->failed_input_height = source.h;
        state->failed_width = width; state->failed_height = height;
        status.store(Fallback);
        std::fprintf(stderr, "SC2 FSR1: native presentation retained: %s\n", SDL_GetError());
        return nullptr;
    };
    if (!pipelines(*state)) return fail();
    if (!state->input || !state->scaled || !state->sharpened ||
        state->input_width != source.w || state->input_height != source.h ||
        state->width != width || state->height != height) {
        releaseTextures(*state);
        state->input = texture(*state, source.w, source.h);
        state->scaled = texture(*state, width, height); state->sharpened = texture(*state, width, height);
        state->input_width = source.w; state->input_height = source.h; state->width = width; state->height = height;
        if (!state->input || !state->scaled || !state->sharpened) return fail();
    }
    // Copy exactly the cropped/layered game rectangle, so AMD gathers cannot
    // sample unrelated pixels from the source target or outside its viewport.
    SDL_GPUBlitInfo compact{}; compact.source = source;
    compact.destination = {state->input, 0, 0, 0, 0, source.w, source.h};
    compact.load_op = SDL_GPU_LOADOP_DONT_CARE; compact.filter = SDL_GPU_FILTER_NEAREST;
    compact.cycle = true;
    SDL_BlitGPUTexture(commands, &compact);
    const float parameters[8] = {float(source.w), float(source.h), float(width), float(height),
                                float((setting >> 1u) & 3u), 0, 0, 0};
    if (!drawPass(*state, commands, state->easu, state->input, state->scaled, parameters) ||
        !drawPass(*state, commands, state->rcas, state->scaled, state->sharpened, parameters)) return fail();
    state->failed_generation = 0u;
    status.store(Active);
    return state->sharpened;
}
#endif // SC2_PS5
