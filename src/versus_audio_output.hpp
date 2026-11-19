#pragma once

#include <SDL3/SDL.h>
#include <algorithm>
#include <array>
#include <cerrno>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <limits>
#include <memory>
#include <span>
#include <stdexcept>
#include <string>

namespace ss6 {

// The battle clock owns sample production. SDL converts the queued 48 kHz
// stream to the device's format without running simulation on its audio thread.
class VersusPlayback {
public:
    ~VersusPlayback() {
        stream_.reset();
        if(initialized_)SDL_QuitSubSystem(SDL_INIT_AUDIO);
    }
    void open() {
        SDL_AudioSpec spec{};
        spec.freq=48000;
        spec.format=SDL_AUDIO_S16;
        spec.channels=2;
        initialized_=SDL_InitSubSystem(SDL_INIT_AUDIO);
        if(initialized_)
            stream_.reset(SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK,&spec,nullptr,nullptr));
        if(!stream_){disable();return;}
        SDL_AudioSpec device{};
        int frames=0;
        if(SDL_GetAudioDeviceFormat(SDL_GetAudioStreamDevice(stream_.get()),&device,&frames) && device.freq>0) {
            // Keep at least a complete hardware pull for a device with a long period.
            const auto inputFrames=(int64_t(frames)*48000+device.freq-1)/device.freq;
            targetBytes_=std::max<int64_t>(targetBytes_,inputFrames*4);
        }
        if(!SDL_ResumeAudioStreamDevice(stream_.get()))disable();
    }
    void pause(bool value) {
        paused_=value;
        if(stream_ && !(paused_?SDL_PauseAudioStreamDevice(stream_.get()):SDL_ResumeAudioStreamDevice(stream_.get())))disable();
    }
    void clear() {if(stream_ && !SDL_ClearAudioStream(stream_.get()))disable();}
    void write(std::span<const int16_t,1600> pcm) {
        if(!stream_ || paused_)return;
        if(!makeRoom() || !SDL_PutAudioStreamData(stream_.get(),pcm.data(),tickBytes))disable();
    }
private:
    static constexpr int tickBytes=800*2*sizeof(int16_t);
    int64_t targetBytes_=3*tickBytes;

    bool makeRoom() {
        int queued=SDL_GetAudioStreamQueued(stream_.get());
        if(queued<0)return false;
        // In ordinary playback submit every sample at its original rate. Only
        // a late batch or a slow sink crosses the high watermark (normally 100 ms).
        if(queued+int64_t(tickBytes)<=targetBytes_+3*tickBytes)return true;
        SDL_AudioSpec out{};
        if(!SDL_GetAudioStreamFormat(stream_.get(),nullptr,&out))return false;
        // GetAudioStreamData consumes the OLDEST, converted frames. Keep a
        // reserve for the device and trim in small whole-frame chunks. Clearing
        // the stream here would also starve a device that is already playing.
        std::array<uint8_t,4096> discard;
        const int frameBytes=SDL_AUDIO_FRAMESIZE(out);
        if(frameBytes<=0 || frameBytes>int(discard.size()) || out.freq<=0)return false;
        const int frames=std::clamp(out.freq/240,1,int(discard.size())/frameBytes);
        while(queued>targetBytes_) {
            const int read=SDL_GetAudioStreamData(stream_.get(),discard.data(),frames*frameBytes);
            if(read<0)return false;
            queued=SDL_GetAudioStreamQueued(stream_.get());
            if(queued<0)return false;
            // A concurrent hardware pull can empty the stream before this read.
            if(read==0)return queued+int64_t(tickBytes)<=targetBytes_+3*tickBytes ||
                SDL_ClearAudioStream(stream_.get());
        }
        return true;
    }
    void disable() {
        SDL_Log("Versus audio unavailable: %s",SDL_GetError());
        stream_.reset();
    }
    std::unique_ptr<SDL_AudioStream,decltype(&SDL_DestroyAudioStream)> stream_{nullptr,SDL_DestroyAudioStream};
    bool paused_=false,initialized_=false;
};

// Publish only a complete RIFF file, even if the replay fails halfway through.
// Place the temporary recording beside its destination so rename is atomic.
class VersusWaveFile {
public:
    explicit VersusWaveFile(const std::filesystem::path& target):target_(target) {
        // The exclusive open prevents concurrent captures from sharing a
        // temporary file even if both see the same performance counter.
        for(unsigned tries=0;tries<16;++tries) {
            const auto name=target.string()+".part."+std::to_string(SDL_GetPerformanceCounter())+"."+std::to_string(tries);
            file_.reset(std::fopen(name.c_str(),"wbx"));
            if(file_){temporary_=name;break;}
            if(errno!=EEXIST)break;
        }
        if(!file_)throw std::runtime_error("Cannot create recording beside "+target.string());
        // Leave the first 44 bytes for a size-correct PCM header at commit.
        if(std::fseek(file_.get(),44,SEEK_SET)) {
            file_.reset();
            std::remove(temporary_.c_str());
            fail();
        }
    }
    ~VersusWaveFile() {
        file_.reset();
        if(!temporary_.empty())std::remove(temporary_.c_str());
    }
    void write(std::span<const int16_t> pcm) {
        const auto bytes=pcm.size_bytes();
        if(bytes>std::numeric_limits<uint32_t>::max()-36-size_)throw std::runtime_error("Versus recording exceeds RIFF size limit");
        if constexpr(std::endian::native==std::endian::little) {
            if(std::fwrite(pcm.data(),1,bytes,file_.get())!=bytes)fail();
        } else {
            for(auto value:pcm)putLE(static_cast<uint16_t>(value),2);
        }
        size_+=static_cast<uint32_t>(bytes);
    }
    void finish() {
        if(std::fseek(file_.get(),0,SEEK_SET))fail();
        putTag("RIFF");putLE(size_+36,4);putTag("WAVE");putTag("fmt ");
        putLE(16,4);putLE(1,2);putLE(2,2);putLE(48000,4);
        putLE(48000*4,4);putLE(4,2);putLE(16,2);putTag("data");putLE(size_,4);
        if(std::fclose(file_.release()))fail();
        std::error_code error;
        std::filesystem::rename(temporary_,target_,error);
        if(error)fail();
        temporary_.clear();
    }
private:
    [[noreturn]] void fail() const {throw std::runtime_error("Cannot write versus recording: "+target_.string());}
    void putTag(const char* tag) {if(std::fwrite(tag,1,4,file_.get())!=4)fail();}
    void putLE(uint32_t value,unsigned width) {
        for(unsigned i=0;i<width;++i)if(std::fputc(static_cast<unsigned char>(value>>(8*i)),file_.get())==EOF)fail();
    }
    std::filesystem::path target_;
    std::string temporary_;
    std::unique_ptr<FILE,decltype(&std::fclose)> file_{nullptr,std::fclose};
    uint32_t size_=0;
};
}
