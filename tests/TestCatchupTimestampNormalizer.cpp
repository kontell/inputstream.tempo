/*
 *  Copyright (C) 2026 Team Kodi (https://kodi.tv)
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later
 *  See LICENSE.md for more information.
 */

#include "../src/stream/CatchupTimestampNormalizer.h"
#include "../src/stream/TempoMap.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>

using ffmpegdirect::CatchupTimestampNormalizer;

static void Near(double actual, double expected)
{
  if (std::abs(actual - expected) > 0.001)
    throw std::runtime_error("Unexpected normalized timestamp");
}

static void Normalize(CatchupTimestampNormalizer& normalizer, int id,
                      double pts, double dts, double duration,
                      double expectedPts, double expectedDts)
{
  normalizer.Normalize(id, pts, dts, duration, true);
  Near(pts, expectedPts);
  Near(dts, expectedDts);
}

int main()
{
  CatchupTimestampNormalizer normalizer;
  const double jump = 64068994688.888916;
  // Preserve presentation/decode differences and original A/V alignment.
  Normalize(normalizer, 0, 60000, 0, 20000, 60000, 0);
  Normalize(normalizer, 1, 5000, 5000, 32000, 5000, 5000);
  Normalize(normalizer, 0, 40000, 20000, 20000, 40000, 20000);
  Normalize(normalizer, 0, jump + 100000, jump + 40000, 20000, 100000, 40000);
  // Audio can still deliver packets from before video's boundary.
  Normalize(normalizer, 1, 37000, 37000, 32000, 37000, 37000);
  Normalize(normalizer, 1, jump + 69000, jump + 69000, 32000, 69000, 69000);
  Normalize(normalizer, 0, jump + 120000, jump + 60000, 20000, 120000, 60000);
  // A backward reset must also remain on the same continuous timeline.
  Normalize(normalizer, 0, 70000, 10000, 20000, 140000, 80000);
  Normalize(normalizer, 1, 31000, 31000, 32000, 101000, 101000);

  // Missing timestamps remain missing; PTS alone can drive the timeline.
  const double noPts = static_cast<double>(STREAM_NOPTS_VALUE);
  normalizer.Reset();
  Normalize(normalizer, 0, 0, noPts, 20000, 0, noPts);
  Normalize(normalizer, 0, jump + 20000, noPts, 20000, 20000, noPts);
  Normalize(normalizer, 0, noPts, noPts, noPts, noPts, noPts);
  Normalize(normalizer, 0, noPts, jump + 40000, 20000, noPts, 40000);

  // Seeking/reopening forgets the previous response's correction entirely.
  normalizer.Reset();
  Normalize(normalizer, 0, 60000, 0, 20000, 60000, 0);
  Normalize(normalizer, 0, 80000, 20000, 20000, 80000, 20000);

  // Sparse non-A/V packets follow the common correction but cannot change it.
  Normalize(normalizer, 0, jump + 100000, jump + 40000, 20000, 100000, 40000);
  double pts = jump + 200000;
  double dts = noPts;
  normalizer.Normalize(2, pts, dts, 0, false);
  Near(pts, 200000);
  Near(dts, noPts);

  // Normalize in content time before the tempo map. At a non-unit rate,
  // correcting output packets by the source jump would overcorrect them.
  normalizer.Reset();
  ffmpegdirect::TempoMap map;
  map.Reset(0);
  map.Anchor(0, 1.5);
  pts = 60000;
  dts = 0;
  normalizer.Normalize(0, pts, dts, 20000, true);
  Near(map.ToOutput(pts), 40000);
  pts = jump + 80000;
  dts = jump + 20000;
  normalizer.Normalize(0, pts, dts, 20000, true);
  Near(map.ToOutput(pts), 80000 / 1.5);
  Near(map.ToOutput(dts), 20000 / 1.5);

  std::cout << "Catchup timestamp normalization tests passed\n";
  return EXIT_SUCCESS;
}
