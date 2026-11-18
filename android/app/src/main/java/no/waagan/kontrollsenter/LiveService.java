package no.waagan.kontrollsenter;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONObject;

/** Levende varsel mens du spiller: spillet, FPS, temperaturer og spilletid – også på låseskjermen.
 *  Oppdateres hvert 5. sekund og stopper av seg selv når spillet avsluttes. */
public class LiveService extends Service {
    static final String CH = "live";
    static final int ID = 4242;
    static final String STOP = "no.waagan.kontrollsenter.LIVE_STOP";
    static final String CLIP = "no.waagan.kontrollsenter.LIVE_CLIP";
    private volatile boolean run = false;

    static void start(Context c) {
        Intent i = new Intent(c, LiveService.class);
        if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i); else c.startService(i);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String a = intent == null ? null : intent.getAction();
        if (STOP.equals(a)) {
            run = false;
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        if (CLIP.equals(a)) {
            new Thread(() -> {
                try { Net.action(this, new JSONObject().put("a", "clip")); } catch (Exception e) { /* neste gang */ }
            }).start();
            return START_NOT_STICKY;
        }
        Notification n = build("Kontrollsenter", "Henter status fra PC-en …");
        if (Build.VERSION.SDK_INT >= 34) startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else startForeground(ID, n);
        if (!run) {
            run = true;
            new Thread(this::loop).start();
        }
        return START_NOT_STICKY;
    }

    private void loop() {
        int idle = 0;
        NotificationManager nm = getSystemService(NotificationManager.class);
        while (run) {
            try {
                JSONObject s = Net.status(this);
                String game = s.isNull("game") ? "" : s.optString("game", "");
                if (game.isEmpty()) {
                    if (++idle >= 3) break;                    // spillet er avsluttet
                } else {
                    idle = 0;
                    JSONObject cpu = s.optJSONObject("cpu"), gpu = s.optJSONObject("gpu");
                    StringBuilder b = new StringBuilder();
                    if (!s.isNull("fps") && s.has("fps")) b.append(s.optInt("fps")).append(" FPS · ");
                    if (cpu != null && !cpu.isNull("temp")) b.append("CPU ").append(Math.round(cpu.optDouble("temp"))).append("° · ");
                    if (gpu != null && !gpu.isNull("temp")) b.append("GPU ").append(Math.round(gpu.optDouble("temp"))).append("° · ");
                    JSONObject info = s.optJSONObject("info");
                    if (info != null && info.has("play_s")) {
                        int sec = info.optInt("play_s");
                        b.append("spilt i dag ").append(sec / 3600).append(" t ").append(sec % 3600 / 60).append(" min");
                    }
                    if (nm != null) nm.notify(ID, build("🎮 " + game, b.toString()));
                }
            } catch (Exception e) {
                if (++idle >= 6) break;                        // PC-en svarer ikke
            }
            try { Thread.sleep(5000); } catch (InterruptedException e) { break; }
        }
        run = false;
        stopForeground(true);
        stopSelf();
    }

    private Notification build(String title, String text) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26 && nm != null)
            nm.createNotificationChannel(new NotificationChannel(CH, "Mens du spiller (live)", NotificationManager.IMPORTANCE_LOW));
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent po = PendingIntent.getActivity(this, 7, open, PendingIntent.FLAG_IMMUTABLE);
        PendingIntent clip = PendingIntent.getService(this, 8, new Intent(this, LiveService.class).setAction(CLIP),
                PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getService(this, 9, new Intent(this, LiveService.class).setAction(STOP),
                PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CH) : new Notification.Builder(this);
        b.setSmallIcon(android.R.drawable.ic_media_play).setContentTitle(title).setContentText(text)
                .setOngoing(true).setOnlyAlertOnce(true).setContentIntent(po)
                .setVisibility(Notification.VISIBILITY_PUBLIC).setCategory(Notification.CATEGORY_STATUS)
                .addAction(new Notification.Action.Builder(null, "🎬 Lagre klipp", clip).build())
                .addAction(new Notification.Action.Builder(null, "Stopp", stop).build());
        return b.build();
    }

    @Override
    public void onDestroy() {
        run = false;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) { return null; }
}
