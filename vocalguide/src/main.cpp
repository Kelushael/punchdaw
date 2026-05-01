#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"
#include "json.hpp"

#include <SDL2/SDL.h>
#include <SDL2/SDL_ttf.h>
#include <GL/gl.h>
#include <GL/glext.h>

#include <vector>
#include <string>
#include <deque>
#include <cmath>
#include <fstream>
#include <iostream>
#include <algorithm>
#include <cstring>

using json = nlohmann::json;

// =============================================================================
// GUIDE DATA
// =============================================================================
struct PitchPoint { float time=0, freq=0, midi=0, confidence=0; };
struct EnergyPoint { float time=0, rms=0; };
struct Bar { int index=0; float start=0, end=0; std::vector<float> beats; };
struct Section { std::string name; int startBar=0, endBar=0; float start=0, end=0; };
struct LyricWord {
    std::string text;
    float start=0, end=0;
    int beatIndex=0, barIndex=0, beatInBar=0;
};

struct Guide {
    float bpm=120.0f, duration=0.0f, beatPeriod=0.5f, beatsPerSecond=2.0f;
    int beatsPerBar=4;
    std::vector<float> beats;
    std::vector<Bar> bars;
    std::vector<Section> sections;
    std::vector<PitchPoint> pitch;
    std::vector<EnergyPoint> energy;
    std::vector<LyricWord> lyrics;
};

Guide loadGuide(const std::string& path) {
    Guide g;
    std::ifstream f(path);
    if (!f) { std::cerr << "Cannot open " << path << "\n"; return g; }
    json j; f >> j;
    g.bpm = j.value("bpm", 120.0f);
    g.duration = j.value("duration_seconds", 0.0f);
    g.beatPeriod = j.value("beat_period", 60.0f / g.bpm);
    g.beatsPerSecond = j.value("beats_per_second", g.bpm / 60.0f);
    g.beatsPerBar = j.value("beats_per_bar", 4);
    if (j.contains("beats")) for (auto& b : j["beats"]) g.beats.push_back(b);
    if (j.contains("bars")) {
        for (auto& b : j["bars"]) {
            Bar bar; bar.index = b.value("index", 0);
            bar.start = b.value("start_time", 0.0f); bar.end = b.value("end_time", 0.0f);
            if (b.contains("beat_times")) for (auto& bt : b["beat_times"]) bar.beats.push_back(bt);
            g.bars.push_back(bar);
        }
    }
    if (j.contains("sections")) {
        for (auto& s : j["sections"]) {
            Section sec; sec.name = s.value("name", "Section");
            sec.startBar = s.value("start_bar", 0); sec.endBar = s.value("end_bar", 0);
            sec.start = s.value("start_time", 0.0f); sec.end = s.value("end_time", 0.0f);
            g.sections.push_back(sec);
        }
    }
    if (j.contains("pitch_contour")) {
        for (auto& p : j["pitch_contour"]) {
            PitchPoint pp;
            pp.time = p.value("time", 0.0f); pp.freq = p.value("frequency", 0.0f);
            pp.midi = p.value("midi", 0.0f); pp.confidence = p.value("confidence", 0.0f);
            g.pitch.push_back(pp);
        }
    }
    if (j.contains("energy")) {
        for (auto& e : j["energy"]) {
            EnergyPoint ep; ep.time = e.value("time", 0.0f); ep.rms = e.value("rms", 0.0f);
            g.energy.push_back(ep);
        }
    }
    if (j.contains("lyrics")) {
        for (auto& w : j["lyrics"]) {
            LyricWord lw;
            lw.text = w.value("text", "");
            lw.start = w.value("start_time", 0.0f);
            lw.end = w.value("end_time", 0.0f);
            lw.beatIndex = w.value("beat_index", 0);
            lw.barIndex = w.value("bar_index", 0);
            lw.beatInBar = w.value("beat_within_bar", 0);
            g.lyrics.push_back(lw);
        }
    }
    std::cout << "Guide: " << g.bpm << " BPM, " << g.bars.size() << " bars, "
              << g.sections.size() << " sections, " << g.lyrics.size() << " words\n";
    return g;
}

// =============================================================================
// AUDIO (miniaudio)
// =============================================================================
struct AppAudio {
    ma_engine engine;
    ma_sound sound;
    ma_device captureDev;
    std::deque<float> micRing;
    size_t micRingSize = 0;
    SDL_mutex* micMutex = nullptr;
    bool hasSound = false;
    bool running = true;
};

static AppAudio* gAudio = nullptr;

void captureCallback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount) {
    (void)pOutput;
    AppAudio* a = (AppAudio*)pDevice->pUserData;
    if (!a || !a->running) return;
    const float* input = (const float*)pInput;
    SDL_LockMutex(a->micMutex);
    for (ma_uint32 i = 0; i < frameCount; ++i) {
        a->micRing.push_back(input[i]);
        if (a->micRing.size() > a->micRingSize) a->micRing.pop_front();
    }
    SDL_UnlockMutex(a->micMutex);
}

bool initAudio(AppAudio* a, const char* mp3Path) {
    a->micMutex = SDL_CreateMutex();
    a->micRingSize = 44100 * 3;
    if (ma_engine_init(nullptr, &a->engine) != MA_SUCCESS) return false;
    if (ma_sound_init_from_file(&a->engine, mp3Path, MA_SOUND_FLAG_STREAM, nullptr, nullptr, &a->sound) != MA_SUCCESS) {
        ma_engine_uninit(&a->engine); return false;
    }
    a->hasSound = true;
    ma_device_config dcfg = ma_device_config_init(ma_device_type_capture);
    dcfg.capture.format = ma_format_f32; dcfg.capture.channels = 1;
    dcfg.sampleRate = 44100; dcfg.dataCallback = captureCallback; dcfg.pUserData = a;
    if (ma_device_init(nullptr, &dcfg, &a->captureDev) != MA_SUCCESS) return false;
    ma_device_start(&a->captureDev);
    return true;
}

void shutdownAudio(AppAudio* a) {
    a->running = false;
    if (a->hasSound) { ma_sound_uninit(&a->sound); a->hasSound = false; }
    ma_engine_uninit(&a->engine);
    ma_device_stop(&a->captureDev); ma_device_uninit(&a->captureDev);
    if (a->micMutex) { SDL_DestroyMutex(a->micMutex); a->micMutex = nullptr; }
}

double playbackTime(AppAudio* a) {
    if (!a || !a->hasSound) return 0.0;
    ma_uint64 cursor; ma_sound_get_cursor_in_pcm_frames(&a->sound, &cursor);
    return (double)cursor / 44100.0;
}

// =============================================================================
// YIN PITCH DETECTOR
// =============================================================================
class YIN {
    std::vector<float> buf, diff;
    int sr; float threshold;
public:
    YIN(int sampleRate=44100, float thresh=0.15f) : sr(sampleRate), threshold(thresh) {}
    float detect(const float* samples, int n) {
        if (n < 256) return 0.0f;
        int half = n / 2;
        buf.resize(n); diff.resize(half);
        for (int i = 0; i < n; ++i) buf[i] = samples[i];
        for (int tau = 0; tau < half; ++tau) {
            float d = 0.0f;
            for (int i = 0; i < half; ++i) { float delta = buf[i] - buf[i + tau]; d += delta * delta; }
            diff[tau] = d;
        }
        diff[0] = 1.0f;
        float runningSum = 0.0f;
        for (int tau = 1; tau < half; ++tau) { runningSum += diff[tau]; diff[tau] = diff[tau] * tau / runningSum; }
        int tau = 2;
        for (; tau < half; ++tau) {
            if (diff[tau] < threshold) { while (tau + 1 < half && diff[tau + 1] < diff[tau]) ++tau; break; }
        }
        if (tau >= half || diff[tau] >= threshold) return 0.0f;
        float y0 = (tau > 0) ? diff[tau - 1] : diff[tau];
        float y1 = diff[tau];
        float y2 = (tau + 1 < half) ? diff[tau + 1] : diff[tau];
        float shift = (y2 - y0) / (2.0f * (2.0f * y1 - y0 - y2));
        float period = (float)tau + shift;
        return (period < 1.0f) ? 0.0f : (float)sr / period;
    }
};

// =============================================================================
// LPC FORMANT ANALYZER
// =============================================================================
class FormantAnalyzer {
    int order; std::vector<float> a, r;
public:
    FormantAnalyzer(int lpcOrder=10) : order(lpcOrder) { a.resize(order + 1); r.resize(order + 1); }
    void analyze(const float* samples, int n, float sr, float* f1, float* f2, float* f3) {
        std::vector<float> x(n);
        x[0] = samples[0];
        for (int i = 1; i < n; ++i) x[i] = samples[i] - 0.97f * samples[i - 1];
        for (int i = 0; i < n; ++i) { float w = 0.5f - 0.5f * cosf(6.2831853f * i / (n - 1)); x[i] *= w; }
        for (int k = 0; k <= order; ++k) {
            double sum = 0.0;
            for (int i = 0; i < n - k; ++i) sum += x[i] * x[i + k];
            r[k] = (float)sum;
        }
        if (r[0] < 1e-10f) { *f1 = *f2 = *f3 = 0; return; }
        a[0] = 1.0f; float E = r[0];
        for (int i = 1; i <= order; ++i) {
            double sum = 0.0;
            for (int j = 1; j < i; ++j) sum += a[j] * r[i - j];
            float k = (r[i] - (float)sum) / E;
            a[i] = k;
            for (int j = 1; j < i; ++j) {
                float tmp = a[j];
                a[j] = tmp - k * a[i - j];
                a[i - j] -= k * tmp;
            }
            E *= (1.0f - k * k);
        }
        int fftSize = 512; float binHz = sr / fftSize;
        std::vector<float> spec(fftSize / 2 + 1);
        for (int k = 0; k <= fftSize / 2; ++k) {
            float omega = 6.2831853f * k / fftSize;
            float real = 1.0f, imag = 0.0f;
            for (int j = 1; j <= order; ++j) {
                real += a[j] * cosf(omega * j);
                imag -= a[j] * sinf(omega * j);
            }
            spec[k] = 1.0f / (real * real + imag * imag + 1e-10f);
        }
        int peaks[3] = {0,0,0}; float peakVals[3] = {0,0,0};
        for (int k = 2; k < fftSize / 2; ++k) {
            float hz = k * binHz;
            if (hz < 150 || hz > 4000) continue;
            if (spec[k] > spec[k-1] && spec[k] > spec[k+1]) {
                if (spec[k] > peakVals[0]) { peakVals[2]=peakVals[1]; peaks[2]=peaks[1]; peakVals[1]=peakVals[0]; peaks[1]=peaks[0]; peakVals[0]=spec[k]; peaks[0]=k; }
                else if (spec[k] > peakVals[1]) { peakVals[2]=peakVals[1]; peaks[2]=peaks[1]; peakVals[1]=spec[k]; peaks[1]=k; }
                else if (spec[k] > peakVals[2]) { peakVals[2]=spec[k]; peaks[2]=k; }
            }
        }
        std::sort(peaks, peaks + 3);
        *f1 = peaks[0] * binHz; *f2 = peaks[1] * binHz; *f3 = peaks[2] * binHz;
    }
};

// =============================================================================
// OPENGL HELPERS
// =============================================================================
static const char* vertSrc = R"(#version 330 core
layout(location=0) in vec2 aPos;
void main(){gl_Position=vec4(aPos,0.0,1.0);}
)";

// CYMATIC / CHLADNI PLATE STANDING WAVE SHADER
static const char* cymaticFrag = R"(#version 330 core
uniform float u_time;
uniform vec2 u_res;
uniform float u_energy;
uniform float u_pitch;
uniform float u_consistency;
out vec4 fc;

float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
float a=hash(i),b=hash(i+vec2(1,0)),c=hash(i+vec2(0,1)),d=hash(i+vec2(1,1));
return mix(mix(a,b,f.x),mix(c,d,f.x),f.y);}

void main(){
vec2 uv=gl_FragCoord.xy/u_res;
float t=u_time*0.4;
float e=u_energy*3.0;
float p=(u_pitch>0.0)?(u_pitch/440.0):1.0;
float c=u_consistency;

// Chladni-like standing wave patterns
float m1=3.0+e*2.0; float m2=2.0+e;
float wave1=sin(m1*3.14159*uv.x)*sin(m2*3.14159*uv.y);
float wave2=cos(m2*3.14159*uv.x)*sin(m1*3.14159*uv.y);
float wave3=sin((m1+m2)*3.14159*(uv.x+uv.y)*0.5);

// Time animation
wave1+=0.3*sin(uv.x*10.0*p+t)*cos(uv.y*8.0*p-t*0.7);
wave2+=0.3*cos(uv.x*7.0*p-t*0.5)*sin(uv.y*9.0*p+t);

float v=abs(wave1)*0.4+abs(wave2)*0.35+abs(wave3)*0.25;
v+=e*noise(uv*6.0+t);
v=smoothstep(0.1,0.9,v);

// Color palette: deep space -> violet -> magenta -> gold -> white
vec3 deep=vec3(0.02,0.0,0.08);
vec3 violet=vec3(0.3,0.0,0.5);
vec3 magenta=vec3(0.8,0.0,0.4);
vec3 orange=vec3(1.0,0.35,0.0);
vec3 gold=vec3(1.0,0.8,0.1);
vec3 white=vec3(1.0,0.95,0.9);

vec3 col=mix(deep,violet,smoothstep(0.0,0.2,v));
col=mix(col,magenta,smoothstep(0.2,0.45,v));
col=mix(col,orange,smoothstep(0.45,0.65,v+c*0.2));
col=mix(col,gold,smoothstep(0.65,0.85,v+c*0.3));
col=mix(col,white,smoothstep(0.85,1.0,v+c*0.4+e*0.2));

// Symmetric glow around center
float dist=length(uv-vec2(0.5,0.5));
col+=vec3(0.1,0.05,0.2)*(1.0-smoothstep(0.0,0.4,dist))*c;

fc=vec4(col,1.0);}
)";

static PFNGLCREATESHADERPROC glCreateShader_=nullptr; static PFNGLSHADERSOURCEPROC glShaderSource_=nullptr;
static PFNGLCOMPILESHADERPROC glCompileShader_=nullptr; static PFNGLGETSHADERIVPROC glGetShaderiv_=nullptr;
static PFNGLGETSHADERINFOLOGPROC glGetShaderInfoLog_=nullptr; static PFNGLCREATEPROGRAMPROC glCreateProgram_=nullptr;
static PFNGLATTACHSHADERPROC glAttachShader_=nullptr; static PFNGLLINKPROGRAMPROC glLinkProgram_=nullptr;
static PFNGLGETPROGRAMIVPROC glGetProgramiv_=nullptr; static PFNGLGETPROGRAMINFOLOGPROC glGetProgramInfoLog_=nullptr;
static PFNGLUSEPROGRAMPROC glUseProgram_=nullptr; static PFNGLUNIFORM1FPROC glUniform1f_=nullptr;
static PFNGLUNIFORM2FPROC glUniform2f_=nullptr; static PFNGLUNIFORM1IPROC glUniform1i_=nullptr;
static PFNGLGETUNIFORMLOCATIONPROC glGetUniformLocation_=nullptr; static PFNGLGENBUFFERSPROC glGenBuffers_=nullptr;
static PFNGLBINDBUFFERPROC glBindBuffer_=nullptr; static PFNGLBUFFERDATAPROC glBufferData_=nullptr;
static PFNGLGENVERTEXARRAYSPROC glGenVertexArrays_=nullptr; static PFNGLBINDVERTEXARRAYPROC glBindVertexArray_=nullptr;
static PFNGLVERTEXATTRIBPOINTERPROC glVertexAttribPointer_=nullptr; static PFNGLENABLEVERTEXATTRIBARRAYPROC glEnableVertexAttribArray_=nullptr;
static PFNGLDELETEVERTEXARRAYSPROC glDeleteVertexArrays_=nullptr; static PFNGLDELETEBUFFERSPROC glDeleteBuffers_=nullptr;
static PFNGLDELETEPROGRAMPROC glDeleteProgram_=nullptr; static PFNGLDELETESHADERPROC glDeleteShader_=nullptr;

#define GLFN(name) name ## _
#define glCreateShader GLFN(glCreateShader)
#define glShaderSource GLFN(glShaderSource)
#define glCompileShader GLFN(glCompileShader)
#define glGetShaderiv GLFN(glGetShaderiv)
#define glGetShaderInfoLog GLFN(glGetShaderInfoLog)
#define glCreateProgram GLFN(glCreateProgram)
#define glAttachShader GLFN(glAttachShader)
#define glLinkProgram GLFN(glLinkProgram)
#define glGetProgramiv GLFN(glGetProgramiv)
#define glGetProgramInfoLog GLFN(glGetProgramInfoLog)
#define glUseProgram GLFN(glUseProgram)
#define glUniform1f GLFN(glUniform1f)
#define glUniform2f GLFN(glUniform2f)
#define glUniform1i GLFN(glUniform1i)
#define glGetUniformLocation GLFN(glGetUniformLocation)
#define glGenBuffers GLFN(glGenBuffers)
#define glBindBuffer GLFN(glBindBuffer)
#define glBufferData GLFN(glBufferData)
#define glGenVertexArrays GLFN(glGenVertexArrays)
#define glBindVertexArray GLFN(glBindVertexArray)
#define glVertexAttribPointer GLFN(glVertexAttribPointer)
#define glEnableVertexAttribArray GLFN(glEnableVertexAttribArray)
#define glDeleteVertexArrays GLFN(glDeleteVertexArrays)
#define glDeleteBuffers GLFN(glDeleteBuffers)
#define glDeleteProgram GLFN(glDeleteProgram)
#define glDeleteShader GLFN(glDeleteShader)

void loadGL() {
    #define L(n) n = (decltype(n))SDL_GL_GetProcAddress(#n)
    L(glCreateShader); L(glShaderSource); L(glCompileShader); L(glGetShaderiv); L(glGetShaderInfoLog);
    L(glCreateProgram); L(glAttachShader); L(glLinkProgram); L(glGetProgramiv); L(glGetProgramInfoLog);
    L(glUseProgram); L(glUniform1f); L(glUniform2f); L(glUniform1i); L(glGetUniformLocation);
    L(glGenBuffers); L(glBindBuffer); L(glBufferData); L(glGenVertexArrays); L(glBindVertexArray);
    L(glVertexAttribPointer); L(glEnableVertexAttribArray); L(glDeleteVertexArrays); L(glDeleteBuffers);
    L(glDeleteProgram); L(glDeleteShader);
    #undef L
}

GLuint compileShader(const char* src, GLenum type) {
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, nullptr);
    glCompileShader(s);
    GLint ok; glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) { char log[512]; glGetShaderInfoLog(s, 512, nullptr, log); std::cerr << "Shader error:\n" << log << "\n"; glDeleteShader(s); return 0; }
    return s;
}

GLuint buildProgram(const char* vs, const char* fs) {
    GLuint a = compileShader(vs, GL_VERTEX_SHADER);
    GLuint b = compileShader(fs, GL_FRAGMENT_SHADER);
    if (!a || !b) return 0;
    GLuint p = glCreateProgram();
    glAttachShader(p, a); glAttachShader(p, b);
    glLinkProgram(p);
    GLint ok; glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok) { char log[512]; glGetProgramInfoLog(p, 512, nullptr, log); std::cerr << "Link error:\n" << log << "\n"; glDeleteProgram(p); return 0; }
    glDeleteShader(a); glDeleteShader(b);
    return p;
}

// =============================================================================
// TEXTURE TEXT
// =============================================================================
struct TexText {
    GLuint tex = 0;
    int w = 0, h = 0;
    void render(TTF_Font* font, const char* text, SDL_Color color) {
        if (tex) glDeleteTextures(1, &tex);
        SDL_Surface* surf = TTF_RenderText_Blended(font, text, color);
        if (!surf) return;
        w = surf->w; h = surf->h;
        glGenTextures(1, &tex);
        glBindTexture(GL_TEXTURE_2D, tex);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, surf->pixels);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        SDL_FreeSurface(surf);
    }
    void draw(float x, float y, float screenW, float screenH) {
        if (!tex) return;
        float x0 = (x / screenW) * 2.0f - 1.0f;
        float y0 = 1.0f - (y / screenH) * 2.0f;
        float x1 = ((x + w) / screenW) * 2.0f - 1.0f;
        float y1 = 1.0f - ((y + h) / screenH) * 2.0f;
        glEnable(GL_TEXTURE_2D);
        glBindTexture(GL_TEXTURE_2D, tex);
        glBegin(GL_QUADS);
        glTexCoord2f(0, 0); glVertex2f(x0, y0);
        glTexCoord2f(1, 0); glVertex2f(x1, y0);
        glTexCoord2f(1, 1); glVertex2f(x1, y1);
        glTexCoord2f(0, 1); glVertex2f(x0, y1);
        glEnd();
        glDisable(GL_TEXTURE_2D);
    }
    void destroy() { if (tex) glDeleteTextures(1, &tex); }
};

// =============================================================================
// QUAD
// =============================================================================
struct Quad {
    GLuint vao=0, vbo=0;
    void init() {
        float v[] = {-1,-1, 1,-1, -1,1, 1,1};
        glGenVertexArrays(1, &vao); glGenBuffers(1, &vbo);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glBufferData(GL_ARRAY_BUFFER, sizeof(v), v, GL_STATIC_DRAW);
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, nullptr);
        glEnableVertexAttribArray(0);
        glBindVertexArray(0);
    }
    void draw() { glBindVertexArray(vao); glDrawArrays(GL_TRIANGLE_STRIP, 0, 4); }
    void destroy() { glDeleteVertexArrays(1, &vao); glDeleteBuffers(1, &vbo); }
};

// =============================================================================
// LOOKUPS
// =============================================================================
float lookupRefPitch(const Guide& g, double t) {
    if (g.pitch.empty()) return 0.0f;
    size_t lo = 0, hi = g.pitch.size() - 1;
    while (lo < hi) { size_t mid = (lo + hi) / 2; if (g.pitch[mid].time < t) lo = mid + 1; else hi = mid; }
    if (lo == 0) return g.pitch[0].midi;
    const auto& a = g.pitch[lo - 1]; const auto& b = g.pitch[lo];
    if (b.time <= a.time) return a.midi;
    float f = (float)((t - a.time) / (b.time - a.time));
    return a.midi + (b.midi - a.midi) * f;
}

float lookupRefEnergy(const Guide& g, double t) {
    if (g.energy.empty()) return 0.0f;
    size_t lo = 0, hi = g.energy.size() - 1;
    while (lo < hi) { size_t mid = (lo + hi) / 2; if (g.energy[mid].time < t) lo = mid + 1; else hi = mid; }
    if (lo == 0) return g.energy[0].rms;
    const auto& a = g.energy[lo - 1]; const auto& b = g.energy[lo];
    if (b.time <= a.time) return a.rms;
    float f = (float)((t - a.time) / (b.time - a.time));
    return a.rms + (b.rms - a.rms) * f;
}

const Section* currentSection(const Guide& g, double t) {
    for (const auto& s : g.sections) if (t >= s.start && t < s.end) return &s;
    return g.sections.empty() ? nullptr : &g.sections.back();
}

const LyricWord* currentWord(const Guide& g, double t) {
    for (const auto& w : g.lyrics) if (t >= w.start && t < w.end) return &w;
    return nullptr;
}

std::vector<const LyricWord*> upcomingWords(const Guide& g, double t, int count=8) {
    std::vector<const LyricWord*> out;
    for (const auto& w : g.lyrics) {
        if (w.start > t) { out.push_back(&w); if ((int)out.size() >= count) break; }
    }
    return out;
}

// =============================================================================
// MAIN
// =============================================================================
int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: vocalguide <guide.json> <reference.mp3>\n";
        return 1;
    }

    Guide guide = loadGuide(argv[1]);
    if (guide.duration <= 0.0f) { std::cerr << "Failed to load guide\n"; return 1; }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_TIMER) < 0) { std::cerr << "SDL init failed\n"; return 1; }
    if (TTF_Init() < 0) { std::cerr << "TTF init failed\n"; SDL_Quit(); return 1; }

    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 3);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);

    int winW = 1280, winH = 720;
    SDL_Window* window = SDL_CreateWindow("NeonForge Vocal Guide",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, winW, winH,
        SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_SHOWN);
    if (!window) { TTF_Quit(); SDL_Quit(); return 1; }

    SDL_GLContext glc = SDL_GL_CreateContext(window);
    if (!glc) { SDL_DestroyWindow(window); TTF_Quit(); SDL_Quit(); return 1; }
    loadGL();

    AppAudio audio;
    gAudio = &audio;
    if (!initAudio(&audio, argv[2])) {
        SDL_GL_DeleteContext(glc); SDL_DestroyWindow(window); TTF_Quit(); SDL_Quit(); return 1;
    }

    // Try multiple font paths
    TTF_Font* fontBig = nullptr, *fontMed = nullptr, *fontSmall = nullptr;
    const char* fontPaths[] = {
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
    };
    const char* fontPathsReg[] = {
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
    };
    for (auto p : fontPaths) { if (!fontBig) fontBig = TTF_OpenFont(p, 52); }
    for (auto p : fontPathsReg) { if (!fontMed) fontMed = TTF_OpenFont(p, 28); }
    for (auto p : fontPathsReg) { if (!fontSmall) fontSmall = TTF_OpenFont(p, 18); }

    GLuint prog = buildProgram(vertSrc, cymaticFrag);
    GLint uTime = glGetUniformLocation(prog, "u_time");
    GLint uRes = glGetUniformLocation(prog, "u_res");
    GLint uEnergy = glGetUniformLocation(prog, "u_energy");
    GLint uPitch = glGetUniformLocation(prog, "u_pitch");
    GLint uCons = glGetUniformLocation(prog, "u_consistency");
    Quad quad; quad.init();

    YIN yin; FormantAnalyzer formant;
    TexText texSection, texLineCurrent, texLineNext, texWord, texInfo, texBarNum;
    SDL_Color white = {255,255,255,255};
    SDL_Color gold = {255,220,50,255};
    SDL_Color cyan = {80,255,255,255};
    SDL_Color dim = {180,180,180,200};
    SDL_Color hot = {255,100,100,255};

    bool running = true, paused = false;
    double pauseOffset = 0.0;
    float smoothCons = 0.0f, smoothEnergy = 0.0f, smoothPitch = 0.0f;

    ma_sound_start(&audio.sound);

    while (running) {
        SDL_Event e;
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_QUIT) running = false;
            if (e.type == SDL_KEYDOWN) {
                if (e.key.keysym.sym == SDLK_SPACE) {
                    paused = !paused;
                    if (paused) { ma_sound_stop(&audio.sound); pauseOffset = playbackTime(&audio); }
                    else { ma_sound_start(&audio.sound); }
                }
                if (e.key.keysym.sym == SDLK_ESCAPE) running = false;
                if (e.key.keysym.sym == SDLK_r) {
                    ma_sound_stop(&audio.sound);
                    ma_sound_seek_to_pcm_frame(&audio.sound, 0);
                    ma_sound_start(&audio.sound);
                    paused = false; pauseOffset = 0.0;
                }
            }
            if (e.type == SDL_WINDOWEVENT && e.window.event == SDL_WINDOWEVENT_RESIZED) {
                winW = e.window.data1; winH = e.window.data2;
                glViewport(0, 0, winW, winH);
            }
        }

        double t = paused ? pauseOffset : playbackTime(&audio);
        if (t > guide.duration) { t = guide.duration; paused = true; }

        // ---- MIC ----
        float liveFreq = 0.0f, liveMidi = 0.0f;
        float f1=0, f2=0, f3=0;
        std::vector<float> micBuf(2048);
        {
            SDL_LockMutex(audio.micMutex);
            size_t n = std::min(audio.micRing.size(), micBuf.size());
            if (n > 0) { auto it = audio.micRing.end() - n; for (size_t i = 0; i < n; ++i) micBuf[i] = it[i]; }
            SDL_UnlockMutex(audio.micMutex);
        }
        if (micBuf.size() >= 1024) {
            liveFreq = yin.detect(micBuf.data(), (int)micBuf.size());
            if (liveFreq > 20.0f && liveFreq < 2000.0f)
                liveMidi = 69.0f + 12.0f * log2f(liveFreq / 440.0f);
            std::vector<float> fbuf(4096);
            for (size_t i = 0; i < fbuf.size() && i < micBuf.size(); ++i) fbuf[i] = micBuf[i];
            formant.analyze(fbuf.data(), (int)fbuf.size(), 44100.0f, &f1, &f2, &f3);
        }

        float refMidi = lookupRefPitch(guide, t);
        float refEnergy = lookupRefEnergy(guide, t);
        float consistency = 0.0f;
        if (liveMidi > 0.0f && refMidi > 0.0f) {
            float diff = fabsf(liveMidi - refMidi);
            consistency = 1.0f - diff / 12.0f;
            if (consistency < 0.0f) consistency = 0.0f;
        }
        smoothCons += (consistency - smoothCons) * 0.1f;
        smoothEnergy += (refEnergy * 5.0f - smoothEnergy) * 0.05f;
        if (smoothEnergy < 0.0f) smoothEnergy = 0.0f;
        if (liveMidi > 0.0f) smoothPitch += (liveMidi - smoothPitch) * 0.2f;

        // ---- RENDER CYMATIC BACKGROUND ----
        glClear(GL_COLOR_BUFFER_BIT);
        glUseProgram(prog);
        glUniform1f(uTime, (float)(SDL_GetTicks() / 1000.0));
        glUniform2f(uRes, (float)winW, (float)winH);
        glUniform1f(uEnergy, smoothEnergy);
        glUniform1f(uPitch, liveFreq);
        glUniform1f(uCons, smoothCons);
        quad.draw();

        // ---- UI OVERLAY ----
        glUseProgram(0);
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

        float laneY0 = winH * 0.22f;
        float laneH = winH * 0.56f;
        float midiMin = 48.0f, midiMax = 84.0f;
        float timeWindow = (60.0f / guide.bpm) * guide.beatsPerBar * 4.0f;
        float timeCenter = (float)t;
        float timeLeft = timeCenter - timeWindow * 0.5f;
        float timeRight = timeCenter + timeWindow * 0.5f;

        auto timeToX = [&](float sec) -> float {
            return ((sec - timeLeft) / timeWindow) * winW;
        };
        auto midiToY = [&](float m) -> float {
            return laneY0 + laneH - ((m - midiMin) / (midiMax - midiMin)) * laneH;
        };

        // Lane glass panel
        glColor4f(0.0f, 0.0f, 0.0f, 0.35f);
        glBegin(GL_QUADS);
        glVertex2f(0, laneY0); glVertex2f(winW, laneY0);
        glVertex2f(winW, laneY0 + laneH); glVertex2f(0, laneY0 + laneH);
        glEnd();

        // BEAT LATTICE — symmetric cymatic grid
        glLineWidth(1.0f);
        for (const auto& bar : guide.bars) {
            if (bar.end < timeLeft || bar.start > timeRight) continue;
            float x = timeToX(bar.start);
            // Downbeat (bar start) — thick, bright
            glColor4f(1.0f, 0.9f, 0.3f, 0.5f);
            glLineWidth(2.5f);
            glBegin(GL_LINES);
            glVertex2f(x, laneY0); glVertex2f(x, laneY0 + laneH);
            glEnd();
            // Bar number
            if (fontSmall) {
                char bn[32]; snprintf(bn, sizeof(bn), "%d", bar.index + 1);
                texBarNum.render(fontSmall, bn, gold);
                texBarNum.draw(x + 4, laneY0 + laneH - texBarNum.h - 4, winW, winH);
            }
            // Sub-beats — thin, dim
            glLineWidth(1.0f);
            for (size_t bi = 1; bi < bar.beats.size(); ++bi) {
                float bt = bar.beats[bi];
                if (bt < timeLeft || bt > timeRight) continue;
                float bx = timeToX(bt);
                bool isDownbeat = (bi % guide.beatsPerBar == 0);
                glColor4f(1.0f, 1.0f, 1.0f, isDownbeat ? 0.25f : 0.08f);
                glBegin(GL_LINES);
                glVertex2f(bx, laneY0); glVertex2f(bx, laneY0 + laneH);
                glEnd();
            }
        }

        // Section color bands
        for (const auto& sec : guide.sections) {
            if (sec.end < timeLeft || sec.start > timeRight) continue;
            float x0 = timeToX(sec.start);
            float x1 = timeToX(sec.end);
            unsigned int h = 0;
            for (char c : sec.name) h = h * 31 + c;
            float r = ((h >> 0) & 0xFF) / 255.0f * 0.25f + 0.05f;
            float g = ((h >> 8) & 0xFF) / 255.0f * 0.25f + 0.05f;
            float b = ((h >> 16) & 0xFF) / 255.0f * 0.25f + 0.05f;
            glColor4f(r, g, b, 0.3f);
            glBegin(GL_QUADS);
            glVertex2f(x0, laneY0); glVertex2f(x1, laneY0);
            glVertex2f(x1, laneY0 + laneH); glVertex2f(x0, laneY0 + laneH);
            glEnd();
        }

        // Reference pitch contour (cyan lattice line)
        glLineWidth(2.0f);
        glColor4f(0.3f, 0.85f, 1.0f, 0.55f);
        glBegin(GL_LINE_STRIP);
        for (const auto& p : guide.pitch) {
            if (p.time < timeLeft || p.time > timeRight) continue;
            if (p.midi > midiMin && p.midi < midiMax)
                glVertex2f(timeToX(p.time), midiToY(p.midi));
        }
        glEnd();

        // Now-line (symmetry axis)
        float nowX = timeToX((float)t);
        glLineWidth(2.0f);
        glColor4f(1.0f, 0.95f, 0.4f, 0.85f);
        glBegin(GL_LINES);
        glVertex2f(nowX, laneY0); glVertex2f(nowX, laneY0 + laneH);
        glEnd();

        // Live pitch orb
        if (smoothPitch > midiMin && smoothPitch < midiMax) {
            float py = midiToY(smoothPitch);
            float size = 6.0f + smoothCons * 14.0f;
            glColor4f(1.0f - smoothCons * 0.4f, smoothCons * 0.9f + 0.1f, 0.3f, 0.9f);
            glBegin(GL_TRIANGLE_FAN);
            for (int i = 0; i <= 24; ++i) {
                float ang = 6.2831853f * i / 24.0f;
                glVertex2f(nowX + cosf(ang) * size, py + sinf(ang) * size);
            }
            glEnd();
            // Consistency ring
            float ringR = 25.0f + smoothCons * 45.0f;
            glColor4f(1.0f, 0.85f, 0.0f, 0.2f + smoothCons * 0.5f);
            glLineWidth(2.5f);
            glBegin(GL_LINE_LOOP);
            for (int i = 0; i <= 48; ++i) {
                float ang = 6.2831853f * i / 48.0f;
                glVertex2f(nowX + cosf(ang) * ringR, py + sinf(ang) * ringR);
            }
            glEnd();
        }

        // ---- LYRICS ON THE LATTICE ----
        if (fontMed && !guide.lyrics.empty()) {
            for (const auto& w : guide.lyrics) {
                if (w.end < timeLeft || w.start > timeRight) continue;
                float wx = timeToX(w.start);
                // Position vertically by bar (stack bars vertically within lane)
                float barFrac = (float)w.barIndex / std::max(1, (int)guide.bars.size());
                float wy = laneY0 + 20 + (w.barIndex % 3) * 30;
                bool isCurrent = (t >= w.start && t < w.end);
                bool isPast = (t > w.end);
                bool isFuture = (t < w.start);
                float alpha = isCurrent ? 1.0f : (isPast ? 0.25f : 0.6f);
                SDL_Color wc = isCurrent ? gold : (isPast ? dim : white);
                texWord.render(fontMed, w.text.c_str(), wc);
                // Fade with distance from center
                float dist = fabsf(wx - nowX) / (winW * 0.5f);
                alpha *= 1.0f - dist * 0.5f;
                if (alpha > 0.05f) {
                    glColor4f(1,1,1,alpha);
                    texWord.draw(wx, wy, winW, winH);
                }
            }
        }

        // ---- TEXT OVERLAYS ----
        if (fontBig && fontMed && fontSmall) {
            char buf[256];
            const Section* cs = currentSection(guide, t);

            // Section name (top center)
            if (cs) {
                texSection.render(fontBig, cs->name.c_str(), gold);
                texSection.draw(winW/2 - texSection.w/2, 10, winW, winH);
            }

            // Current + next lyric lines (bottom area, lookahead)
            const LyricWord* cw = currentWord(guide, t);
            auto upcoming = upcomingWords(guide, t, 12);
            if (cw || !upcoming.empty()) {
                std::string curLine, nextLine;
                if (cw) curLine += cw->text + " ";
                int barTarget = cw ? cw->barIndex : (upcoming.empty() ? -1 : upcoming[0]->barIndex);
                for (auto* w : upcoming) {
                    if (w->barIndex == barTarget) curLine += w->text + " ";
                    else if (w->barIndex == barTarget + 1) nextLine += w->text + " ";
                    if (curLine.size() > 60 || nextLine.size() > 60) break;
                }
                if (!curLine.empty()) {
                    texLineCurrent.render(fontMed, curLine.c_str(), gold);
                    texLineCurrent.draw(winW/2 - texLineCurrent.w/2, winH - 110, winW, winH);
                }
                if (!nextLine.empty()) {
                    texLineNext.render(fontSmall, nextLine.c_str(), dim);
                    texLineNext.draw(winW/2 - texLineNext.w/2, winH - 70, winW, winH);
                }
            }

            // Time / Bar / BPM math
            int barIdx = 0;
            for (size_t i = 0; i < guide.bars.size(); ++i) {
                if (t >= guide.bars[i].start && t < guide.bars[i].end) { barIdx = (int)i + 1; break; }
            }
            int min = (int)(t / 60.0);
            int sec = (int)fmod(t, 60.0);
            snprintf(buf, sizeof(buf), "%02d:%02d  |  Bar %d  |  BPM %.0f  |  %.2f beats/sec",
                     min, sec, barIdx, guide.bpm, guide.beatsPerSecond);
            texInfo.render(fontSmall, buf, white);
            texInfo.draw(20, winH - texInfo.h - 15, winW, winH);

            // Live data
            if (liveMidi > 0) {
                snprintf(buf, sizeof(buf), "Live: %.1f Hz  MIDI %.1f  |  F1:%.0f F2:%.0f F3:%.0f",
                         liveFreq, liveMidi, f1, f2, f3);
                texInfo.render(fontSmall, buf, cyan);
                texInfo.draw(winW - texInfo.w - 20, winH - texInfo.h - 15, winW, winH);
            }
        }

        glDisable(GL_BLEND);
        SDL_GL_SwapWindow(window);
        SDL_Delay(16);
    }

    // Cleanup
    texSection.destroy(); texLineCurrent.destroy(); texLineNext.destroy();
    texWord.destroy(); texInfo.destroy(); texBarNum.destroy();
    quad.destroy(); glDeleteProgram(prog);
    if (fontBig) TTF_CloseFont(fontBig); if (fontMed) TTF_CloseFont(fontMed); if (fontSmall) TTF_CloseFont(fontSmall);
    shutdownAudio(&audio);
    SDL_GL_DeleteContext(glc); SDL_DestroyWindow(window); TTF_Quit(); SDL_Quit();
    return 0;
}
