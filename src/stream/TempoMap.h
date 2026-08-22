/*
 *  Copyright (C) 2005-2021 Team Kodi (https://kodi.tv)
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later
 *  See LICENSE.md for more information.
 */

#pragma once

#include <vector>

namespace ffmpegdirect
{

/*!
 * Piecewise-linear map between the two time domains a tempo-shifting
 * demuxer has to keep consistent:
 *
 *   content time — where the media really is (what the OSD shows)
 *   output time  — what ActiveAE and the renderer see on packet pts/dts
 *
 * Within one segment, output advances by 1/rate per unit of content. A new
 * segment starts at every tempo change. Every stream — the stretched audio,
 * the untouched video and subtitle packets — is projected through the same
 * map so they stay locked to one another at any rate.
 *
 * Δ = content − output is the quantity Kodi consumes (as `time_offset`,
 * via ITimes::ptsStart). It must change only while the rate is not 1:
 * never at a seek, never at a flush. Reset() therefore remembers the Δ to
 * continue from, and Anchor() starts the new map at output = content − Δ.
 *
 * All times are in the caller's units (STREAM_TIME_BASE microseconds in
 * the add-on); the class is unit-agnostic.
 */
class TempoMap
{
public:
  struct Segment
  {
    double content; // content time where the segment starts
    double output; // output time where the segment starts
    double rate; // content advanced per unit of output
  };

  /*! Forget every segment; the next Anchor() continues from deltaKeep. */
  void Reset(double deltaKeep)
  {
    m_segments.clear();
    m_deltaKeep = deltaKeep;
  }

  bool HasAnchor() const { return !m_segments.empty(); }
  double DeltaKeep() const { return m_deltaKeep; }
  const std::vector<Segment>& Segments() const { return m_segments; }

  /*! Start the map at a content time, keeping Δ continuous with the
   *  previous map (or with deltaKeep after Reset()). */
  void Anchor(double content, double rate)
  {
    m_segments.clear();
    m_segments.push_back({content, content - m_deltaKeep, SafeRate(rate)});
  }

  /*! Begin a new segment with a new rate at the given point. The point
   *  normally comes from the audio counters, which are the source of truth
   *  for where the rate change lands in both domains. */
  void ChangeRate(double content, double output, double rate)
  {
    if (m_segments.empty())
    {
      m_deltaKeep = content - output;
      Anchor(content, rate);
      return;
    }
    Segment& last = m_segments.back();
    if (content < last.content)
    {
      if (m_segments.size() == 1)
      {
        // The anchor came from a packet ahead of the audio (video usually
        // arrives first after a seek). Re-base the anchor on the audio point.
        last = {content, output, SafeRate(rate)};
        return;
      }
      // Counters are monotone; never let a segment start behind its predecessor.
      content = last.content;
      output = last.output;
    }
    m_segments.push_back({content, output, SafeRate(rate)});
  }

  /*! Rate in force at a content time (1.0 before any anchor). */
  double RateAt(double content) const
  {
    const Segment* s = Find(content);
    return s ? s->rate : 1.0;
  }

  /*! M(content): the output time a content time maps to. Extrapolates with
   *  the first segment's rate before the anchor so B-frame dts ahead of the
   *  anchor stay monotone. */
  double ToOutput(double content) const
  {
    if (m_segments.empty())
      return content - m_deltaKeep;
    const Segment& s = *Find(content);
    return s.output + (content - s.content) / s.rate;
  }

  /*! M⁻¹(output). */
  double ToContent(double output) const
  {
    if (m_segments.empty())
      return output + m_deltaKeep;
    const Segment& s = *FindByOutput(output);
    return s.content + (output - s.output) * s.rate;
  }

  /*! Δ = content − output at an output time. Clamped to the anchor rather
   *  than extrapolated: before the anchor the map is Δ_keep by definition. */
  double DeltaAtOutput(double output) const
  {
    if (m_segments.empty())
      return m_deltaKeep;
    if (output < m_segments.front().output)
      output = m_segments.front().output;
    return ToContent(output) - output;
  }

  /*! Drop segments that ended before the given output time, keeping the one
   *  that covers it so DeltaAtOutput() stays exact for everything newer. */
  void Prune(double olderThanOutput)
  {
    while (m_segments.size() > 1 && m_segments[1].output <= olderThanOutput)
      m_segments.erase(m_segments.begin());
  }

private:
  static double SafeRate(double rate) { return rate > 0.0 ? rate : 1.0; }

  const Segment* Find(double content) const
  {
    if (m_segments.empty())
      return nullptr;
    const Segment* best = &m_segments.front();
    for (const Segment& s : m_segments)
    {
      if (s.content <= content)
        best = &s;
      else
        break;
    }
    return best;
  }

  const Segment* FindByOutput(double output) const
  {
    const Segment* best = &m_segments.front();
    for (const Segment& s : m_segments)
    {
      if (s.output <= output)
        best = &s;
      else
        break;
    }
    return best;
  }

  std::vector<Segment> m_segments;
  double m_deltaKeep = 0.0;
};

} // namespace ffmpegdirect
