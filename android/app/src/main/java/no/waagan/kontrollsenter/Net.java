package no.waagan.kontrollsenter;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Felles HTTP mot Kontrollsenter på PC-ene (for varsler, widget og hurtigfliser – også når appen er lukket). */
final class Net {
    private Net() {
    }

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("ks", 0);
    }

    static String token(Context c, String pc) {
        return c.getSharedPreferences("ks_tokens", 0).getString(pc == null ? "" : pc, "");
    }

    /** PC-ene appen kjenner: [{name, host, ts, mac}] (lagret av startsiden). */
    static JSONArray pcs(Context c) {
        try {
            return new JSONArray(prefs(c).getString("pcs", "[]"));
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    /** PC-en som sist ble åpnet: {name, base} der base er f.eks. «http://192.168.1.53:27100». */
    static JSONObject active(Context c) {
        try {
            return new JSONObject(prefs(c).getString("active", "{}"));
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    static String request(String url, String token, String body, int timeoutMs) throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        con.setConnectTimeout(timeoutMs);
        con.setReadTimeout(timeoutMs * 3);
        if (token != null && !token.isEmpty()) con.setRequestProperty("Authorization", "Bearer " + token);
        if (body != null) {
            con.setDoOutput(true);
            con.setRequestMethod("POST");
            con.setRequestProperty("Content-Type", "application/json");
            try (OutputStream o = con.getOutputStream()) {
                o.write(body.getBytes(StandardCharsets.UTF_8));
            }
        }
        try {
            int code = con.getResponseCode();
            InputStream in = code < 400 ? con.getInputStream() : con.getErrorStream();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            if (in != null) {
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) > 0 && out.size() < 2_000_000) out.write(buf, 0, n);
                in.close();
            }
            if (code >= 400) throw new Exception("PC-en svarte " + code);
            return out.toString("UTF-8");
        } finally {
            con.disconnect();
        }
    }

    /** Første adresse som svarer for en PC (hjemme, ellers Tailscale). */
    static String reach(JSONObject pc) {
        for (String k : new String[]{"host", "ts", "tsname"}) {
            String h = pc.optString(k, "");
            if (h.isEmpty() || !MainActivity.isLocal(h)) continue;
            try {
                String r = request("http://" + h + ":27100/api/hello", null, null, k.equals("host") ? 1500 : 4000);
                if (r.contains("Kontrollsenter")) return "http://" + h + ":27100";
            } catch (Exception e) {
                // prøv neste adresse
            }
        }
        return null;
    }

    /** Kommando til PC-en som sist ble brukt (fra hurtigflis/widget). Returnerer svaret eller kaster. */
    static JSONObject action(Context c, JSONObject body) throws Exception {
        JSONObject a = active(c);
        String name = a.optString("name");
        String base = a.optString("base");
        JSONObject pc = findPc(c, name);
        if (pc != null) {
            String b = reach(pc);
            if (b != null) base = b;
        }
        if (base.isEmpty()) throw new Exception("åpne appen og velg en PC først");
        return new JSONObject(request(base + "/api/action", token(c, name), body.toString(), 4000));
    }

    static JSONObject status(Context c) throws Exception {
        JSONObject a = active(c);
        String name = a.optString("name");
        String base = a.optString("base");
        JSONObject pc = findPc(c, name);
        if (pc != null) {
            String b = reach(pc);
            if (b != null) base = b;
        }
        if (base.isEmpty()) throw new Exception("ingen PC valgt");
        return new JSONObject(request(base + "/api/status", token(c, name), null, 4000));
    }

    /** Alt widgetene viser (én henting for alle widgetene). */
    static JSONObject widgets(Context c) throws Exception {
        JSONObject a = active(c);
        String name = a.optString("name");
        String base = a.optString("base");
        JSONObject pc = findPc(c, name);
        if (pc != null) {
            String b = reach(pc);
            if (b != null) base = b;
        }
        if (base.isEmpty()) throw new Exception("åpne appen og velg en PC først");
        return new JSONObject(request(base + "/api/widgets", token(c, name), null, 4000));
    }

    static JSONObject findPc(Context c, String name) {
        JSONArray a = pcs(c);
        for (int i = 0; i < a.length(); i++) {
            JSONObject p = a.optJSONObject(i);
            if (p != null && name != null && name.equals(p.optString("name"))) return p;
        }
        return null;
    }
}
