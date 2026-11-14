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

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
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
                status("Oppdateringen feilet: " + (msg != null ? msg : ("kode " + st)));
            }
        } else if (ACTION_UPDATE.equals(intent.getAction())) {
            web.loadUrl(START + "?oppdater=1");
        }
    }

    /** Melding til siden som vises (window.ksUpdateStatus) – f.eks. «Laster ned …». */
    void status(String msg) {
        String q = JSONObject.quote(msg);
        runOnUiThread(() -> web.evaluateJavascript("window.ksUpdateStatus && window.ksUpdateStatus(" + q + ")",
                null));
    }

    /** Last ned APK-en fra en PC på hjemmenettet og installer den med Android sitt eget installasjonsprogram.
     *  Android godtar bare en oppdatering som er signert med samme nøkkel som appen. */
    void installFrom(String url) {
        Uri u = Uri.parse(url);
        if (!"http".equals(u.getScheme()) || !isLocal(u.getHost())) {
            status("Ugyldig adresse");
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
                if (Build.VERSION.SDK_INT >= 31) {
                    sp.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
                }
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
        if (host.endsWith(".local") || host.equals("localhost") || !host.contains(".")) return true;
        return host.matches("^(10\\.|192\\.168\\.|172\\.(1[6-9]|2\\d|3[01])\\.|127\\.)[\\d.]+$");
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

        /** IPv4-adressen og nettmasken på Wi-Fi/Ethernet, f.eks. «192.168.1.23/24». */
        @JavascriptInterface
        public String subnet() {
            try {
                ConnectivityManager cm = getSystemService(ConnectivityManager.class);
                Network n = cm.getActiveNetwork();
                LinkProperties lp = n == null ? null : cm.getLinkProperties(n);
                if (lp == null) return "";
                for (LinkAddress la : lp.getLinkAddresses()) {
                    InetAddress a = la.getAddress();
                    if (a instanceof Inet4Address && !a.isLoopbackAddress()) {
                        return a.getHostAddress() + "/" + la.getPrefixLength();
                    }
                }
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
