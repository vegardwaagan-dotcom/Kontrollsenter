package no.waagan.kontrollsenter;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.os.Build;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Sjekker i bakgrunnen (ca. hver 6. time, bare på Wi-Fi) om PC-ene har en nyere app fra NAS-en,
 * og gir et varsel. PC-ene appen kjenner, lagres av startsiden (KS.rememberHosts).
 */
public class UpdateJob extends JobService {
    static final int JOB_ID = 1;
    static final String CHANNEL = "oppdatering";

    static void schedule(Context c) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js == null || js.getPendingJob(JOB_ID) != null) return;
        JobInfo ji = new JobInfo.Builder(JOB_ID, new ComponentName(c, UpdateJob.class))
                .setPeriodic(6 * 3600 * 1000L)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_UNMETERED)
                .setPersisted(true)
                .build();
        js.schedule(ji);
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            check(this);
            jobFinished(params, false);
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        return true;
    }

    static long installedCode(Context c) {
        try {
            PackageInfo pi = c.getPackageManager().getPackageInfo(c.getPackageName(), 0);
            return Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    /** Spør PC-ene etter nyeste app; varsler én gang per ny versjon. */
    static void check(Context c) {
        SharedPreferences p = c.getSharedPreferences("ks", 0);
        String hosts = p.getString("hosts", "");
        long have = installedCode(c);
        for (String host : hosts.split(",")) {
            host = host.trim();
            if (host.isEmpty() || !MainActivity.isLocal(host)) continue;
            try {
                JSONObject j = new JSONObject(get("http://" + host + ":27100/api/appupdate"));
                long code = j.optLong("code", 0);
                if (code > have) {
                    if (code > p.getLong("varslet", 0)) {
                        notify(c, j.optString("version", ""));
                        p.edit().putLong("varslet", code).apply();
                    }
                    return;
                }
                return;                         // PC-en svarte og appen er oppdatert
            } catch (Exception e) {
                // prøv neste PC
            }
        }
    }

    static String get(String url) throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        con.setConnectTimeout(4000);
        con.setReadTimeout(8000);
        try (InputStream in = con.getInputStream(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) > 0 && out.size() < 65536) out.write(buf, 0, n);
            return out.toString("UTF-8");
        } finally {
            con.disconnect();
        }
    }

    static void notify(Context c, String version) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null) return;
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Oppdateringer",
                    NotificationManager.IMPORTANCE_DEFAULT));
        }
        Intent i = new Intent(c, MainActivity.class).setAction(MainActivity.ACTION_UPDATE)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent pi = PendingIntent.getActivity(c, 1, i,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CHANNEL)
                : new Notification.Builder(c);
        b.setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle("Kontrollsenter " + version + " er klar")
                .setContentText("Trykk for å oppdatere appen")
                .setContentIntent(pi)
                .setAutoCancel(true);
        try {
            nm.notify(1, b.build());
        } catch (SecurityException e) {
            // varsler er slått av – banneret i appen sier fra i stedet
        }
    }
}
