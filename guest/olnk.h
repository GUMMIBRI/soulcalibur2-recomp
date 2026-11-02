/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Namco's "olnk" containers (root.olk) and the numbered packs inside them
   (tools/guests/olnk.py describes both). */
#ifndef SC2_GUEST_OLNK_H
#define SC2_GUEST_OLNK_H

#include "bytes.h"

#include <functional>
#include <optional>

namespace guest {

/* A container read through a reader (a file, or a disc image's file). */
class Olnk {
public:
    using Reader = std::function<Bytes(uint64_t offset, size_t size)>;
    Olnk(Reader read, uint64_t base);

    uint32_t count() const { return count_; }
    uint32_t alignment() const { return alignment_; }
    uint32_t time() const { return time_; }
    /* entry i: its bytes (empty for a hole), its time */
    Bytes bytes(uint32_t i) const;
    uint32_t entry_time(uint32_t i) const;
    uint32_t entry_size(uint32_t i) const;
    bool is_container(uint32_t i) const;
    Olnk child(uint32_t i) const;

private:
    Reader read_;
    uint64_t base_;
    uint32_t count_, alignment_, header_, time_;
    Bytes index_;
};

/* An olnk container of entries (empty ones are holes), each with its time. */
Bytes build_olnk(const std::vector<Bytes> &entries, const std::vector<uint32_t> &times, uint32_t alignment,
                 uint32_t time);

/* The parts of a numbered pack, or nothing when the bytes are not one. */
std::optional<std::vector<Bytes>> pack_parts(const Bytes &data, bool big_endian);
/* A little-endian numbered pack, each part on `alignment`. */
Bytes build_pack(const std::vector<Bytes> &parts, size_t alignment = 0x80);
/* The alignment a little-endian pack's parts start on (0x80 or 0x800). */
size_t pack_alignment(const Bytes &pack);

} // namespace guest

#endif
