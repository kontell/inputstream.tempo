/*
 *  Copyright (C) 2005-2021 Team Kodi (https://kodi.tv)
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later
 *  See LICENSE.md for more information.
 */

#include "DemuxStream.h"

#include "../utils/Log.h"
#include "url/URL.h"

#ifndef __STDC_CONSTANT_MACROS
#define __STDC_CONSTANT_MACROS
#endif
#ifndef __STDC_LIMIT_MACROS
#define __STDC_LIMIT_MACROS
#endif
#ifdef TARGET_POSIX
#include <stdint.h>
#endif

extern "C" {
#include <libavutil/dict.h>
#include <libavutil/opt.h>
}

#include <kodi/tools/StringUtils.h>

using namespace ffmpegdirect;
using namespace kodi::tools;

/***********************************************************
* InputSteam Client AddOn specific public library functions
***********************************************************/

std::string DemuxStream::GetStreamName()
{
  return name;
}

bool DemuxStream::GetInformation(kodi::addon::InputstreamInfo& info)
{
  info.SetStreamType(type);

  info.SetFlags(flags);
  info.SetName(name);
  info.SetCodecName(codecName);
  info.SetCodecProfile(ConvertToInputStreamProfile(codec, profile));
  info.SetPhysicalIndex(uniqueId);
  info.SetExtraData(extraData.GetData(), extraData.GetSize());
  info.SetLanguage(language);
  info.SetCodecFourCC(codec_fourcc);

  if (cryptoSession)
  {
    info.SetCryptoSession(*cryptoSession);
  }

  return true;
}

STREAMCODEC_PROFILE DemuxStream::ConvertToInputStreamProfile(AVCodecID codec, int profile)
{
  // https://github.com/xbmc/xbmc/blob/1dbab77181398ce816ea81d17d5159288fb97814/xbmc/addons/kodi-dev-kit/include/kodi/c-api/addon-instance/inputstream/stream_codec.h#L24
  // https://github.com/xbmc/xbmc/blob/1dbab77181398ce816ea81d17d5159288fb97814/xbmc/cores/VideoPlayer/DVDInputStreams/InputStreamAddon.cpp#L760
  switch (codec) {
    case AV_CODEC_ID_AAC:
      [[fallthrough]];
    case AV_CODEC_ID_AAC_LATM:
      switch (profile) {
        case AV_PROFILE_AAC_MAIN:
          return AACCodecProfileMAIN;
        case AV_PROFILE_AAC_LOW:
          return AACCodecProfileLOW;
        case AV_PROFILE_AAC_SSR:
          return AACCodecProfileSSR;
        case AV_PROFILE_AAC_LTP:
          return AACCodecProfileLTP;
        case AV_PROFILE_AAC_HE:
          return AACCodecProfileHE;
        case AV_PROFILE_AAC_HE_V2:
          return AACCodecProfileHEV2;
        case AV_PROFILE_AAC_LD:
          return AACCodecProfileLD;
        case AV_PROFILE_AAC_ELD:
          return AACCodecProfileELD;
      }

      break;
    default:
    	break;
  }

  // for everything else leave original profile
  return static_cast<STREAMCODEC_PROFILE>(profile);
}

bool DemuxStreamVideoFFmpeg::GetInformation(kodi::addon::InputstreamInfo& info)
{
  DemuxStream::GetInformation(info);

  info.SetFpsScale(iFpsScale);
  info.SetFpsRate(iFpsRate);
  info.SetHeight(iHeight);
  info.SetWidth(iWidth);
  info.SetAspect(fAspect);
  info.SetChannels(0);
  info.SetSampleRate(0);
  info.SetBitRate(0);
  info.SetBitsPerSample(0);
  info.SetBlockAlign(0);

  // The inputstream enums mirror FFmpeg's numbering one-to-one (Kodi casts
  // them straight back to AVColor* in CInputStreamAddon::GetStream), so a
  // range-checked cast is the whole mapping. Anything outside the range Kodi
  // knows degrades to unspecified rather than to garbage.
  const int space = static_cast<int>(colorSpace);
  const int range = static_cast<int>(colorRange);
  const int primaries = static_cast<int>(colorPrimaries);
  const int trc = static_cast<int>(colorTransferCharacteristic);
  info.SetColorSpace(space >= 0 && space < static_cast<int>(INPUTSTREAM_COLORSPACE_MAX)
                         ? static_cast<INPUTSTREAM_COLORSPACE>(space)
                         : INPUTSTREAM_COLORSPACE_UNSPECIFIED);
  info.SetColorRange(range >= 0 && range < static_cast<int>(INPUTSTREAM_COLORRANGE_MAX)
                         ? static_cast<INPUTSTREAM_COLORRANGE>(range)
                         : INPUTSTREAM_COLORRANGE_UNKNOWN);
  info.SetColorPrimaries(primaries >= 0 && primaries < static_cast<int>(INPUTSTREAM_COLORPRIMARY_MAX)
                             ? static_cast<INPUTSTREAM_COLORPRIMARIES>(primaries)
                             : INPUTSTREAM_COLORPRIMARY_UNSPECIFIED);
  info.SetColorTransferCharacteristic(trc >= 0 && trc < static_cast<int>(INPUTSTREAM_COLORTRC_MAX)
                                          ? static_cast<INPUTSTREAM_COLORTRC>(trc)
                                          : INPUTSTREAM_COLORTRC_UNSPECIFIED);

  if (masteringMetaData)
  {
    kodi::addon::InputstreamMasteringMetadata masteringMetadata;

    if (masteringMetaData->has_primaries)
    {
      masteringMetadata.SetPrimaryR_ChromaticityX(masteringMetaData->display_primaries[0][0].num / masteringMetaData->display_primaries[0][0].den);
      masteringMetadata.SetPrimaryR_ChromaticityY(masteringMetaData->display_primaries[0][1].num / masteringMetaData->display_primaries[0][1].den);
      masteringMetadata.SetPrimaryG_ChromaticityX(masteringMetaData->display_primaries[1][0].num / masteringMetaData->display_primaries[1][0].den);
      masteringMetadata.SetPrimaryG_ChromaticityY(masteringMetaData->display_primaries[1][1].num / masteringMetaData->display_primaries[1][1].den);
      masteringMetadata.SetPrimaryB_ChromaticityX(masteringMetaData->display_primaries[2][0].num / masteringMetaData->display_primaries[2][0].den);
      masteringMetadata.SetPrimaryB_ChromaticityY(masteringMetaData->display_primaries[2][1].num / masteringMetaData->display_primaries[2][1].den);
      masteringMetadata.SetWhitePoint_ChromaticityX(masteringMetaData->white_point[0].num / masteringMetaData->white_point[0].den);
      masteringMetadata.SetWhitePoint_ChromaticityY(masteringMetaData->white_point[1].num / masteringMetaData->white_point[1].den);
    }

    if (masteringMetaData->has_luminance)
    {
      masteringMetadata.SetLuminanceMax(masteringMetaData->max_luminance.num / masteringMetaData->max_luminance.den);
      masteringMetadata.SetLuminanceMin(masteringMetaData->min_luminance.num / masteringMetaData->min_luminance.den);
    }

    info.SetMasteringMetadata(masteringMetadata);
  }

  if (contentLightMetaData)
  {
    kodi::addon::InputstreamContentlightMetadata contentlightMetadata;

    contentlightMetadata.SetMaxCll(contentLightMetaData->MaxCLL);
    contentlightMetadata.SetMaxFall(contentLightMetaData->MaxFALL);

    info.SetContentLightMetadata(contentlightMetadata);
  }

  return true;
}

std::string DemuxStreamAudioFFmpeg::GetStreamName()
{
  if (!m_stream)
    return "";
  if (!m_description.empty())
    return m_description;
  else
    return DemuxStream::GetStreamName();
}

bool DemuxStreamAudioFFmpeg::GetInformation(kodi::addon::InputstreamInfo& info)
{
  DemuxStream::GetInformation(info);

  if (m_tempoActive)
  {
    // Codec name must stay as pcm_f32le — Kodi uses it to select the audio
    // decoder pipeline, and our output IS raw PCM float. But report the SOURCE
    // bitrate and bits-per-sample so the OSD doesn't show huge PCM numbers.
    info.SetCodecName("pcm_f32le");
    info.SetExtraData(nullptr, 0);
    info.SetChannels(iChannels);
    info.SetSampleRate(iSampleRate);
    info.SetBitsPerSample(m_sourceBitsPerSample > 0 ? m_sourceBitsPerSample : 32);
    info.SetBlockAlign(iChannels * 4);
    info.SetBitRate(m_sourceBitRate > 0 ? m_sourceBitRate : iSampleRate * iChannels * 32);
  }
  else
  {
    info.SetChannels(iChannels);
    info.SetSampleRate(iSampleRate);
    info.SetBitRate(iBitRate);
    info.SetBitsPerSample(iBitsPerSample);
    info.SetBlockAlign(iBlockAlign);
  }

  return true;
}

std::string DemuxStreamSubtitleFFmpeg::GetStreamName()
{
  if (!m_stream)
    return "";
  if (!m_description.empty())
    return m_description;
  else
    return DemuxStream::GetStreamName();
}

bool DemuxStreamSubtitleFFmpeg::GetInformation(kodi::addon::InputstreamInfo& info)
{
  DemuxStream::GetInformation(info);

  return true;
}

std::string DemuxStreamVideoFFmpeg::GetStreamName()
{
  if (!m_stream)
    return "";
  if (!m_description.empty())
    return m_description;
  else
    return DemuxStream::GetStreamName();
}

DemuxParserFFmpeg::~DemuxParserFFmpeg()
{
  if (m_codecCtx)
    avcodec_free_context(&m_codecCtx);
  if (m_parserCtx)
  {
    av_parser_close(m_parserCtx);
    m_parserCtx = nullptr;
  }
}

FFmpegExtraData::FFmpegExtraData(size_t size)
  : m_data(reinterpret_cast<uint8_t*>(av_mallocz(size + AV_INPUT_BUFFER_PADDING_SIZE))),
    m_size(size)
{
  // using av_mallocz because some APIs require at least the padding to be zeroed, e.g. AVCodecParameters
  if (!m_data)
    throw std::bad_alloc();
}

FFmpegExtraData::FFmpegExtraData(const uint8_t* data, size_t size) : FFmpegExtraData(size)
{
  std::memcpy(m_data, data, size);
}

FFmpegExtraData::~FFmpegExtraData()
{
  av_free(m_data);
}

FFmpegExtraData::FFmpegExtraData(const FFmpegExtraData& e) : FFmpegExtraData(e.m_size)
{
  std::memcpy(m_data, e.m_data, m_size);
}

FFmpegExtraData::FFmpegExtraData(FFmpegExtraData&& other) noexcept : FFmpegExtraData()
{
  std::swap(m_data, other.m_data);
  std::swap(m_size, other.m_size);
}

FFmpegExtraData& FFmpegExtraData::operator=(const FFmpegExtraData& other)
{
  if (this != &other)
  {
    if (m_size >= other.m_size) // reuse current buffer if large enough
    {
      std::memcpy(m_data, other.m_data, other.m_size);
      m_size = other.m_size;
    }
    else
    {
      FFmpegExtraData extraData(other);
      *this = std::move(extraData);
    }
  }
  return *this;
}

FFmpegExtraData& FFmpegExtraData::operator=(FFmpegExtraData&& other) noexcept
{
  if (this != &other)
  {
    std::swap(m_data, other.m_data);
    std::swap(m_size, other.m_size);
  }
  return *this;
}

bool FFmpegExtraData::operator==(const FFmpegExtraData& other) const
{
  return m_size == other.m_size && std::memcmp(m_data, other.m_data, m_size) == 0;
}

bool FFmpegExtraData::operator!=(const FFmpegExtraData& other) const
{
  return !(*this == other);
}

uint8_t* FFmpegExtraData::TakeData()
{
  auto tmp = m_data;
  m_data = nullptr;
  m_size = 0;
  return tmp;
}
