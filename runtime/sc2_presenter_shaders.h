/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Exact shared presenter gamma source from tmcleroy/doa2u-re
   8464693079a9feb32ab38136a224caf9163d6b71, also used by the host provisioner. */
#pragma once
inline constexpr char kGammaShader[] =
    "[[vk::binding(0, 2)]] Texture2D pixels : register(t0);\n"
    "[[vk::binding(0, 2)]] SamplerState pixel_sampler : register(s0);\n"
    "[[vk::binding(0, RECOMP_UNIFORM_SET)]] cbuffer Gamma : register(b0) { float4 ramp[256]; };\n"
    "float4 vs_main(uint id : SV_VertexID) : SV_Position {\n"
    " float2 p = float2((id << 1) & 2, id & 2);\n"
    " return float4(p * float2(2,-2) + float2(-1,1), 0, 1); }\n"
    "float4 ps_main(float4 p : SV_Position) : SV_Target {\n"
    " float4 c = pixels.Load(int3(p.xy, 0));\n"
    " uint3 i = (uint3)(saturate(c.rgb) * 255 + 0.5);\n"
    " return float4(ramp[i.r].r, ramp[i.g].g, ramp[i.b].b, c.a); }\n";

// The count pass uses the same exact source transform on host and console.
#include <string>
inline void sc2PresenterCountShader(std::string &source)
{
    static const std::string result = "    return shaded;\n";
    const auto at = source.rfind(result);
    if (at != std::string::npos)
        source.replace(at, result.size(), "    return float4(1, 1, 1, 1);\n");
}
