package io.github.master666max.sillytavern;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.widget.Button;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import java.io.IOException;

public class MainActivity extends Activity {

    private View extractContainer;
    private View mainContainer;
    private ProgressBar extractBar;
    private TextView extractStatus;
    private TextView envStatus;
    private Button launchBtn;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private boolean launching;

    private final BroadcastReceiver serviceReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (NodeService.ACTION_READY.equals(action)) {
                launching = false;
                startActivity(new Intent(MainActivity.this, WebActivity.class));
            } else if (NodeService.ACTION_FAILED.equals(action)) {
                launching = false;
                launchBtn.setText(R.string.launch);
                String msg = intent.getStringExtra("message");
                Toast.makeText(MainActivity.this,
                        msg != null ? msg : getString(R.string.start_failed), Toast.LENGTH_LONG).show();
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        extractContainer = findViewById(R.id.extract_container);
        mainContainer = findViewById(R.id.main_container);
        extractBar = findViewById(R.id.extract_bar);
        extractStatus = findViewById(R.id.extract_status);
        envStatus = findViewById(R.id.env_status);
        launchBtn = findViewById(R.id.launch_btn);
        Button resetBtn = findViewById(R.id.reset_btn);

        envStatus.setText(getString(R.string.env_ready, RootfsInstaller.bundledVersion(this)));
        launchBtn.setOnClickListener(v -> startTavern());
        resetBtn.setOnClickListener(v -> confirmReset());

        if (RootfsInstaller.isInstalled(this)) {
            showMain();
        } else {
            startExtraction();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        IntentFilter f = new IntentFilter();
        f.addAction(NodeService.ACTION_READY);
        f.addAction(NodeService.ACTION_FAILED);
        registerReceiver(serviceReceiver, f);
    }

    @Override
    protected void onPause() {
        super.onPause();
        unregisterReceiver(serviceReceiver);
    }

    private void showMain() {
        extractContainer.setVisibility(View.GONE);
        mainContainer.setVisibility(View.VISIBLE);
        launchBtn.setText(R.string.launch);
        launching = false;
        if ((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0) {
            // headless emulator testing: adb input injection is flaky
            new Handler(Looper.getMainLooper()).postDelayed(this::startTavern, 1500);
        }
    }

    private void startExtraction() {
        mainContainer.setVisibility(View.GONE);
        extractContainer.setVisibility(View.VISIBLE);
        extractBar.setIndeterminate(true);
        extractStatus.setText(getString(R.string.extract_phase, "解压中"));
        new Thread(() -> {
            try {
                RootfsInstaller.install(this, (entries, bytes) -> {
                    if (entries % 200 != 0) {
                        return; // throttle UI updates
                    }
                    ui.post(() -> extractStatus.setText(
                            getString(R.string.extract_count, entries)));
                });
                ui.post(this::showMain);
            } catch (IOException e) {
                android.util.Log.e("ST-Extract", "extract failed", e);
                ui.post(() -> {
                    extractStatus.setText(getString(R.string.extract_failed, e.getMessage()));
                    Toast.makeText(this, R.string.extract_failed_short, Toast.LENGTH_LONG).show();
                });
            }
        }, "st-extract").start();
    }

    private void startTavern() {
        if (launching) {
            return;
        }
        launching = true;
        launchBtn.setText(R.string.starting);
        Intent i = new Intent(this, NodeService.class).setAction(NodeService.ACTION_START);
        startForegroundService(i);
    }

    private void confirmReset() {
        new AlertDialog.Builder(this)
                .setTitle(R.string.reset_env)
                .setMessage(R.string.reset_confirm)
                .setPositiveButton(android.R.string.ok, (d, w) -> {
                    d.dismiss();
                    new Thread(() -> {
                        RootfsInstaller.deleteRecursively(RootfsInstaller.rootfsDir(this));
                        ui.post(this::startExtraction);
                    }, "st-reset").start();
                })
                .setNegativeButton(android.R.string.cancel, null)
                .show();
    }
}
