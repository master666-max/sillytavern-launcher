package io.github.master666max.sillytavern;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;

public class TarReaderTest {

    static class Entry {
        final String name;
        final int typeflag;
        final long size;
        final int mode;
        final String linkname;
        final byte[] content;

        Entry(String name, int typeflag, long size, int mode, String linkname, byte[] content) {
            this.name = name;
            this.typeflag = typeflag;
            this.size = size;
            this.mode = mode;
            this.linkname = linkname;
            this.content = content;
        }
    }

    private static List<Entry> readFixture() throws IOException {
        InputStream raw = TarReaderTest.class.getResourceAsStream("/fixture.tar.gz");
        assertNotNull("fixture.tar.gz missing from test resources", raw);
        final List<Entry> out = new ArrayList<>();
        try (java.util.zip.GZIPInputStream gz = new java.util.zip.GZIPInputStream(raw)) {
            TarReader.read(gz, (name, typeflag, size, mode, linkname, content) -> {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] chunk = new byte[4096];
                int n;
                while ((n = content.read(chunk)) > 0) {
                    buf.write(chunk, 0, n);
                }
                out.add(new Entry(name, typeflag, size, mode, linkname, buf.toByteArray()));
            });
        }
        return out;
    }

    private static Entry find(List<Entry> entries, String name) {
        for (Entry e : entries) {
            if (name.equals(e.name)) {
                return e;
            }
        }
        return null;
    }

    @Test
    public void readsRegularFileWithContentAndMode() throws IOException {
        List<Entry> entries = readFixture();
        Entry f = find(entries, "dir/file.txt");
        assertNotNull(f);
        assertEquals(TarReader.TYPE_REG, f.typeflag);
        assertEquals(5, f.size);
        assertEquals(0644, f.mode & 0777);
        assertArrayEquals("hello".getBytes("UTF-8"), f.content);
    }

    @Test
    public void readsSymlinkAndHardlink() throws IOException {
        List<Entry> entries = readFixture();
        Entry link = find(entries, "dir/link");
        assertNotNull(link);
        assertEquals(TarReader.TYPE_SYMLINK, link.typeflag);
        assertEquals("file.txt", link.linkname);

        Entry hard = find(entries, "dir/hard");
        assertNotNull(hard);
        assertEquals(TarReader.TYPE_LINK, hard.typeflag);
        assertEquals("dir/file.txt", hard.linkname);
    }

    @Test
    public void handlesGnuLongName() throws IOException {
        List<Entry> entries = readFixture();
        StringBuilder sb = new StringBuilder("dir/");
        for (int i = 0; i < 40; i++) {
            sb.append("long");
        }
        Entry longFile = find(entries, sb.append(".dat").toString());
        assertNotNull("GNU longname entry not resolved", longFile);
        assertEquals(16, longFile.size);
        for (int i = 0; i < 16; i++) {
            assertEquals((byte) i, longFile.content[i]);
        }
    }

    @Test
    public void preservesExecutableMode() throws IOException {
        List<Entry> entries = readFixture();
        Entry sh = find(entries, "dir/run.sh");
        assertNotNull(sh);
        assertEquals(0755, sh.mode & 0777);
        assertTrue((sh.mode & 0111) != 0);
    }

    @Test
    public void readsAllEntriesInOrder() throws IOException {
        List<Entry> entries = readFixture();
        assertEquals(6, entries.size());
        assertEquals("dir", entries.get(0).name);
    }
}
