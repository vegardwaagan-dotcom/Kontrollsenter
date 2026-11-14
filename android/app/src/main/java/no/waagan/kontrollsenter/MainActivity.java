package no.waagan.kontrollsenter;

import android.Manifest;
import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.ConnectivityManager;
import android.net.LinkAddress;
import android.net.LinkProperties;
import android.net.Network;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.hardware.biometrics.BiometricPrompt;
import android.os.CancellationSignal;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.URL;

/**
 * Kontrollsenter for Android: startsiden (assets/start.html) finner PC-ene med Kontrollsenter på hjemmenettet,
 * og kontrollpanelet lastes fra PC-en selv (http://PC:27100/app/) – så appen får nye funksjoner hver gang
 * Kontrollsenter på PC-en oppdateres.
 */
public class MainActivity extends Activity {
    static final String START = "file:///android_asset/start.html";
    static final String ACTION_UPDATE = "no.waagan.kontrollsenter.OPPDATER";     // fra varselet
    static final String ACTION_INSTALL = "no.waagan.kontrollsenter.INSTALLER";   // svar fra PackageInstaller
    private WebView web;
    private FrameLayout root;
    private String sharedText;                       // tekst/lenke delt fra en annen app («Del» → Kontrollsenter)

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        root = new FrameLayout(this);
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);

        // Kant til kant (Android 15): hold innholdet unna statuslinjen, navigasjonen, kamerahullet og tastaturet
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            root.setOnApplyWindowInsetsListener((v, ins) -> {
                Insets i = ins.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()
                        | WindowInsets.Type.ime());
                v.setPadding(i.left, i.top, i.right, i.bottom);
                return WindowInsets.CONSUMED;
            });
        }
        applyTheme();

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setBuiltInZoomControls(false);
        s.setSupportZoom(false);
        web.addJavascriptInterface(new Bridge(), "KS");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                String sc = u.getScheme();
                // bare egne sider: startsiden i appen og Kontrollsenter på PC-er i hjemmenettet
                return !("file".equals(sc) || ("http".equals(sc) && isLocal(u.getHost())));
            }
        });
        // en lenke til en .apk (f.eks. «Last ned appen») installeres som oppdatering i stedet for å vises
        web.setDownloadListener((url, ua, cd, mime, len) -> {
            Uri u = Uri.parse(url);
            if ("http".equals(u.getScheme()) && isLocal(u.getHost())) installFrom(url);
        });
        takeShared(getIntent());
        if (saved != null) {
            web.restoreState(saved);
        } else {
            web.loadUrl(ACTION_UPDATE.equals(getIntent().getAction()) ? START + "?oppdater=1" : START);
        }
        // varsel om nye app-versjoner (Android 13+ spør om lov én gang)
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }
        UpdateJob.schedule(this);
    }

    /** «Del» fra en annen app: ta vare på teksten og vis den i «Send til PC-en». */
    private boolean takeShared(Intent i) {
        if (i != null && Intent.ACTION_SEND.equals(i.getAction())) {
            String t = i.getStringExtra(Intent.EXTRA_TEXT);
            if (t != null && !t.isEmpty()) {
                sharedText = t.length() > 100000 ? t.substring(0, 100000) : t;
                return true;
            }
        }
        return false;
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (takeShared(intent)) {
            String q = JSONObject.quote(sharedText);
            web.evaluateJavascript("window.ksShared ? window.ksShared(" + q + ") : 0", null);
            return;
        }
        if (ACTION_INSTALL.equals(intent.getAction())) {
            int st = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -999);
            if (st == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                @SuppressWarnings("deprecation")
                Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirm != null) startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                status("Bekreft oppdateringen …");
            } else if (st == PackageInstaller.STATUS_SUCCESS) {
                status("Oppdatert ✓");
            } else {
                String msg = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
                String low = msg == null ? "" : msg.toLowerCase();
                if (low.contains("self update") || low.contains("blocked")) {
                    // nyere Android (f.eks. Samsung) lar ikke en app fra «ukjent kilde» oppdatere seg selv –
                    // da lastes den ned i nettleseren i stedet (vanlig, tillatt installasjon), også neste gang
                    getSharedPreferences("ks", 0).edit().putBoolean("via_nettleser", true).apply();
                    if (lastUrl != null) {
                        openInBrowser(lastUrl);
                        return;
                    }
                }
                status("Oppdateringen feilet: " + (msg != null ? msg : ("kode " + st)));
            }
        } else if (ACTION_UPDATE.equals(intent.getAction())) {
            web.loadUrl(START + "?oppdater=1");
        }
    }

    void bio(boolean ok) {
        web.evaluateJavascript("window.ksBio && window.ksBio(" + ok + ")", null);
    }

    /** Melding til siden som vises (window.ksUpdateStatus) – f.eks. «Laster ned …». */
    void status(String msg) {
        String q = JSONObject.quote(msg);
        runOnUiThread(() -> web.evaluateJavascript("window.ksUpdateStatus && window.ksUpdateStatus(" + q + ")",
                null));
    }

    /** Last ned APK-en fra en PC på hjemmenettet og installer den med Android sitt eget installasjonsprogram.
     *  Android godtar bare en oppdatering som er signert med samme nøkkel som appen. */
    private String lastUrl;

    /** Åpne APK-en i nettleseren: den lastes ned og installeres med Android sitt installasjonsprogram. */
    void openInBrowser(String url) {
        status("Android lar ikke appen oppdatere seg selv – åpner nedlastingen i nettleseren. Trykk på "
                + "Kontrollsenter.apk når den er lastet ned, og velg Oppdater.");
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url))
                    .addCategory(Intent.CATEGORY_BROWSABLE).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch (Exception e) {
            status("Åpne " + url + " i nettleseren for å laste ned oppdateringen");
        }
    }

    void installFrom(String url) {
        Uri u = Uri.parse(url);
        if (!"http".equals(u.getScheme()) || !isLocal(u.getHost())) {
            status("Ugyldig adresse");
            return;
        }
        lastUrl = url;
        if (getSharedPreferences("ks", 0).getBoolean("via_nettleser", false)) {
            openInBrowser(url);
            return;
        }
        if (Build.VERSION.SDK_INT >= 26 && !getPackageManager().canRequestPackageInstalls()) {
            status("Gi Kontrollsenter lov til å installere oppdateringer, og trykk «Oppdater» igjen");
            startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getPackageName())));
            return;
        }
        new Thread(() -> {
            HttpURLConnection con = null;
            try {
                status("Laster ned oppdateringen …");
                con = (HttpURLConnection) new URL(url).openConnection();
                con.setConnectTimeout(5000);
                con.setReadTimeout(60000);
                if (con.getResponseCode() != 200) throw new IOException("PC-en svarte " + con.getResponseCode());
                PackageInstaller pi = getPackageManager().getPackageInstaller();
                PackageInstaller.SessionParams sp =
                        new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                sp.setAppPackageName(getPackageName());
                int id = pi.createSession(sp);
                try (PackageInstaller.Session session = pi.openSession(id)) {
                    try (InputStream in = con.getInputStream();
                         OutputStream out = session.openWrite("Kontrollsenter.apk", 0, con.getContentLengthLong())) {
                        byte[] buf = new byte[65536];
                        int n;
                        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
                        session.fsync(out);
                    }
                    Intent i = new Intent(this, MainActivity.class).setAction(ACTION_INSTALL);
                    int fl = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                    session.commit(PendingIntent.getActivity(this, 2, i, fl).getIntentSender());
                }
                status("Installerer …");
            } catch (Exception e) {
                status("Oppdateringen feilet: " + e.getMessage());
            } finally {
                if (con != null) con.disconnect();
            }
        }).start();
    }

    static boolean isLocal(String host) {
        if (host == null) return false;
        if (host.endsWith(".local") || host.endsWith(".ts.net") || host.equals("localhost") || !host.contains(".")) {
            return true;
        }
        // hjemmenett, eller Tailscale (100.64.0.0/10 – bare dine egne enheter)
        return host.matches("^(10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[01])\\.|127\\.|100\\.(6[4-9]|[7-9]\\d|1[01]\\d|12[0-7])\\.)[\\d.]+$");
    }

    private boolean night() {
        return (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK)
                == Configuration.UI_MODE_NIGHT_YES;
    }

    private void applyTheme() {
        boolean dark = night();
        int bg = dark ? Color.rgb(0x1e, 0x1e, 0x24) : Color.rgb(0xf4, 0xf4, 0xf7);
        root.setBackgroundColor(bg);
        web.setBackgroundColor(bg);
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                int light = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS
                        | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                c.setSystemBarsAppearance(dark ? 0 : light, light);
            }
        } else {
            getWindow().setStatusBarColor(bg);
            getWindow().setNavigationBarColor(bg);
            if (!dark) {
                getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
            }
        }
    }

    @Override
    public void onConfigurationChanged(Configuration c) {
        super.onConfigurationChanged(c);
        applyTheme();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        web.resumeTimers();
    }

    @Override
    protected void onPause() {
        web.onPause();                  // ingen henting i bakgrunnen – sparer batteri
        web.pauseTimers();
        super.onPause();
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        String url = web.getUrl();
        if (url != null && url.startsWith("http")) {
            web.loadUrl(START + "?hjem=1");          // fra en PC: tilbake til PC-listen
        } else if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    /** Tilgjengelig for sidene som window.KS – bare ufarlige funksjoner. */
    class Bridge {
        @JavascriptInterface
        public void home() {
            runOnUiThread(() -> web.loadUrl(START + "?hjem=1"));
        }

        /** IPv4-adressen og nettmasken på Wi-Fi/Ethernet, f.eks. «192.168.1.23/24». Hopper over VPN (f.eks.
         *  Tailscale, 100.x) – ellers søker appen i feil nett når VPN-en er på. */
        @JavascriptInterface
        public String subnet() {
            try {
                ConnectivityManager cm = getSystemService(ConnectivityManager.class);
                String fallback = "";
                for (Network n : cm.getAllNetworks()) {
                    android.net.NetworkCapabilities nc = cm.getNetworkCapabilities(n);
                    LinkProperties lp = cm.getLinkProperties(n);
                    if (nc == null || lp == null || nc.hasTransport(android.net.NetworkCapabilities.TRANSPORT_VPN)) continue;
                    boolean lan = nc.hasTransport(android.net.NetworkCapabilities.TRANSPORT_WIFI)
                            || nc.hasTransport(android.net.NetworkCapabilities.TRANSPORT_ETHERNET);
                    for (LinkAddress la : lp.getLinkAddresses()) {
                        InetAddress a = la.getAddress();
                        if (a instanceof Inet4Address && !a.isLoopbackAddress() && a.isSiteLocalAddress()) {
                            String v = a.getHostAddress() + "/" + la.getPrefixLength();
                            if (lan) return v;
                            if (fallback.isEmpty()) fallback = v;
                        }
                    }
                }
                return fallback;
            } catch (Exception e) {
                // ingen nettverkstilgang – siden lar deg skrive inn adressen selv
            }
            return "";
        }

        /** Navnet på enheten (f.eks. «Galaxy Tab S11 Ultra») – brukes som forslag ved paring. */
        @JavascriptInterface
        public String model() {
            String n = null;
            try {
                n = Settings.Global.getString(getContentResolver(), "device_name");
            } catch (Exception e) {
                // bruk modellnavnet
            }
            return (n != null && !n.isEmpty()) ? n : (Build.MANUFACTURER + " " + Build.MODEL);
        }

        @JavascriptInterface
        public void keepAwake(boolean on) {
            runOnUiThread(() -> {
                if (on) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            });
        }

        /** Fingeravtrykk/ansikt (eller PIN) før farlige handlinger. Svar: window.ksBio(true|false). */
        @JavascriptInterface
        public void authenticate(String reason) {
            runOnUiThread(() -> {
                if (Build.VERSION.SDK_INT < 28) {
                    bio(true);
                    return;
                }
                BiometricPrompt.Builder b = new BiometricPrompt.Builder(MainActivity.this)
                        .setTitle("Kontrollsenter").setSubtitle(reason == null ? "Bekreft" : reason);
                if (Build.VERSION.SDK_INT >= 30) {
                    b.setAllowedAuthenticators(android.hardware.biometrics.BiometricManager.Authenticators.BIOMETRIC_WEAK
                            | android.hardware.biometrics.BiometricManager.Authenticators.DEVICE_CREDENTIAL);
                } else if (Build.VERSION.SDK_INT >= 29) {
                    b.setDeviceCredentialAllowed(true);
                } else {
                    b.setNegativeButton("Avbryt", getMainExecutor(), (d, w) -> bio(false));
                }
                try {
                    b.build().authenticate(new CancellationSignal(), getMainExecutor(),
                            new BiometricPrompt.AuthenticationCallback() {
                                @Override
                                public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult r) {
                                    bio(true);
                                }

                                @Override
                                public void onAuthenticationError(int code, CharSequence msg) {
                                    bio(false);
                                }
                            });
                } catch (Exception e) {
                    bio(true);                 // ingen skjermlås satt opp – ikke stopp brukeren
                }
            });
        }

        @JavascriptInterface
        public String sharedText() {
            String t = sharedText;
            sharedText = null;
            return t == null ? "" : t;
        }

        /** Wake-on-LAN fra telefonen (når den er på samme nett som PC-en). */
        @JavascriptInterface
        public void wol(String mac) {
            new Thread(() -> {
                try {
                    String hex = mac.replaceAll("[^0-9A-Fa-f]", "");
                    if (hex.length() != 12) return;
                    byte[] m = new byte[6];
                    for (int i = 0; i < 6; i++) m[i] = (byte) Integer.parseInt(hex.substring(i * 2, i * 2 + 2), 16);
                    byte[] pkt = new byte[102];
                    for (int i = 0; i < 6; i++) pkt[i] = (byte) 0xff;
                    for (int i = 6; i < 102; i++) pkt[i] = m[(i - 6) % 6];
                    java.util.List<InetAddress> targets = new java.util.ArrayList<>();
                    targets.add(InetAddress.getByName("255.255.255.255"));
                    String sn = new Bridge().subnet();
                    if (sn.contains("/")) {
                        byte[] ip = InetAddress.getByName(sn.split("/")[0]).getAddress();
                        int pre = Integer.parseInt(sn.split("/")[1]);
                        int v = ((ip[0] & 255) << 24) | ((ip[1] & 255) << 16) | ((ip[2] & 255) << 8) | (ip[3] & 255);
                        int bc = v | (pre >= 32 ? 0 : (int) ((1L << (32 - pre)) - 1));
                        targets.add(InetAddress.getByAddress(new byte[]{(byte) (bc >>> 24), (byte) (bc >>> 16),
                                (byte) (bc >>> 8), (byte) bc}));
                    }
                    try (DatagramSocket ds = new DatagramSocket()) {
                        ds.setBroadcast(true);
                        for (InetAddress t : targets) {
                            for (int port : new int[]{9, 7}) ds.send(new DatagramPacket(pkt, pkt.length, t, port));
                        }
                    }
                } catch (Exception e) {
                    // ikke på hjemmenettet – startsiden ber en annen PC sende i stedet
                }
            }).start();
        }

        /** PC-en som er åpen nå – brukes av widgeten og hurtigflisene. */
        @JavascriptInterface
        public void setActive(String name, String base) {
            try {
                Uri u = Uri.parse(base);
                if (!"http".equals(u.getScheme()) || !isLocal(u.getHost())) return;
                Net.prefs(MainActivity.this).edit()
                        .putString("active", new JSONObject().put("name", name).put("base", base).toString()).apply();
            } catch (Exception e) {
                // ugyldig – behold den gamle
            }
        }

        /** Alle PC-ene appen kjenner ([{name, host, ts, tsname, mac}]) – for varsler, widget og fliser. */
        @JavascriptInterface
        public void rememberPcs(String json) {
            try {
                JSONArray in = new JSONArray(json);
                JSONArray out = new JSONArray();
                for (int i = 0; i < in.length() && i < 20; i++) {
                    JSONObject p = in.getJSONObject(i);
                    JSONObject q = new JSONObject().put("name", p.optString("name"));
                    for (String k : new String[]{"host", "ts", "tsname"}) {
                        String h = p.optString(k, "");
                        if (!h.isEmpty() && isLocal(h)) q.put(k, h);
                    }
                    q.put("mac", p.optString("mac", ""));
                    out.put(q);
                }
                Net.prefs(MainActivity.this).edit().putString("pcs", out.toString()).apply();
            } catch (Exception e) {
                // ugyldig liste
            }
        }

        @JavascriptInterface
        public long versionCode() {
            return UpdateJob.installedCode(MainActivity.this);
        }

        /** Last ned og installer en ny app-versjon fra en PC (bare http://<hjemmenett>:27100/api/apk). */
        @JavascriptInterface
        public void update(String url) {
            Uri u = Uri.parse(url);
            if (u.getPort() == 27100 && "/api/apk".equals(u.getPath())) {
                runOnUiThread(() -> installFrom(url));
            }
        }

        /** Nøkkelen fra paringen, lagret per PC (samme nøkkel hjemme og via Tailscale). */
        @JavascriptInterface
        public String getToken(String pc) {
            return getSharedPreferences("ks_tokens", 0).getString(pc, "");
        }

        @JavascriptInterface
        public void setToken(String pc, String token) {
            if (pc == null || pc.isEmpty()) return;
            getSharedPreferences("ks_tokens", 0).edit().putString(pc, token == null ? "" : token).apply();
        }

        /** PC-ene startsiden kjenner (JSON-liste med adresser) – brukes av bakgrunnssjekken. */
        @JavascriptInterface
        public void rememberHosts(String json) {
            try {
                JSONArray a = new JSONArray(json);
                StringBuilder sb = new StringBuilder();
                for (int i = 0; i < a.length() && i < 20; i++) {
                    String h = a.getString(i);
                    if (isLocal(h)) sb.append(sb.length() > 0 ? "," : "").append(h);
                }
                getSharedPreferences("ks", 0).edit().putString("hosts", sb.toString()).apply();
            } catch (Exception e) {
                // ugyldig liste – behold den gamle
            }
        }

        @JavascriptInterface
        public String version() {
            try {
                return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
            } catch (Exception e) {
                return "";
            }
        }
    }
}
