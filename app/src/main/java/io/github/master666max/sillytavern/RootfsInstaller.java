package io.github.master666max.sillytavern;

import android.content.Context;
import android.system.ErrnoException;
import android.system.Os;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.zip.GZIPInputStream;

/**
 * First-run extraction of the bundled rootfs.tar.gz into app-private
 * storage, restoring Unix permissions well enough for node + proot to run.
 */
public final class RootfsInstaller {

    public static final String ROOTFS_VERSION = "1.19.0-1";
    private static final String VERSION_FILE = ".st-version";

    public interface Progress {
        /** @param entries extracted entry count so far
         *  @param bytes   decompressed bytes so far */
        void onProgress(long entries, long bytes);
    }

    private RootfsInstaller() {
    }

    public static File rootfsDir(Context ctx) {
        return new File(ctx.getFilesDir(), "rootfs");
    }

    public static boolean isInstalled(Context ctx) {
        File marker = new File(rootfsDir(ctx), VERSION_FILE);
        if (!marker.isFile()) {
            return false;
        }
        try (InputStream in = new java.io.FileInputStream(marker)) {
            byte[] buf = new byte[32];
            int n = in.read(buf);
            String v = n > 0 ? new String(buf, 0, n).trim() : "";
            return ROOTFS_VERSION.equals(v);
        } catch (IOException e) {
            return false;
        }
    }

    public static void install(Context ctx, Progress progress) throws IOException {
        final String TAG = "ST-Extract";
        File rootfs = rootfsDir(ctx);
        android.util.Log.i(TAG, "install begin, rootfs=" + rootfs);
        // Fresh extraction: a partial or version-mismatched tree is unusable.
        deleteRecursively(rootfs);
        if (!rootfs.isDirectory() && !rootfs.mkdirs() && !rootfs.isDirectory()) {
            throw new IOException("cannot create rootfs dir: " + rootfs);
        }
        android.util.Log.i(TAG, "opening asset");
        // .stgz: aapt2 strips/preprocesses ".gz" assets, so the archive ships
        // under a custom extension with noCompress configured in build.gradle.
        InputStream asset = ctx.getAssets().open("rootfs.stgz");
        android.util.Log.i(TAG, "asset opened, wrapping gzip");

        long bytes = 0;
        final long[] entryCount = {0};
        try (InputStream raw = new java.util.zip.GZIPInputStream(
                new java.io.BufferedInputStream(asset, 65536))) {
            android.util.Log.i(TAG, "gzip opened, streaming entries");
            final CountingStream counter = new CountingStream(raw);
            TarReader.read(counter, (name, typeflag, size, mode, linkname, content) -> {
                File target = safeChild(rootfs, name);
                if (target == null) {
                    return;
                }
                switch (typeflag) {
                    case TarReader.TYPE_DIR:
                        mkdirs(target);
                        break;
                    case TarReader.TYPE_REG:
                        mkdirs(target.getParentFile());
                        extractFile(target, content, mode);
                        break;
                    case TarReader.TYPE_SYMLINK:
                        mkdirs(target.getParentFile());
                        symlink(target, linkname);
                        break;
                    case TarReader.TYPE_LINK:
                        // npm trees rarely hardlink; a best-effort copy is fine.
                        mkdirs(target.getParentFile());
                        hardlinkOrIgnore(target, new File(rootfs, linkname));
                        break;
                    default:
                        break;
                }
                long n = ++entryCount[0];
                if (n % 2000 == 0) {
                    android.util.Log.i(TAG, "entries=" + n + " bytes=" + counter.count()
                            + " last=" + name);
                }
                progress.onProgress(n, counter.count());
            });
            android.util.Log.i(TAG, "stream done, entries=" + entryCount[0]);
        }
        // Marker must be written last so an interrupted extract re-runs.
        if (!writeMarker(new File(rootfs, VERSION_FILE))) {
            throw new IOException("cannot write version marker");
        }
    }

    private static final class CountingStream extends java.io.FilterInputStream {
        private volatile long count;

        CountingStream(InputStream in) {
            super(in);
        }

        @Override
        public int read() throws IOException {
            int c = super.read();
            if (c >= 0) {
                count++;
            }
            return c;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            int n = super.read(b, off, len);
            if (n > 0) {
                count += n;
            }
            return n;
        }

        long count() {
            return count;
        }
    }

    /** Blocks path traversal outside the rootfs (entries are pipeline-controlled). */
    private static File safeChild(File rootfs, String name) {
        if (name == null || name.isEmpty() || name.contains("../") || name.contains("/..")
                || name.contains("\\") || name.startsWith("/")) {
            return null;
        }
        return new File(rootfs, name);
    }

    private static void extractFile(File target, InputStream content, int mode) throws IOException {
        // The base rootfs may have left a (dangling) symlink here; the archive
        // is streamed in order, so a later regular file always supersedes it.
        removeIfExists(target);
        try (FileOutputStream out = new FileOutputStream(target)) {
            byte[] buf = new byte[65536];
            int n;
            while ((n = content.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
        }
        target.setReadable(true, false);
        target.setWritable(true, false);
        if ((mode & 0111) != 0) {
            target.setExecutable(true, false);
        }
    }

    private static void mkdirs(File dir) throws IOException {
        if (!dir.isDirectory() && !dir.mkdirs() && !dir.isDirectory()) {
            throw new IOException("cannot mkdir " + dir);
        }
    }

    private static void symlink(File target, String linkname) {
        try {
            removeIfExists(target);
            Os.symlink(linkname, target.getAbsolutePath());
        } catch (ErrnoException e) {
            // keep going: a failed symlink is non-fatal for node/ST
        }
    }

    /** Deletes whatever sits at the path, including dangling symlinks. */
    private static void removeIfExists(File target) {
        try {
            java.nio.file.Files.deleteIfExists(
                    java.nio.file.Paths.get(target.getAbsolutePath()));
        } catch (IOException ignored) {
            // next write will surface the real failure
        }
    }

    private static void hardlinkOrIgnore(File target, File source) {
        try {
            Os.link(source.getAbsolutePath(), target.getAbsolutePath());
        } catch (ErrnoException e) {
            // ignore
        }
    }

    private static boolean writeMarker(File marker) throws IOException {
        try (FileOutputStream out = new FileOutputStream(marker)) {
            out.write(ROOTFS_VERSION.getBytes("UTF-8"));
        }
        return true;
    }

    static void deleteRecursively(File f) {
        if (f == null || !f.exists()) {
            return;
        }
        File[] children = f.listFiles();
        if (children != null) {
            for (File c : children) {
                deleteRecursively(c);
            }
        }
        f.delete();
    }
}
