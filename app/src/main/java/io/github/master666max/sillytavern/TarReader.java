package io.github.master666max.sillytavern;

import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

/**
 * Minimal streaming GNU-tar reader. Handles regular files, dirs, symlinks,
 * hard links, and GNU long-name ('L') members; skips device/fifo entries.
 * Non-file entries get a zero-length stream as content.
 */
public final class TarReader {

    public static final int TYPE_REG = '0';
    public static final int TYPE_LINK = '1';
    public static final int TYPE_SYMLINK = '2';
    public static final int TYPE_DIR = '5';
    public static final int TYPE_GNU_LONGNAME = 'L';

    public interface Callback {
        void entry(String name, int typeflag, long size, int mode, String linkname,
                InputStream content) throws IOException;
    }

    private static final int BLOCK = 512;

    private final InputStream in;
    private final byte[] header = new byte[BLOCK];
    private final byte[] skipBuf = new byte[8192];

    private TarReader(InputStream in) {
        this.in = in;
    }

    public static void read(InputStream raw, Callback cb) throws IOException {
        new TarReader(raw).run(cb);
    }

    private void run(Callback cb) throws IOException {
        String pendingLongName = null;
        while (true) {
            if (!readFully(header)) {
                return; // clean EOF before end blocks
            }
            if (isAllZero(header)) {
                return; // GNU end-of-archive
            }
            int typeflag = header[156] & 0xFF;
            long size = parseOctal(header, 124, 12);
            int mode = (int) parseOctal(header, 100, 8);
            String linkname = parseString(header, 157, 100);
            String name = pendingLongName != null ? pendingLongName : parseString(header, 0, 100);
            pendingLongName = null;
            while (name.endsWith("/")) {
                name = name.substring(0, name.length() - 1);
            }

            if (typeflag == TYPE_GNU_LONGNAME) {
                byte[] buf = new byte[(int) size];
                if (!readFully(buf)) {
                    throw new EOFException("truncated longname member");
                }
                skipAfter(size);
                pendingLongName = new String(buf, "UTF-8").trim();
                continue;
            }
            if (typeflag == '3' || typeflag == '4' || typeflag == '6' || typeflag == '7'
                    || typeflag == 'x' || typeflag == 'g' || typeflag == 'K') {
                skipAfter(size);
                continue;
            }
            int effectiveType = (typeflag == 0) ? TYPE_REG : typeflag;
            boolean hasContent = (effectiveType == TYPE_REG);
            EntryStream content = new EntryStream(hasContent ? size : 0L, size);
            try {
                cb.entry(name, effectiveType, size, mode, linkname, content);
            } finally {
                content.finish();
            }
        }
    }

    /** Skips whatever the callback did not read, plus the 512B block padding. */
    private final class EntryStream extends InputStream {
        private long remaining;
        private final long declaredSize;

        EntryStream(long limit, long declaredSize) {
            this.remaining = limit;
            this.declaredSize = declaredSize;
        }

        @Override
        public int read() throws IOException {
            byte[] one = new byte[1];
            int n = read(one, 0, 1);
            return n < 0 ? -1 : (one[0] & 0xFF);
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (remaining <= 0) {
                return -1;
            }
            int n = in.read(b, off, (int) Math.min(len, remaining));
            if (n < 0) {
                throw new EOFException("archive truncated");
            }
            remaining -= n;
            return n;
        }

        void finish() throws IOException {
            long unread = remaining;
            while (unread > 0) {
                long n = in.skip(unread);
                if (n <= 0) {
                    int chunk = (int) Math.min(unread, skipBuf.length);
                    int got = in.read(skipBuf, 0, chunk);
                    if (got < 0) {
                        throw new EOFException("archive truncated");
                    }
                    unread -= got;
                } else {
                    unread -= n;
                }
            }
            skipAfter(declaredSize);
        }
    }

    /** Skips the 512-byte block padding that follows a size-sized payload. */
    private void skipAfter(long size) throws IOException {
        long pad = (BLOCK - (size % BLOCK)) % BLOCK;
        while (pad > 0) {
            long n = in.skip(pad);
            if (n <= 0) {
                int chunk = (int) Math.min(pad, skipBuf.length);
                int got = in.read(skipBuf, 0, chunk);
                if (got < 0) {
                    throw new EOFException("archive truncated in padding");
                }
                pad -= got;
            } else {
                pad -= n;
            }
        }
    }

    /** Reads exactly b.length bytes; returns false on immediate EOF. */
    private boolean readFully(byte[] b) throws IOException {
        int total = 0;
        while (total < b.length) {
            int n = in.read(b, total, b.length - total);
            if (n < 0) {
                if (total == 0) {
                    return false;
                }
                throw new EOFException("unexpected EOF mid-block");
            }
            total += n;
        }
        return true;
    }

    private static boolean isAllZero(byte[] b) {
        for (byte x : b) {
            if (x != 0) {
                return false;
            }
        }
        return true;
    }

    private static String parseString(byte[] buf, int off, int len) {
        int end = off;
        int limit = off + len;
        while (end < limit && buf[end] != 0) {
            end++;
        }
        return new String(buf, off, end - off);
    }

    private static long parseOctal(byte[] buf, int off, int len) {
        long result = 0;
        int i = off;
        int limit = off + len;
        while (i < limit && (buf[i] == ' ' || buf[i] == 0)) {
            i++;
        }
        boolean any = false;
        for (; i < limit; i++) {
            byte c = buf[i];
            if (c == 0 || c == ' ') {
                break;
            }
            if (c < '0' || c > '7') {
                throw new IllegalArgumentException("bad octal digit " + c);
            }
            result = (result << 3) + (c - '0');
            any = true;
        }
        return any ? result : 0;
    }
}
