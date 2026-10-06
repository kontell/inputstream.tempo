/*
 *  Copyright (C) 2026 Team Kodi (https://kodi.tv)
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later
 *  See LICENSE.md for more information.
 */

#pragma once

#include <cmath>
#include <map>

#include <kodi/c-api/addon-instance/inputstream/timing_constants.h>

namespace ffmpegdirect
{

// Keep each opened catch-up stream on the archive timeline. libavformat exposes
// timestamp resets in discontinuous formats; ffmpeg's CLI corrects them itself.
class CatchupTimestampNormalizer
{
public:
  void Reset()
  {
    m_streams.clear();
    m_correction = 0;
  }

  static bool HasTimestamp(double timestamp)
  {
    return timestamp != static_cast<double>(STREAM_NOPTS_VALUE) && std::isfinite(timestamp);
  }

  bool Normalize(int streamId, double& pts, double& dts, double duration, bool audioOrVideo)
  {
    double correction = m_correction;
    bool discontinuity = false;
    const double timestamp = HasTimestamp(dts) ? dts : pts;
    if (audioOrVideo && HasTimestamp(timestamp))
    {
      auto result = m_streams.emplace(streamId, StreamTiming{});
      StreamTiming& timing = result.first->second;
      if (result.second)
        timing.correction = m_correction;

      if (timing.initialized)
      {
        const double difference = timestamp - timing.correction - timing.nextTimestamp;
        // Match VideoPlayer's one-second discontinuity tolerance. Use DTS so
        // B-frame presentation order does not look like a timestamp reset.
        if (std::abs(difference) > STREAM_TIME_BASE)
        {
          const double candidate = timing.correction + difference;
          // Audio and video can cross the boundary on different reads. Keep
          // the old correction for a stream until it crosses too, then share
          // the correction so their original synchronization is preserved.
          if (std::abs(candidate - m_correction) > STREAM_TIME_BASE)
            m_correction = candidate;
          timing.correction = m_correction;
          discontinuity = true;
        }
      }

      correction = timing.correction;
      timing.nextTimestamp = timestamp - correction;
      if (HasTimestamp(duration) && duration > 0)
        timing.nextTimestamp += duration;
      timing.initialized = true;
    }

    if (HasTimestamp(pts))
      pts -= correction;
    if (HasTimestamp(dts))
      dts -= correction;
    return discontinuity;
  }

private:
  struct StreamTiming
  {
    double correction = 0;
    double nextTimestamp = 0;
    bool initialized = false;
  };

  std::map<int, StreamTiming> m_streams;
  double m_correction = 0;
};

} // namespace ffmpegdirect
