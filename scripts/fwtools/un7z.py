#!/usr/bin/env python3
"""Minimal 7z extractor via system libarchive (ctypes). usage: un7z.py ARCHIVE OUTDIR"""
import ctypes, ctypes.util, os, sys
def main(arc, out):
    name = ctypes.util.find_library("archive") or "libarchive.so.13"
    la = ctypes.CDLL(name)
    la.archive_read_new.restype = ctypes.c_void_p
    la.archive_entry_pathname.restype = ctypes.c_char_p
    la.archive_entry_size.restype = ctypes.c_int64
    la.archive_error_string.restype = ctypes.c_char_p
    la.archive_read_data.restype = ctypes.c_ssize_t
    a = ctypes.c_void_p(la.archive_read_new())
    la.archive_read_support_format_all(a); la.archive_read_support_filter_all(a)
    if la.archive_read_open_filename(a, arc.encode(), 1 << 20) != 0:
        sys.exit("open failed: %r" % la.archive_error_string(a))
    e = ctypes.c_void_p()
    buf = ctypes.create_string_buffer(1 << 20)
    while la.archive_read_next_header(a, ctypes.byref(e)) == 0:
        p = la.archive_entry_pathname(e).decode("utf-8", "replace")
        rel = os.path.normpath(p)
        if rel.startswith("..") or os.path.isabs(rel):
            sys.exit("unsafe path " + p)
        dst = os.path.join(out, rel)
        if la.archive_entry_filetype(e) == 0o040000:
            os.makedirs(dst, exist_ok=True); continue
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        n = 0
        with open(dst, "wb") as f:
            while True:
                r = la.archive_read_data(a, buf, len(buf))
                if r < 0: sys.exit("read error: %r" % la.archive_error_string(a))
                if r == 0: break
                f.write(buf.raw[:r]); n += r
        print(n, rel)
    la.archive_read_free(a)
if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
