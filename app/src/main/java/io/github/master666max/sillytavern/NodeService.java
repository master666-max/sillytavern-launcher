package io.github.master666max.sillytavern;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import java.io.File;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Map;

/**
 * Foreground service that runs the bundled SillyTavern Node server via proot
 * and keeps it alive while the app is backgrounded.
 *
 * The child process is launched strictly as an argv list through
 * ProcessBuilder (no shell involved); all arguments are package-internal
 * paths built by RuntimeProvision, never user input.
 */
public class NodeService extends Service {

    public static final String ACTION_START = "io.github.master666max.sillytavern.START";
    public static final String ACTION_STOP = "io.github.master666max.sillytavern.STOP";
    public static final String ACTION_READY = "io.github.master666max.sillytavern.READY";
    public static final String ACTION_FAILED = "io.github.master666max.sillytavern.FAILED";

    private static final String CHANNEL_ID = "st_service";
    private static final int NOTIF_ID = 1;
    // First start compiles the ST frontend: 8+ min on weak devices (but the
    // bundled rootfs ships with a prebuilt webpack cache, so this is rare).
    private static final long READY_TIMEOUT_MS = 900_000;
    private static final long POLL_INTERVAL_MS = 1500;
    private static final long WATCHDOG_INTERVAL_MS = 60_000;

    private Process process;
    private Thread waiter;
    private final Handler main = new Handler(Looper.getMainLooper());

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopServer();
            return START_NOT_STICKY;
        }
        startForeground(NOTIF_ID, buildNotification("酒馆服务运行中"));
        if (process == null) {
            startServer();
        }
        return START_STICKY;
    }

    private void startServer() {
        android.util.Log.i("ST-Node", "startServer begin");
        try {
            RuntimeProvision.provision(this);
            // user-editable config from the external dir wins over factory
            RuntimeProvision.syncExternalConfig(this);
        } catch (IOException e) {
            android.util.Log.e("ST-Node", "provision failed", e);
            broadcast(ACTION_FAILED, "运行时初始化失败: " + e.getMessage());
            stopSelf();
            return;
        }
        android.util.Log.i("ST-Node", "provision done, launching child");
        Process proc = launchChild();
        android.util.Log.i("ST-Node", "launchChild -> " + (proc != null ? "started" : "null"));
        if (proc == null) {
            broadcast(ACTION_FAILED, "无法启动内置环境");
            stopSelf();
            return;
        }
        process = proc;
        trackExit(proc);
        pollReady();
    }

    /** argv-list launch: no shell, no string concatenation of user data.
     *  Prefers the bionic runtime (/opt/bionic) when present: node executes
     *  directly, no proot and no ptrace tax. Falls back to proot otherwise. */
    private Process launchChild() {
        File rootfs = RuntimeProvision.rootfsDir(this);
        File log = RuntimeProvision.logFile(this);
        if (log.exists()) {
            log.delete();
        }
        ProcessBuilder pb = new ProcessBuilder();
        Map<String, String> env;
        if (RuntimeProvision.bionicAvailable(this)) {
            File bionic = RuntimeProvision.bionicDir(this);
            // OEM ROMs sometimes fail File.setExecutable(); force the bit via
            // chmod so exec cannot fail with EACCES (exit code 13).
            RuntimeProvision.ensureBionicExecutable(this);
            pb.command(RuntimeProvision.bionicCommand(rootfs, bionic));
            pb.directory(new File(rootfs, "opt/st"));
            env = RuntimeProvision.bionicEnv(rootfs, bionic, getCacheDir());
            android.util.Log.i("ST-Node", "launching with bionic runtime (no proot)");
        } else {
            File runtime = RuntimeProvision.runtimeDir(this);
            pb.command(RuntimeProvision.prootCommand(rootfs, runtime));
            pb.directory(getFilesDir());
            env = RuntimeProvision.prootEnv(runtime, getCacheDir());
            android.util.Log.i("ST-Node", "launching with proot runtime");
        }
        pb.redirectErrorStream(true);
        pb.redirectOutput(ProcessBuilder.Redirect.appendTo(log));
        pb.environment().putAll(env);
        try {
            Process p = pb.start();
            android.util.Log.i("ST-Node", "child started");
            return p;
        } catch (IOException e) {
            android.util.Log.e("ST-Node", "pb.start failed", e);
            return null;
        }
    }

    private void trackExit(final Process proc) {
        waiter = new Thread(() -> {
            try {
                int code = proc.waitFor();
                if (code != 0 && process == proc) {
                    final String tail = readLogTail(RuntimeProvision.logFile(this), 2000);
                    main.post(() -> {
                        if (process == proc) {
                            Intent i = new Intent(ACTION_FAILED).setPackage(getPackageName());
                            i.putExtra("message", "内置环境异常退出（代码 " + code + "）");
                            i.putExtra("log", tail);
                            sendBroadcast(i);
                        }
                    });
                }
            } catch (InterruptedException ignored) {
                // service shutting down
            }
        }, "st-exit-watcher");
        waiter.setDaemon(true);
        waiter.start();
    }

    /** Last N characters of the server log, for on-screen diagnostics. */
    private static String readLogTail(File log, int maxChars) {
        try (java.io.RandomAccessFile raf = new java.io.RandomAccessFile(log, "r")) {
            long len = raf.length();
            long start = Math.max(0, len - maxChars);
            raf.seek(start);
            byte[] buf = new byte[(int) (len - start)];
            raf.readFully(buf);
            return new String(buf, "UTF-8");
        } catch (Exception e) {
            return "(log unavailable: " + e.getMessage() + ")";
        }
    }

    private void pollReady() {
        final long deadline = System.currentTimeMillis() + READY_TIMEOUT_MS;
        Thread t = new Thread(() -> {
            while (System.currentTimeMillis() < deadline) {
                if (isServerUp()) {
                    broadcast(ACTION_READY, null);
                    startWatchdog();
                    return;
                }
                try {
                    Thread.sleep(POLL_INTERVAL_MS);
                } catch (InterruptedException e) {
                    return;
                }
            }
            broadcast(ACTION_FAILED, "等待酒馆启动超时");
        }, "st-ready-poll");
        t.setDaemon(true);
        t.start();
    }

    /** After READY: if the server process dies (OOM, ANR-kill), relaunch it
     *  (max 5x). Liveness is a cheap process check — the HTTP probe woke the
     *  event loop every 30s for nothing. */
    private void startWatchdog() {
        Thread t = new Thread(() -> {
            int restarts = 0;
            try {
                while (restarts < 5) {
                    Thread.sleep(WATCHDOG_INTERVAL_MS);
                    Process proc = process;
                    if (proc == null) {
                        return; // stopped by user
                    }
                    if (proc.isAlive()) {
                        continue;
                    }
                    Process relaunched = launchChild();
                    if (relaunched == null) {
                        main.post(() -> broadcast(ACTION_FAILED, "酒馆进程掉线且重启失败"));
                        return;
                    }
                    process = relaunched;
                    restarts++;
                    trackExit(relaunched);
                    pollReady();
                }
            } catch (InterruptedException ignored) {
                // stopped
            }
        }, "st-watchdog");
        t.setDaemon(true);
        t.start();
    }

    private boolean isServerUp() {
        try {
            HttpURLConnection conn = (HttpURLConnection) new URL(
                    "http://127.0.0.1:" + RuntimeProvision.ST_PORT + "/").openConnection();
            conn.setConnectTimeout(1000);
            conn.setReadTimeout(1000);
            int code = conn.getResponseCode();
            conn.disconnect();
            return code > 0;
        } catch (IOException e) {
            return false;
        }
    }

    private void stopServer() {
        if (process != null) {
            process.destroy();
            if (waiter != null) {
                waiter.interrupt();
            }
            try {
                if (!process.waitFor(3, java.util.concurrent.TimeUnit.SECONDS)) {
                    process.destroyForcibly();
                }
            } catch (InterruptedException ignored) {
                process.destroyForcibly();
            }
            process = null;
        }
        stopForeground(true);
        stopSelf();
    }

    @Override
    public void onDestroy() {
        if (process != null) {
            process.destroy();
            process = null;
        }
        super.onDestroy();
    }

    private void broadcast(String action, String message) {
        Intent i = new Intent(action).setPackage(getPackageName());
        if (message != null) {
            i.putExtra("message", message);
        }
        sendBroadcast(i);
    }

    private Notification buildNotification(String text) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL_ID) == null) {
            nm.createNotificationChannel(new NotificationChannel(CHANNEL_ID, "酒馆服务",
                    NotificationManager.IMPORTANCE_LOW));
        }
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT);
        Intent stop = new Intent(this, NodeService.class).setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 1, stop,
                PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        return b.setContentTitle("酒馆")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.stat_notify_sync_noanim)
                .setContentIntent(pi)
                .addAction(new Notification.Action.Builder(null, "停止", stopPi).build())
                .setOngoing(true)
                .build();
    }
}
