package io.github.master666max.sillytavern;

import static org.junit.Assert.assertTrue;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicLong;
import java.util.zip.GZIPInputStream;
import org.junit.Test;

/** Reproduces device-side extraction on the PC JVM: real rootfs archive. */
public class BigArchiveTest {

    @Test(timeout = 300_000)
    public void extractsRealRootfs() throws IOException {
        java.io.File f = new java.io.File("dist/rootfs-x86_64.tar.gz");
        org.junit.Assume.assumeTrue("rootfs not built, skipping", f.exists());
        Path dest = Files.createTempDirectory("rootfs-extract-test");
        AtomicLong entries = new AtomicLong();
        try (InputStream raw = new GZIPInputStream(
                new java.io.BufferedInputStream(new FileInputStream(f), 65536))) {
            TarReader.read(raw, (name, typeflag, size, mode, linkname, content) -> {
                long n = entries.incrementAndGet();
                if (n % 5000 == 0) {
                    System.out.println("entries=" + n + " last=" + name);
                }
                if (typeflag == TarReader.TYPE_REG) {
                    Path target = dest.resolve(name);
                    Files.createDirectories(target.getParent());
                    Files.copy(content, target, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
            });
        }
        System.out.println("TOTAL entries=" + entries.get());
        assertTrue(entries.get() > 10000);
    }
}
