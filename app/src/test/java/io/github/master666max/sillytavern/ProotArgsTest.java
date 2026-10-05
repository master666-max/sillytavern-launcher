package io.github.master666max.sillytavern;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import java.io.File;
import java.util.Map;
import org.junit.Test;

public class ProotArgsTest {

    private final File rootfs = new File("/data/pkg/files/rootfs");
    private final File runtime = new File("/data/pkg/files/runtime");
    private final File cache = new File("/data/pkg/cache");

    @Test
    public void commandTargetsBundledNodeInsideRootfs() {
        String[] cmd = RuntimeProvision.prootCommand(rootfs, runtime);
        assertArrayEquals(new String[]{
                new File(runtime, "proot").getAbsolutePath(),
                "-r", rootfs.getAbsolutePath(),
                "-0",
                "-w", "/opt/st",
                "--kill-on-exit",
                "-b", "/dev",
                "-b", "/proc",
                "-b", "/sys",
                "/usr/bin/nice", "-n", "10",
                "/usr/local/bin/node", "/opt/st/server.js",
        }, cmd);
    }

    @Test
    public void envOverridesTermuxHardcodedLoaderPath() {
        Map<String, String> env = RuntimeProvision.prootEnv(runtime, cache);
        // termux proot hardcodes /data/data/com.termux/... loader paths; our
        // package differs, so PROOT_LOADER must point into our runtime dir.
        assertEquals(new File(runtime, "loader").getAbsolutePath(), env.get("PROOT_LOADER"));
        assertEquals(new File(runtime, "loader32").getAbsolutePath(), env.get("PROOT_LOADER_32"));
        assertEquals("1", env.get("PROOT_NO_SECCOMP"));
        assertEquals(cache.getAbsolutePath(), env.get("PROOT_TMP_DIR"));
        assertEquals(runtime.getAbsolutePath(), env.get("LD_LIBRARY_PATH"));
        assertEquals("/opt/st", env.get("HOME"));
        assertTrue(env.get("PATH").startsWith("/usr/local/bin"));
    }

    @Test
    public void portConstantMatchesPipelineConfig() {
        assertEquals(8000, RuntimeProvision.ST_PORT);
    }
}
