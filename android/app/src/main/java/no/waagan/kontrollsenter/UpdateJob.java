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

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Bakgrunnssjekk ca. hvert 15. minutt (også når appen er lukket):
 *  - nye hendelser fra PC-ene (varm CPU, vifte stoppet, spilletid nådd, spilløkt ferdig …) → varsel
 *  - en PC som svarte forrige gang, men ikke nå (og ikke ble slått av med vilje) → varsel
 *  - ny app-versjon på NAS-en → varsel
 *  - widgeten oppdateres
 */
public class UpdateJob extends JobService {
    static final int JOB_ID = 1;
    static final String CH_UPDATE = "oppdatering";
    static final String CH_EVENTS = "hendelser";

    static void schedule(Context c) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js == null) return;
        JobInfo old = js.getPendingJob(JOB_ID);
        if (old != null && old.getIntervalMillis() <= 20 * 60 * 1000L) return;
        js.schedule(new JobInfo.Builder(JOB_ID, new ComponentName(c, UpdateJob.class))
                .setPeriodic(15 * 60 * 1000L)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPersisted(true)
                .build());
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        new Thread(() -> {
            try {
                checkPcs(this);
                check(this);
                KsWidget.refreshAll(this);
            } catch (Exception e) {
                // prøv igjen neste gang
            }
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

    /** Hendelser og «PC svarer ikke». */
    static void checkPcs(Context c) {
        SharedPreferences p = Net.prefs(c);
        JSONArray pcs = Net.pcs(c);
        String anyBase = null, anyName = null;
        java.util.List<JSONObject> down = new java.util.ArrayList<>();
        for (int i = 0; i < pcs.length(); i++) {
            JSONObject pc = pcs.optJSONObject(i);
            if (pc == null) continue;
            String name = pc.optString("name");
            String base = Net.reach(pc);
            String upKey = "up:" + name;
            if (base == null) {
                if (p.getBoolean(upKey, false)) down.add(pc);
                p.edit().putBoolean(upKey, false).apply();
                continue;
            }
            p.edit().putBoolean(upKey, true).apply();
            try {                                              // spiller noen? tilby levende varsel (trykk = start)
                JSONObject st = new JSONObject(Net.request(base + "/api/status", Net.token(c, name), null, 4000));
                String g = st.isNull("game") ? "" : st.optString("game", "");
                String key = "live_offer:" + name;
                if (!g.isEmpty() && !g.equals(p.getString(key, "")) && wants(c, "live")) {
                    p.edit().putString(key, g).apply();
                    NotificationManager nm = c.getSystemService(NotificationManager.class);
                    if (nm != null) {
                        channel(nm, CH_EVENTS, "Hendelser fra PC-ene", NotificationManager.IMPORTANCE_DEFAULT);
                        PendingIntent pi = Build.VERSION.SDK_INT >= 26
                                ? PendingIntent.getForegroundService(c, 11, new Intent(c, LiveService.class), PendingIntent.FLAG_IMMUTABLE)
                                : PendingIntent.getService(c, 11, new Intent(c, LiveService.class), PendingIntent.FLAG_IMMUTABLE);
                        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CH_EVENTS) : new Notification.Builder(c);
                        b.setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("🎮 " + name + " spiller " + g)
                                .setContentText("Trykk for live-status med FPS og temperatur").setContentIntent(pi).setAutoCancel(true);
                        try { nm.notify(5000 + Math.abs(name.hashCode() % 1000), b.build()); } catch (SecurityException e) { /* av */ }
                    }
                } else if (g.isEmpty()) {
                    p.edit().remove(key).apply();
                }
            } catch (Exception e) {
                // neste gang
            }
            anyBase = base;
            anyName = name;
            String tok = Net.token(c, name);
            if (tok.isEmpty()) continue;
            try {
                double since = Double.longBitsToDouble(p.getLong("ev:" + name, Double.doubleToLongBits(0)));
                if (since == 0) since = System.currentTimeMillis() / 1000.0;   // første gang: bare nye fra nå
                JSONObject r = new JSONObject(Net.request(base + "/api/x/events?since=" + since, tok, null, 5000));
                JSONArray evs = r.optJSONArray("events");
                double last = since;
                for (int k = 0; evs != null && k < evs.length(); k++) {
                    JSONObject e = evs.getJSONObject(k);
                    last = Math.max(last, e.optDouble("t", last));
                    String lvl = e.optString("level");
                    if (!"info".equals(lvl) && wants(c, e.optString("kind"))) {
                        notifyEvent(c, (int) (e.optDouble("t") % 100000), name + ": " + e.optString("title"),
                                e.optString("body"));
                    }
                }
                p.edit().putLong("ev:" + name, Double.doubleToLongBits(last)).apply();
            } catch (Exception e) {
                // PC-en svarte ikke på hendelser – prøv igjen neste gang
            }
        }
        // en PC som var på, svarer ikke lenger: ble den slått av med vilje? (statusen på NAS-en via en annen PC)
        for (JSONObject pc : down) {
            String name = pc.optString("name");
            boolean intended = false;
            if (anyBase != null) {
                try {
                    JSONObject r = new JSONObject(Net.request(anyBase + "/api/x/homepcs", Net.token(c, anyName), null, 8000));
                    JSONArray all = r.optJSONArray("pcs");
                    for (int k = 0; all != null && k < all.length(); k++) {
                        JSONObject s = all.getJSONObject(k);
                        if (name.equalsIgnoreCase(s.optString("name"))) intended = s.optBoolean("off", false);
                    }
                } catch (Exception e) {
                    // vet ikke – varsle forsiktig
                }
            } else {
                continue;   // ingen PC svarer (f.eks. borte uten Tailscale) – da vet vi ingenting
            }
            if (!intended && wants(c, "offline")) {
                notifyEvent(c, name.hashCode(), name + " svarer ikke",
                        "Den var på for litt siden, men ble ikke slått av fra Kontrollsenter. Strømbrudd eller krasj?");
            }
        }
    }

    /** Ny app-versjon. */
    static void check(Context c) {
        SharedPreferences p = Net.prefs(c);
        long have = installedCode(c);
        JSONArray pcs = Net.pcs(c);
        for (int i = 0; i < pcs.length(); i++) {
            JSONObject pc = pcs.optJSONObject(i);
            String base = pc == null ? null : Net.reach(pc);
            if (base == null) continue;
            try {
                JSONObject j = new JSONObject(Net.request(base + "/api/appupdate", null, null, 5000));
                long code = j.optLong("code", 0);
                if (code > have && code > p.getLong("varslet", 0) && wants(c, "appupdate")) {
                    notifyUpdate(c, j.optString("version", ""));
                    p.edit().putLong("varslet", code).apply();
                }
                return;
            } catch (Exception e) {
                // neste PC
            }
        }
    }

    /** Samme typer som på PC-en (background.KINDS), pluss «offline» og «appupdate» som bare finnes på telefonen. */
    static String kindOf(String key) {
        if (key == null) return "";
        if (key.equals("cpu") || key.equals("gpu")) return "temp";
        if (key.startsWith("disk")) return "disk";
        if (key.startsWith("bat")) return "battery";
        if (key.startsWith("full")) return "batfull";
        if (key.startsWith("smart") || key.startsWith("temprise")) return "health";
        if (key.equals("lanupdate") || key.equals("lanpublish") || key.equals("restart")) return "updates";
        if (key.equals("playlimit") || key.equals("bedtime")) return "playtime";
        return key;
    }

    /** Skal dette varselet vises? Hovedbryter + valg per type (Innstillinger → Varsler i appen). */
    static boolean wants(Context c, String key) {
        if ("watch".equals(key)) return true;
        SharedPreferences p = Net.prefs(c);
        if (!p.getBoolean("nf_all", true)) return false;
        return p.getBoolean("nf_" + kindOf(key), true);
    }

    static void channel(NotificationManager nm, String id, String name, int imp) {
        if (Build.VERSION.SDK_INT >= 26) nm.createNotificationChannel(new NotificationChannel(id, name, imp));
    }

    static void notifyEvent(Context c, int id, String title, String body) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null) return;
        channel(nm, CH_EVENTS, "Hendelser fra PC-ene", NotificationManager.IMPORTANCE_DEFAULT);
        Intent i = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CH_EVENTS) : new Notification.Builder(c);
        b.setSmallIcon(android.R.drawable.stat_notify_error).setContentTitle(title).setContentText(body)
                .setStyle(new Notification.BigTextStyle().bigText(body))
                .setContentIntent(PendingIntent.getActivity(c, 4, i, PendingIntent.FLAG_IMMUTABLE)).setAutoCancel(true);
        try {
            nm.notify(1000 + Math.abs(id % 50000), b.build());
        } catch (SecurityException e) {
            // varsler er slått av
        }
    }

    static void notifyUpdate(Context c, String version) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm == null) return;
        channel(nm, CH_UPDATE, "Oppdateringer", NotificationManager.IMPORTANCE_DEFAULT);
        Intent i = new Intent(c, MainActivity.class).setAction(MainActivity.ACTION_UPDATE)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, CH_UPDATE) : new Notification.Builder(c);
        b.setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setContentTitle("Kontrollsenter " + version + " er klar")
                .setContentText("Trykk for å oppdatere appen")
                .setContentIntent(PendingIntent.getActivity(c, 1, i,
                        PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE))
                .setAutoCancel(true);
        try {
            nm.notify(1, b.build());
        } catch (SecurityException e) {
            // varsler er slått av
        }
    }
}
