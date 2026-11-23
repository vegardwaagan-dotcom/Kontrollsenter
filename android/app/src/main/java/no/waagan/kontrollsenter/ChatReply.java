package no.waagan.kontrollsenter;

import android.app.Notification;
import android.app.NotificationManager;
import android.app.RemoteInput;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;

import org.json.JSONObject;

/** «Svar» rett fra chat-varselet (29): sender svaret til PC-en og oppdaterer varselet. */
public class ChatReply extends BroadcastReceiver {
    static final String KEY = "svar";

    @Override
    public void onReceive(Context c, Intent i) {
        Bundle r = RemoteInput.getResultsFromIntent(i);
        if (r == null) return;
        CharSequence txt = r.getCharSequence(KEY);
        String room = i.getStringExtra("room");
        int id = i.getIntExtra("id", 0);
        String pc = i.getStringExtra("pc");
        if (txt == null || txt.length() == 0 || room == null) return;
        PendingResult pr = goAsync();
        new Thread(() -> {
            String status;
            try {
                if (pc != null) Net.prefs(c).edit().putString("active", pc).apply();
                Net.action(c, new JSONObject().put("a", "chat2").put("room", room).put("text", txt.toString()));
                status = "✓ Sendt: " + txt;
            } catch (Exception e) {
                status = "✗ Kom ikke fram: " + e.getMessage();
            }
            NotificationManager nm = c.getSystemService(NotificationManager.class);
            if (nm != null) {
                Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(c, UpdateJob.CH_CHAT)
                        : new Notification.Builder(c);
                b.setSmallIcon(android.R.drawable.stat_notify_chat).setContentText(status).setTimeoutAfter(4000);
                try {
                    nm.notify(id, b.build());
                } catch (SecurityException e) {
                    // varsler er av
                }
            }
            pr.finish();
        }).start();
    }
}
