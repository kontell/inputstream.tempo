// Standalone test for TempoMap. No Kodi or FFmpeg dependency:
//
//   g++ -std=c++17 -I src/stream tests/tempomap_test.cpp -o /tmp/tempomap_test && /tmp/tempomap_test
//
// Times are plain seconds here; the class is unit-agnostic.

#include "TempoMap.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using ffmpegdirect::TempoMap;

static int g_failures = 0;

static void Expect(const char* what, double got, double want, double tol = 1e-9)
{
  if (std::fabs(got - want) > tol)
  {
    std::printf("FAIL %s: got %.9f want %.9f\n", what, got, want);
    ++g_failures;
  }
}

int main()
{
  {
    // Identity: rate 1, no Δ.
    TempoMap m;
    m.Anchor(10.0, 1.0);
    Expect("identity ToOutput", m.ToOutput(12.0), 12.0);
    Expect("identity ToContent", m.ToContent(12.0), 12.0);
    Expect("identity Delta", m.DeltaAtOutput(12.0), 0.0);
    Expect("identity rate", m.RateAt(12.0), 1.0);
  }
  {
    // 1.5x from the anchor: content runs 1.5 per output second.
    TempoMap m;
    m.Anchor(10.0, 1.5);
    Expect("1.5x ToOutput", m.ToOutput(13.0), 12.0);
    Expect("1.5x ToContent", m.ToContent(12.0), 13.0);
    Expect("1.5x Delta", m.DeltaAtOutput(12.0), 1.0);
    // Before the anchor: extrapolate (B-frame dts ahead of the anchor).
    Expect("1.5x extrapolate back", m.ToOutput(7.0), 8.0);
    // Δ is clamped before the anchor, not extrapolated.
    Expect("1.5x Delta clamped", m.DeltaAtOutput(0.0), 0.0);
  }
  {
    // A nudge: 1.03 for 10 output seconds, then back to 1.0. Δ ends at +0.3
    // and stays there — that is the position correction the nudge bought.
    TempoMap m;
    m.Anchor(0.0, 1.0);
    m.ChangeRate(10.0, 10.0, 1.03);
    Expect("nudge rate", m.RateAt(15.0), 1.03);
    Expect("nudge ToOutput end", m.ToOutput(20.3), 20.0);
    Expect("nudge Delta end", m.DeltaAtOutput(20.0), 0.3);
    m.ChangeRate(20.3, 20.0, 1.0);
    Expect("after nudge ToOutput", m.ToOutput(30.3), 30.0);
    Expect("after nudge Delta", m.DeltaAtOutput(30.0), 0.3);
    Expect("after nudge ToContent", m.ToContent(30.0), 30.3);
    // Mid-segment lookups pick the right segment.
    Expect("mid first", m.ToOutput(5.0), 5.0);
    Expect("mid second", m.ToOutput(15.15), 15.0);
    Expect("mid second delta", m.DeltaAtOutput(15.0), 0.15);
  }
  {
    // Continuity across a seek: Δ must survive Reset()+Anchor().
    TempoMap m;
    m.Anchor(0.0, 1.0);
    m.ChangeRate(10.0, 10.0, 1.03);
    m.ChangeRate(20.3, 20.0, 1.0);
    const double keep = m.DeltaAtOutput(25.0);
    Expect("keep", keep, 0.3);
    m.Reset(keep);
    Expect("empty map ToOutput", m.ToOutput(100.0), 99.7);
    Expect("empty map Delta", m.DeltaAtOutput(50.0), 0.3);
    m.Anchor(100.0, 1.0);
    Expect("re-anchored ToOutput", m.ToOutput(100.0), 99.7);
    Expect("re-anchored Delta", m.DeltaAtOutput(99.7), 0.3);
    Expect("re-anchored later", m.ToOutput(160.0), 159.7);
  }
  {
    // The anchor came from a video packet ahead of the audio; the first rate
    // change from the audio counters re-bases it rather than going backwards.
    TempoMap m;
    m.Reset(0.0);
    m.Anchor(12.0, 1.0);
    m.ChangeRate(11.5, 11.5, 1.02);
    Expect("rebased anchor content", m.Segments().front().content, 11.5);
    Expect("rebased rate", m.RateAt(13.0), 1.02);
    // A later out-of-order call is clamped, never reordered.
    m.ChangeRate(20.0, m.ToOutput(20.0), 1.0);
    m.ChangeRate(19.0, 18.0, 1.05);
    Expect("clamped content", m.Segments().back().content, 20.0);
    Expect("segments", static_cast<double>(m.Segments().size()), 3.0);
  }
  {
    // Prune keeps the segment that covers the cut-off point.
    TempoMap m;
    m.Anchor(0.0, 1.0);
    m.ChangeRate(10.0, 10.0, 1.03);
    m.ChangeRate(20.3, 20.0, 1.0);
    m.ChangeRate(40.3, 40.0, 0.98);
    m.Prune(25.0);
    Expect("pruned count", static_cast<double>(m.Segments().size()), 2.0);
    Expect("pruned delta", m.DeltaAtOutput(30.0), 0.3);
    Expect("pruned later", m.DeltaAtOutput(50.0), 0.3 - 0.2);
  }
  {
    // ChangeRate on an empty map anchors with the implied Δ.
    TempoMap m;
    m.ChangeRate(50.0, 49.0, 1.1);
    Expect("implied keep", m.DeltaKeep(), 1.0);
    Expect("implied ToOutput", m.ToOutput(50.0), 49.0);
    Expect("implied rate", m.RateAt(60.0), 1.1);
  }

  if (g_failures)
  {
    std::printf("%d failure(s)\n", g_failures);
    return EXIT_FAILURE;
  }
  std::printf("tempomap: all checks passed\n");
  return EXIT_SUCCESS;
}
