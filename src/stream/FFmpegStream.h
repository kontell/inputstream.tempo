/*
 *  Copyright (C) 2005-2021 Team Kodi (https://kodi.tv)
 *
 *  SPDX-License-Identifier: GPL-2.0-or-later
 *  See LICENSE.md for more information.
 */

#pragma once

#include "../utils/HttpProxy.h"
#include "../utils/Properties.h"
#include "BaseStream.h"
#include "DemuxStream.h"
#include "CurlInput.h"
#include "TempoMap.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <sstream>

#include <kodi/addon-instance/Inputstream.h>
#include <kodi/tools/EndTime.h>

#ifndef __GNUC__
#pragma warning(push)
#pragma warning(disable : 4244)
#endif

extern "C"
{
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavfilter/avfilter.h>
#include <libavfilter/buffersink.h>
#include <libavfilter/buffersrc.h>
#include <libavutil/channel_layout.h>
#include <libavutil/mastering_display_metadata.h>
#include <libavutil/opt.h>
#include <libavutil/version.h>
}

#ifndef __GNUC__
#pragma warning(pop)
#endif

#define FFMPEG_DVDNAV_BUFFER_SIZE 2048  // for dvd's

struct StereoModeConversionMap;

namespace ffmpegdirect
{

enum class TRANSPORT_STREAM_STATE
{
  NONE,
  READY,
  NOTREADY,
};

class FFmpegStream
  : public BaseStream
{
public:
  FFmpegStream(IManageDemuxPacket* demuxPacketManager, const Properties& props, const HttpProxy& httpProxy);
  FFmpegStream(IManageDemuxPacket* demuxPacketManager, const Properties& props, std::shared_ptr<CurlInput> curlInput, const HttpProxy& httpProxy);
  ~FFmpegStream();

  virtual bool Open(const std::string& streamUrl, const std::string& mimeType, bool isRealTimeStream, const std::string& programProperty) override;
  virtual void Close() override;
  virtual void GetCapabilities(kodi::addon::InputstreamCapabilities& caps) override;
  virtual bool GetStreamIds(std::vector<unsigned int>& ids) override;
  virtual bool GetStream(int streamid, kodi::addon::InputstreamInfo& info) override;
  virtual void EnableStream(int streamid, bool enable) override;
  virtual bool OpenStream(int streamid) override;

  virtual void DemuxReset() override;
  virtual void DemuxAbort() override;
  virtual void DemuxFlush() override;
  virtual DEMUX_PACKET* DemuxRead() override;
  virtual bool DemuxSeekTime(double time, bool backwards, double& startpts) override;
  virtual void DemuxSetSpeed(int speed) override;
  virtual void SetVideoResolution(unsigned int width, unsigned int height) override;

  virtual int GetTotalTime() override;// { return 20; }
  virtual int GetTime() override;// { return m_displayTime; }
  virtual bool GetTimes(kodi::addon::InputstreamTimes& times) override;
  virtual bool PosTime(int ms) override;

  virtual int GetChapter() override;
  virtual int GetChapterCount() override;
  virtual const char* GetChapterName(int ch) override;
  virtual int64_t GetChapterPos(int ch) override;
  virtual bool SeekChapter(int ch) override;

  virtual int ReadStream(uint8_t* buffer, unsigned int bufferSize) override;
  virtual int64_t SeekStream(int64_t position, int whence = SEEK_SET) override;
  virtual int64_t PositionStream() override;
  virtual int64_t LengthStream() override;
  virtual bool IsRealTimeStream() override; // { return true; }

  void Dispose();
  void DisposeStreams();
  bool Aborted();

  AVFormatContext* m_pFormatContext;
  std::shared_ptr<CurlInput> m_curlInput;

protected:
  // What Kodi's player clock reads for the packet at the demux head, in
  // whichever frame this stream class reports time in — `player_ms` in the
  // state line. Here GetTimes() reports ptsStart = -Δ (and the realtime
  // IDisplayTime path stamps content dispTime), so the player clock runs in
  // content time; a catchup stream reports ptsStart = 0 against its shifted
  // output clock and overrides. A caller reads the source clock for its own
  // playing position as Player.getTime() + (source_ms − player_ms).
  virtual double HeadPlayerMs(double contentMs, double outputMs) const;
  // ── Tempo at read-out ──
  // A stream that fills a buffer from an input thread and serves Kodi from
  // it (TimeshiftStream) runs the tempo stage where Kodi reads, not where
  // the input thread demuxes: a rate change has to reach the packet Kodi is
  // about to play rather than one it will consume when the buffer has
  // drained, and the tempo file has to be polled at Kodi's read cadence, not
  // at the source's segment cadence (measured on a live HLS: a pulse never
  // confirmed). Such a class sets the flag; ReadNew() then stores raw
  // content-domain packets and ApplyTempoOnRead() does on the way out what
  // ReadNew() would have done on the way in.
  bool m_tempoAtReadout = false;
  bool TempoOnInput() const { return m_tempoEnabled && !m_tempoAtReadout; }
  bool TempoEnabled() const { return m_tempoEnabled; }
  bool HasTempoOutput() const { return !m_tempoOutputQueue.empty(); }
  double CurrentDeltaMs() const;
  DEMUX_PACKET* PopTempoOutput();
  void PollTempoFile();
  void FlushTempoForSeek();
  double ReportedDeltaForTimes();
  DEMUX_PACKET* ApplyTempoOnRead(DEMUX_PACKET* raw);
  int64_t ToStreamTimestamp(double dvdTime, int den, int num) const;
  virtual std::string GetStreamCodecName(int iStreamId);
  virtual void CurrentPTSUpdated();
  bool IsPaused() { return m_speed == STREAM_PLAYSPEED_PAUSE; }
  virtual bool CheckReturnEmptyOnPacketResult(int result);

  FFmpegExtraData GetPacketExtradata(const AVPacket* pkt, const AVCodecParameters* codecPar);

  int64_t m_demuxerId;
  mutable std::recursive_mutex m_mutex;
  double m_currentPts; // used for stream length estimation
  bool m_demuxResetOpenSuccess = false;
  std::string m_streamUrl;
  int m_lastPacketResult;
  bool m_isRealTimeStream;

private:
  bool Open(bool fileinfo);
  bool OpenWithFFmpeg(const AVInputFormat* iformat, const AVIOInterruptCB& int_cb);
  bool OpenWithCURL(const AVInputFormat* iformat);
  AVDictionary* GetFFMpegOptionsFromInput();
  void ResetVideoStreams();
  double ConvertTimestamp(int64_t pts, int den, int num);
  unsigned int HLSSelectProgram();
  int GetNrOfStreams() const;
  int GetNrOfStreams(INPUTSTREAM_TYPE streamType);
  int GetNrOfSubtitleStreams();
  std::vector<DemuxStream*> GetDemuxStreams() const;
  DemuxStream* GetDemuxStream(int iStreamId) const;
  void CreateStreams(unsigned int program);
  void AddStream(int streamIdx, DemuxStream* stream);
  DemuxStream* AddStream(int streamIdx);
  void GetL16Parameters(int& channels, int& samplerate);
  double SelectAspect(AVStream* st, bool& forced);
  StreamHdrType DetermineHdrType(AVStream* pStream);
  std::string GetStereoModeFromMetadata(AVDictionary* pMetadata);
  std::string ConvertCodecToInternalStereoMode(const std::string &mode, const StereoModeConversionMap* conversionMap);
  bool SeekTime(double time, bool backwards = false, double* startpts = nullptr);
  void ParsePacket(AVPacket* pkt);
  TRANSPORT_STREAM_STATE TransportStreamAudioState();
  TRANSPORT_STREAM_STATE TransportStreamVideoState();
  bool IsTransportStreamReady();
  bool IsProgramChange();
  void StoreSideData(DEMUX_PACKET *pkt, AVPacket *src);

  bool StreamsOpened() { return m_streams.size() > 0; }

  int64_t NewGuid()
  {
    static int64_t guid = 0;
    return guid++;
  }

  bool m_paused;

  std::map<int, DemuxStream*> m_streams;
  std::map<int, std::unique_ptr<DemuxParserFFmpeg>> m_parsers;

  AVIOContext* m_ioContext;

  bool     m_bMatroska;
  bool     m_bAVI;
  bool     m_bSup;
  int      m_speed;
  unsigned int m_program;
  unsigned int m_streamsInProgram;
  unsigned int m_newProgram;
  unsigned int m_initialProgramNumber;
  int m_seekStream;

  kodi::tools::CEndTime  m_timeout;

  // Due to limitations of ffmpeg, we only can detect a program change
  // with a packet. This struct saves the packet for the next read and
  // signals STREAMCHANGE to player
  struct
  {
    AVPacket pkt;       // packet ffmpeg returned
    int      result;    // result from av_read_packet
  }m_pkt;

  bool m_streaminfo;
  bool m_reopen = false;
  bool m_checkTransportStream;
  int m_displayTime = 0;
  double m_dtsAtDisplayTime;
  bool m_seekToKeyFrame = false;
  double m_startTime = 0;

  std::string m_mimeType;
  std::string m_programProperty;
  std::string m_manifestType;
  bool m_opened;

  HttpProxy m_httpProxy;
  OpenMode m_openMode;
  StreamMode m_streamMode;

  // ── Tempo processing ──
  bool m_tempoEnabled = false;
  double m_currentTempo = 1.0;
  std::string m_tempoFilePath;
  double m_initialSeekTimeSecs = 0.0;
  int m_tempoAudioStreamIndex = -1;

  // Kodi's demux queue depth and the optional add-on-side lead bound, from
  // the queue_secs / lead_secs properties (Properties.h explains both).
  double m_queueSecs = 8.0;
  double m_leadSecs = 0.0;
  // A real video stream exists, so VideoPlayer semantics apply: IPOSTIME is
  // advertised, time is reported at the playing point, and the wall-clock
  // throttle must not block the player loop.
  bool m_hasVideo = false;

  AVCodecContext* m_audioDecoderCtx = nullptr;
  AVFilterGraph* m_filterGraph = nullptr;
  AVFilterContext* m_bufferSrcCtx = nullptr;
  AVFilterContext* m_bufferSinkCtx = nullptr;
  AVFrame* m_decodedFrame = nullptr;
  AVFrame* m_filteredFrame = nullptr;

  std::queue<DEMUX_PACKET*> m_tempoOutputQueue;
  // Packets SeekTime's pts probe has already read after a seek, each with the
  // content pts it set m_currentPts to (the flush Kodi issues right after
  // PosTime clears that, and the drain restores it). They are the first
  // packets of the new position — the keyframe among them — and DemuxRead
  // delivers them before reading anything new, exactly as Kodi's own demuxer
  // keeps its probe packet (ReadInternal(keep=true)). Freeing them, as
  // upstream ffmpegdirect does, starts every decoder mid-GOP after a seek:
  // [hevc] "Could not find ref with POC" on software decode, concealed by most
  // hardware decoders, a wedged AV1 decoder on a Pixel 7. The probe itself
  // reads through ReadNew(), which never consults this queue: probing through
  // DemuxRead would hand it its own first packet back. Survives DemuxFlush.
  std::queue<std::pair<DEMUX_PACKET*, double>> m_pendingPackets;
  // Output PTS (wall-clock rate) — used for packet.pts/dts so ActiveAE
  // schedules audio correctly. Advances by outputDuration per packet.
  double m_tempoOutputPts = 0.0;
  // Content PTS (content rate) — used for dispTime and m_currentPts so OSD
  // progress and GetTime() reflect content position. Advances by contentDuration
  // per packet (= outputDuration × tempo).
  double m_tempoContentPts = 0.0;
  int m_tempoEmittedPackets = 0;
  // Wall-clock throttling state. Without this the tempo pipeline races
  // through the source file as fast as ffmpeg can decode, producing
  // hundreds of seconds of output audio per wall-second, which starves
  // Kodi's audio sink of the initial fill it needs to transition out of
  // SYNC_STARTING. We cap emission at a fixed lead over wall-clock.
  std::chrono::steady_clock::time_point m_tempoFirstEmitWall{};
  double m_tempoCumulativeOutputSecs = 0.0;

  // Initial seek hold. When the caller sets inputstream.tempo.start_time,
  // PAPlayer is about to issue a resume seek to that position — but the
  // sink may Resume() before the seek arrives and play pre-roll at pts=0
  // (the "fraction of a second from the start of the book" leak). While
  // the hold is active, DemuxRead returns empty packets so nothing reaches
  // the sink until SeekTime clears the hold, or kInitialSeekHoldTimeout
  // elapses as a safety fallback.
  bool m_initialSeekHoldActive = false;
  std::chrono::steady_clock::time_point m_initialSeekHoldStart{};
  static constexpr std::chrono::milliseconds kInitialSeekHoldTimeout{2000};
  bool CheckAndUpdateInitialSeekHold();

  // One content↔output map for every stream (TempoMap.h). The audio path
  // walks it with the two counters above; video and subtitle packets are
  // projected through it in ProjectPacket(); GetTimes() reads Δ off it.
  TempoMap m_tempoMap;
  // The audio counters must be (re)initialised from the map at the next
  // decoded frame: set at open, after every seek/flush, and on re-target.
  bool m_tempoAnchorPending = true;
  // Highest output-domain dts handed to Kodi since the last anchor — the
  // demux head. Time is reported QueueSecsForReadout() behind it, because
  // that is where the packet Kodi is actually playing sits.
  double m_headOutputPts = STREAM_NOPTS_VALUE;
  // Δ = content − output as last reported through GetTimes(): the value a
  // seek must continue from so Kodi's own startpts arithmetic stays right.
  double m_deltaReported = 0.0;
  bool m_deltaReportedValid = false;
  std::chrono::steady_clock::time_point m_lastTempoPoll{};
  static constexpr std::chrono::milliseconds kTempoPollInterval{250};
  uint64_t m_tempoStateSeq = 0;

  bool HasVideoStream() const;
  double QueueSecsForReadout() const;
  double CurrentDelta() const;
  // The start ConvertTimestamp() subtracts: the container's own timestamps
  // begin here. Added back to the head's content position it gives
  // `source_ms` in the state line — the source's clock (an MPEG-TS PTS on
  // a broadcast), which every member of a SyncPlay group playing one live
  // feed shares whatever their own stream's start was. ffmpeg unwraps the
  // 33-bit PTS within a session, so the value can pass 2^33/90kHz; the
  // caller compares modulo that period.
  double SourceStartSecs() const;
  void ResetTempoMapForSeek();
  void NoteOutputHead(double outputDts);
  void ProjectPacket(DEMUX_PACKET* pkt, int streamIdx);
  DEMUX_PACKET* ReadNew();
  void FreePendingPackets();
  bool RetargetTempoAudio(int streamIdx);
  void WriteTempoState(const char* event);
  static double ParseTempo(const char* text);

  bool InitTempoProcessing(AVStream* audioStream);
  void DestroyTempoProcessing();
  bool BuildFilterGraph(double tempo);
  void CheckTempoFileUpdate();
  void ApplyQueueSecsDirective(const char* text);
  void ProcessAudioPacketWithTempo(AVPacket* pkt, AVStream* stream);
};

} //namespace ffmpegdirect
