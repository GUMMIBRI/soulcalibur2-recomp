/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Mesa's public u_memstream ABI from PS5_Mesa
   7b59ef27c1b09b9671bc4153c41940c3155c3af2/src/util/memstream.h.
   The pinned non-Windows ABI contains just FILE *f. Its archive's POSIX
   implementation needs open_memstream, absent from the public console libc.
   Supply all three real entrypoints so that archive member is not pulled in.
   Like Mesa's Windows implementation, use a temporary file and publish a heap
   buffer on flush/close, without assuming the console's private FILE layout. */
#if defined(SC2_PS5)
#include "sc2_ps5.h"
#include <cstdio>
#include <cstdlib>
#include <cerrno>
#include <limits>
#include <map>
#include <mutex>

struct u_memstream { FILE *f; };
extern "C" int __real_fflush(FILE *);
extern "C" int __real_fclose(FILE *);

namespace {
struct StreamOutput { char **buffer; std::size_t *size; };
std::mutex stream_mutex;
std::map<FILE *, StreamOutput> streams;
constexpr std::size_t kMaxPublishedStream = 16u * 1024u * 1024u;
constexpr std::size_t kMaxOpenStreams = 32;

int publish(FILE *file, const StreamOutput &output)
{
    if (__real_fflush(file) != 0) return -1;
    const off_t position = ftello(file);
    if (position < 0 || static_cast<uint64_t>(position) >= std::numeric_limits<std::size_t>::max()) {
        errno = EOVERFLOW;
        return -1;
    }
    const auto size = static_cast<std::size_t>(position);
    if (size > kMaxPublishedStream) { errno = EFBIG; return -1; }
    char *buffer = static_cast<char *>(std::malloc(size + 1));
    if (!buffer) return -1;
    if (fseeko(file, 0, SEEK_SET) != 0) { std::free(buffer); return -1; }
    const bool read = std::fread(buffer, 1, size, file) == size;
    const bool restored = fseeko(file, position, SEEK_SET) == 0;
    if (!read || !restored) { std::free(buffer); errno = EIO; return -1; }
    buffer[size] = '\0';
    std::free(*output.buffer);
    *output.buffer = buffer;
    *output.size = size;
    return 0;
}
} // namespace

extern "C" bool u_memstream_open(u_memstream *mem, char **buffer, std::size_t *size)
{
    if (!mem || !buffer || !size) { errno = EINVAL; return false; }
    mem->f = nullptr;
    const char *directory = std::getenv("SC2_PS5_STREAM_DIR");
    if (!directory || !*directory || !sc2::PS5WritablePath(directory)) { errno = EACCES; return false; }
    std::error_code error;
    std::filesystem::create_directories(directory, error);
    if (error) { errno = EACCES; return false; }
    std::string pattern = (std::filesystem::path(directory) / "mesa-XXXXXX").string();
    std::vector<char> name(pattern.begin(), pattern.end()); name.push_back('\0');
    const int fd = mkstemp(name.data());
    if (fd < 0) return false;
    // Unlink while open: crashes cannot leave derived shader/debug text behind.
    if (unlink(name.data()) != 0) { const int failure = errno; close(fd); errno = failure; return false; }
    FILE *file = fdopen(fd, "w+b");
    if (!file) { const int failure = errno; close(fd); errno = failure; return false; }
    try {
        std::lock_guard<std::mutex> lock(stream_mutex);
        if (streams.size() >= kMaxOpenStreams) {
            __real_fclose(file);
            errno = EMFILE;
            return false;
        }
        streams.emplace(file, StreamOutput{buffer, size});
    } catch (...) { __real_fclose(file); errno = ENOMEM; return false; }
    *buffer = nullptr;
    *size = 0;
    mem->f = file;
    return true;
}

/* The SDK has no FILE cookie hooks. Wrap only fflush/fclose at static link
   time: registered streams publish their heap buffer; every other FILE is
   forwarded unchanged to the real libc. This also handles RADV's direct
   open_memstream users, not just its u_memstream convenience API. */
extern "C" FILE *open_memstream(char **buffer, std::size_t *size)
{
    u_memstream stream{};
    return u_memstream_open(&stream, buffer, size) ? stream.f : nullptr;
}

extern "C" int __wrap_fflush(FILE *file)
{
    std::lock_guard<std::mutex> lock(stream_mutex);
    if (!file) {
        int result = __real_fflush(nullptr);
        for (const auto &stream : streams)
            if (publish(stream.first, stream.second) != 0) result = EOF;
        return result;
    }
    const auto found = streams.find(file);
    return found == streams.end() ? __real_fflush(file) : publish(file, found->second);
}

extern "C" int __wrap_fclose(FILE *file)
{
    std::lock_guard<std::mutex> lock(stream_mutex);
    const auto found = streams.find(file);
    int result = 0;
    if (found != streams.end()) {
        result = publish(file, found->second);
        streams.erase(found);
    }
    const int closed = __real_fclose(file);
    return result != 0 ? EOF : closed;
}

extern "C" int u_memstream_flush(u_memstream *mem)
{
    if (!mem || !mem->f) { errno = EINVAL; return EOF; }
    return __wrap_fflush(mem->f);
}

extern "C" void u_memstream_close(u_memstream *mem)
{
    if (!mem || !mem->f) return;
    if (__wrap_fclose(mem->f) != 0)
        std::fprintf(stderr, "SC2 Mesa: cannot close memory stream: %s\n", std::strerror(errno));
    mem->f = nullptr;
}
#endif
