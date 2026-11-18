package no.waagan.kontrollsenter;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Toast;

import org.json.JSONObject;

/** Usynlig: utfører en snarvei (spillmodus, demp, middag, lås PC) mot PC-en og lukker seg. Brukes av
 *  snarveiene på app-ikonet og kan legges på hjemskjermen eller i Bixby/rutiner. */
public class QuickAction extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        Intent i = getIntent();
        String a = i == null ? "" : String.valueOf(i.getAction());
        new Thread(() -> {
            String msg;
            try {
                JSONObject body;
                switch (a) {
                    case "no.waagan.kontrollsenter.SPILLMODUS": {
                        boolean on = !Net.status(this).optBoolean("gamemode");
                        body = new JSONObject().put("a", "gamemode").put("on", on);
                        msg = "Spillmodus " + (on ? "på" : "av");
                        break;
                    }
                    case "no.waagan.kontrollsenter.DEMP": {
                        boolean mute = !Net.widgets(this).optBoolean("mute");
                        body = new JSONObject().put("a", "volume").put("mute", mute);
                        msg = mute ? "Lyden på PC-en er dempet" : "Lyden på PC-en er på";
                        break;
                    }
                    case "no.waagan.kontrollsenter.MIDDAG":
                        body = new JSONObject().put("a", "dinner");
                        msg = "🍽️ «Middag!» er sendt";
                        break;
                    case "no.waagan.kontrollsenter.LAAS":
                        body = new JSONObject().put("a", "system").put("do", "lock");
                        msg = "PC-en er låst";
                        break;
                    default:
                        body = null;
                        msg = "";
                }
                if (body != null) Net.action(this, body);
            } catch (Exception e) {
                msg = "PC-en svarer ikke: " + e.getMessage();
            }
            final String m = msg;
            runOnUiThread(() -> {
                if (!m.isEmpty()) Toast.makeText(this, m, Toast.LENGTH_SHORT).show();
                finish();
            });
        }).start();
    }
}
