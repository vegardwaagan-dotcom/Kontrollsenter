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
    static final String ACTION_CLIP = "no.waagan.kontrollsenter.KLIPP";           // snarvei «Lagre klipp»
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
        // se etter ny app på GitHub med en gang appen starter (startsiden viser «Oppdatering klar»)
        new Thread(() -> { ghCache = new Bridge().fetchGithubLatest(); }, "github-sjekk").start();
        // bilder/filer i chatten og AI-en (<input type=file>) og mikrofonen til talemeldinger – bare egne sider
        web.setWebChromeClient(new android.webkit.WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, android.webkit.ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (fileCb != null) fileCb.onReceiveValue(null);
                fileCb = cb;
                try {
                    startActivityForResult(p.createIntent(), REQ_FILE);
                } catch (Exception e) {
                    fileCb = null;
                    return false;
                }
                return true;
            }

            // fullskjerm for video (klipp): legges over alt, liggende, uten system-linjer
            @Override
            public void onShowCustomView(View v, CustomViewCallback cb) {
                if (fsView != null) { cb.onCustomViewHidden(); return; }
                fsView = v;
                fsCb = cb;
                ((android.view.ViewGroup) getWindow().getDecorView()).addView(v, new android.widget.FrameLayout.LayoutParams(
                        android.view.ViewGroup.LayoutParams.MATCH_PARENT, android.view.ViewGroup.LayoutParams.MATCH_PARENT));
                setLandscape(true);
            }

            @Override
            public void onHideCustomView() {
                if (fsView == null) return;
                ((android.view.ViewGroup) getWindow().getDecorView()).removeView(fsView);
                fsView = null;
                if (fsCb != null) fsCb.onCustomViewHidden();
                fsCb = null;
                setLandscape(false);
            }

            @Override
            public void onPermissionRequest(android.webkit.PermissionRequest req) {
                runOnUiThread(() -> {
                    Uri o = req.getOrigin();
                    boolean mic = false;
                    for (String r : req.getResources()) {
                        if (android.webkit.PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) mic = true;
                    }
                    if (!mic || o == null || !isLocal(o.getHost())) {
                        req.deny();
                        return;
                    }
                    if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                        req.grant(new String[]{android.webkit.PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                    } else {
                        pendingMic = req;
                        requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                    }
                });
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                String sc = u.getScheme();
                // bare egne sider: startsiden i appen og Kontrollsenter på PC-er i hjemmenettet.
                // Andre nettsider (GitHub, driversiden, pakkesporing …) åpnes i telefonens nettleser.
                if ("https".equals(sc) && !isLocal(u.getHost())) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, u).addCategory(Intent.CATEGORY_BROWSABLE));
                    } catch (Exception ignored) { }
                    return true;
                }
                return !("file".equals(sc) || ("http".equals(sc) && isLocal(u.getHost())));
            }
        });
        // en lenke til en .apk (f.eks. «Last ned appen») installeres som oppdatering i stedet for å vises
        web.setDownloadListener((url, ua, cd, mime, len) -> {
            Uri u = Uri.parse(url);
            if ("http".equals(u.getScheme()) && isLocal(u.getHost())) installFrom(url);
        });
        takeShared(getIntent());
        if (ACTION_CLIP.equals(getIntent().getAction())) saveClip();
        if (saved != null) {
            web.restoreState(saved);
        } else {
            String room = getIntent().getStringExtra("chat_room");
            web.loadUrl(ACTION_UPDATE.equals(getIntent().getAction()) ? START + "?oppdater=1"
                    : room != null ? START + "#chat:" + android.net.Uri.encode(room) : START);
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

    /** Snarveien «Lagre klipp» (hold på app-ikonet, eller Google Assistant): lagre klipp på PC-en som sist ble brukt. */
    void saveClip() {
        new Thread(() -> {
            String msg;
            try {
                JSONObject r = Net.action(this, new JSONObject().put("a", "clip"));
                msg = r.optBoolean("ok") ? "🎬 Klipp lagret på PC-en" : r.optString("msg", "Feil");
            } catch (Exception e) {
                msg = "Kunne ikke lagre klipp: " + e.getMessage();
            }
            String m = msg;
            runOnUiThread(() -> android.widget.Toast.makeText(this, m, android.widget.Toast.LENGTH_LONG).show());
        }).start();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (ACTION_CLIP.equals(intent.getAction())) {
            saveClip();
            return;
        }
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
        } else if (intent.getStringExtra("chat_room") != null) {      // fra et chat-varsel: åpne samtalen
            String q = org.json.JSONObject.quote(intent.getStringExtra("chat_room"));
            web.evaluateJavascript("window.ksOpenChat && window.ksOpenChat(" + q + ")", null);
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

    /** GitHub-siden der hver versjon legges ut med appen (samme som PC-ene oppdaterer fra). */
    static final String GH_REPO = "vegardwaagan-dotcom/Kontrollsenter";
    volatile String ghCache = null;           // svaret fra GitHub-sjekken ved oppstart

    static boolean isGithub(Uri u) {
        String h = u.getHost();
        return "https".equals(u.getScheme()) && h != null
                && (h.equals("github.com") || h.equals("api.github.com") || h.endsWith(".githubusercontent.com"));
    }

    void installFrom(String url) {
        Uri u = Uri.parse(url);
        boolean gh = isGithub(u) && u.getPath() != null && u.getPath().startsWith("/" + GH_REPO + "/releases/download/")
                && u.getPath().endsWith(".apk");
        if (!gh && (!"http".equals(u.getScheme()) || !isLocal(u.getHost()))) {
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
                status(gh ? "Laster ned fra GitHub …" : "Laster ned oppdateringen …");
                con = (HttpURLConnection) new URL(url).openConnection();
                con.setInstanceFollowRedirects(true);          // GitHub sender videre til nedlastingsserveren (https)
                con.setRequestProperty("User-Agent", "Kontrollsenter-app");
                con.setConnectTimeout(gh ? 15000 : 5000);
                con.setReadTimeout(60000);
                if (con.getResponseCode() != 200) {
                    throw new IOException((gh ? "GitHub" : "PC-en") + " svarte " + con.getResponseCode());
                }
                if (gh && !isGithub(Uri.parse(con.getURL().toString()))) throw new IOException("ukjent nedlastingsadresse");
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

    /** Liquid Glass / Aero: appen blir gjennomsiktig og viser bakgrunnsbildet bak seg (uskarpt på Android 12+). */
    boolean glassOn = false;
    int glassBlur = 0;

    void setGlassWindow(boolean on, int blur) {
        glassOn = on;
        glassBlur = Math.max(0, Math.min(150, blur));
        android.view.Window w = getWindow();
        if (Build.VERSION.SDK_INT >= 30) setTranslucent(on);   // uskarphet bak krever et gjennomsiktig vindu
        if (on) {
            w.addFlags(WindowManager.LayoutParams.FLAG_SHOW_WALLPAPER);
            w.setBackgroundDrawable(new android.graphics.drawable.ColorDrawable(Color.TRANSPARENT));
            root.setBackgroundColor(Color.TRANSPARENT);
            web.setBackgroundColor(Color.TRANSPARENT);
            if (Build.VERSION.SDK_INT >= 31) w.setBackgroundBlurRadius(glassBlur);
        } else {
            w.clearFlags(WindowManager.LayoutParams.FLAG_SHOW_WALLPAPER);
            if (Build.VERSION.SDK_INT >= 31) w.setBackgroundBlurRadius(0);
            applyTheme();
        }
    }

    private void applyTheme() {
        boolean dark = night();
        int bg = dark ? Color.rgb(0x1e, 0x1e, 0x24) : Color.rgb(0xf4, 0xf4, 0xf7);
        if (glassOn) bg = Color.TRANSPARENT;
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
        recRelease();                   // en talemelding som tas opp, avbrytes – mikrofonen holdes ikke i bakgrunnen
        super.onPause();
    }

    /** Mikrofon-/søkeknappen på TV-fjernkontrollen: talekommando til PC-en («spillmodus på», «middag» …). */
    @Override
    public boolean onKeyDown(int keyCode, android.view.KeyEvent event) {
        if (keyCode == android.view.KeyEvent.KEYCODE_SEARCH || keyCode == android.view.KeyEvent.KEYCODE_VOICE_ASSIST
                || keyCode == android.view.KeyEvent.KEYCODE_ASSIST) {
            String url = web.getUrl();
            if (url != null && url.startsWith("http")) {
                web.evaluateJavascript("window.ksVoiceKey && window.ksVoiceKey()", null);
                return true;
            }
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (fsView != null) {                                 // tilbake: ut av fullskjerm først
            if (fsCb != null) fsCb.onCustomViewHidden();
            ((android.view.ViewGroup) getWindow().getDecorView()).removeView(fsView);
            fsView = null;
            fsCb = null;
            setLandscape(false);
            return;
        }
        String url = web.getUrl();
        if (url != null && url.startsWith("http")) {
            // lukk først det som ligger oppå (velger, «Se på», søk) – ellers tilbake til PC-listen
            web.evaluateJavascript("(window.ksBack && window.ksBack()) ? 1 : 0", (r) -> {
                if (!"1".equals(r)) web.loadUrl(START + "?hjem=1");
            });
        } else if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    /** Tilgjengelig for sidene som window.KS – bare ufarlige funksjoner. */
    static final int REQ_FILE = 7, REQ_MIC = 8, REQ_LISTEN = 9, REQ_REC = 10;
    /** Talemelding i chatten: sidene lastes over http fra PC-en, og der finnes ikke navigator.mediaDevices –
     *  derfor tar appen opp selv (AAC i .m4a) og gir sidene lyden som base64. */
    android.media.MediaRecorder recorder;
    java.io.File recFile;

    synchronized void recRelease() {
        if (recorder != null) {
            try { recorder.release(); } catch (Exception ignored) { }
            recorder = null;
        }
    }
    View fsView;
    android.webkit.WebChromeClient.CustomViewCallback fsCb;

    /** Liggende fullskjerm (video) av/på. */
    void setLandscape(boolean on) {
        setRequestedOrientation(on ? android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                : android.content.pm.ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED);
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                if (on) {
                    c.hide(WindowInsets.Type.systemBars());
                    c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
                } else {
                    c.show(WindowInsets.Type.systemBars());
                }
            }
        }
    }


    android.webkit.ValueCallback<Uri[]> fileCb;
    android.webkit.PermissionRequest pendingMic;
    android.speech.tts.TextToSpeech tts;
    android.speech.SpeechRecognizer recognizer;
    String listenLang = "nb-NO";

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == REQ_FILE && fileCb != null) {
            fileCb.onReceiveValue(android.webkit.WebChromeClient.FileChooserParams.parseResult(res, data));
            fileCb = null;
        }
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] perms, int[] res) {
        super.onRequestPermissionsResult(req, perms, res);
        boolean ok = res.length > 0 && res[0] == PackageManager.PERMISSION_GRANTED;
        if (req == REQ_MIC && pendingMic != null) {
            if (ok) pendingMic.grant(new String[]{android.webkit.PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            else pendingMic.deny();
            pendingMic = null;
        } else if (req == REQ_LISTEN) {
            if (ok) startListen(); else heard("", "Appen fikk ikke bruke mikrofonen");
        } else if (req == REQ_REC) {
            final String js = "window.ksRecPermission && window.ksRecPermission(" + ok + ")";
            runOnUiThread(() -> web.evaluateJavascript(js, null));
        }
    }

    void heard(String text, String err) {
        String js = "window.ksHeard && window.ksHeard(" + JSONObject.quote(text == null ? "" : text) + ","
                + (err == null ? "null" : JSONObject.quote(err)) + ")";
        runOnUiThread(() -> web.evaluateJavascript(js, null));
    }

    void startListen() {
        if (!android.speech.SpeechRecognizer.isRecognitionAvailable(this)) {
            heard("", "Talegjenkjenning finnes ikke på denne telefonen");
            return;
        }
        if (recognizer != null) recognizer.destroy();
        recognizer = android.speech.SpeechRecognizer.createSpeechRecognizer(this);
        recognizer.setRecognitionListener(new android.speech.RecognitionListener() {
            public void onReadyForSpeech(Bundle b) { }
            public void onBeginningOfSpeech() { }
            public void onRmsChanged(float v) { }
            public void onBufferReceived(byte[] b) { }
            public void onEndOfSpeech() { }
            public void onError(int e) {
                heard("", e == android.speech.SpeechRecognizer.ERROR_NO_MATCH
                        || e == android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT ? "Hørte ingenting – prøv igjen"
                        : "Talegjenkjenningen feilet (" + e + ")");
            }
            public void onResults(Bundle b) {
                java.util.ArrayList<String> r = b.getStringArrayList(android.speech.SpeechRecognizer.RESULTS_RECOGNITION);
                heard(r != null && !r.isEmpty() ? r.get(0) : "", r == null || r.isEmpty() ? "Hørte ingenting" : null);
            }
            public void onPartialResults(Bundle b) { }
            public void onEvent(int t, Bundle b) { }
        });
        Intent i = new Intent(android.speech.RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        i.putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                android.speech.RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        i.putExtra(android.speech.RecognizerIntent.EXTRA_LANGUAGE, listenLang);
        recognizer.startListening(i);
    }

    class Bridge {
        /** Start opptak av en talemelding. Svar: "ok", "perm" (spør om tillatelse – prøv igjen etterpå) eller "feil". */
        @JavascriptInterface
        public String recStart() {
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                runOnUiThread(() -> requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_REC));
                return "perm";
            }
            synchronized (MainActivity.this) {
                recRelease();
                try {
                    recFile = new java.io.File(getCacheDir(), "tale.m4a");
                    android.media.MediaRecorder r = Build.VERSION.SDK_INT >= 31
                            ? new android.media.MediaRecorder(MainActivity.this) : new android.media.MediaRecorder();
                    recorder = r;
                    r.setAudioSource(android.media.MediaRecorder.AudioSource.MIC);
                    r.setOutputFormat(android.media.MediaRecorder.OutputFormat.MPEG_4);
                    r.setAudioEncoder(android.media.MediaRecorder.AudioEncoder.AAC);
                    r.setAudioEncodingBitRate(64000);
                    r.setAudioSamplingRate(44100);
                    r.setOutputFile(recFile.getAbsolutePath());
                    r.prepare();
                    r.start();
                    return "ok";
                } catch (Exception e) {
                    recRelease();
                    return "feil";
                }
            }
        }

        /** Lydnivået siden forrige kall (0–32767) – til nivåmåleren mens du snakker. */
        @JavascriptInterface
        public int recLevel() {
            synchronized (MainActivity.this) {
                try {
                    return recorder != null ? recorder.getMaxAmplitude() : 0;
                } catch (Exception e) {
                    return 0;
                }
            }
        }

        /** Stopp opptaket. keep = true: lyden (m4a) som base64, ellers "" (avbrutt eller for kort). */
        @JavascriptInterface
        public String recStop(boolean keep) {
            synchronized (MainActivity.this) {
                if (recorder == null) return "";
                try {
                    recorder.stop();
                } catch (Exception e) {
                    keep = false;                                  // for kort opptak: stop() kaster
                }
                recRelease();
                java.io.File f = recFile;
                recFile = null;
                if (f == null) return "";
                try {
                    if (!keep) return "";
                    byte[] b = java.nio.file.Files.readAllBytes(f.toPath());
                    return android.util.Base64.encodeToString(b, android.util.Base64.NO_WRAP);
                } catch (Exception e) {
                    return "";
                } finally {
                    f.delete();
                }
            }
        }

        /** Snakk inn tekst (AI og chat): telefonens egen talegjenkjenning. Svaret kommer i window.ksHeard(tekst). */
        @JavascriptInterface
        public void listen(String lang) {
            if (lang != null && lang.matches("[a-zA-Z-]{2,10}")) listenLang = lang;
            runOnUiThread(() -> {
                if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_LISTEN);
                } else {
                    startListen();
                }
            });
        }

        /** Kjører appen på en TV (Google TV / Android TV)? Da får sidene større tekst og tydelig fokus for fjernkontrollen. */
        @JavascriptInterface
        public boolean isTv() {
            android.app.UiModeManager um = (android.app.UiModeManager) getSystemService(UI_MODE_SERVICE);
            return um != null && um.getCurrentModeType() == Configuration.UI_MODE_TYPE_TELEVISION;
        }

        /** Liggende visning av/på (fullskjerm-video når nettsiden ikke klarer å låse retningen selv). */
        @JavascriptInterface
        public void landscape(boolean on) {
            runOnUiThread(() -> setLandscape(on));
        }

        /** Les opp et svar (telefonens talesyntese, norsk om den finnes). */
        @JavascriptInterface
        public void speak(String text) {
            if (text == null) return;
            String t = text.length() > 3500 ? text.substring(0, 3500) : text;
            runOnUiThread(() -> {
                if (tts == null) {
                    tts = new android.speech.tts.TextToSpeech(MainActivity.this, st -> {
                        if (st == android.speech.tts.TextToSpeech.SUCCESS) {
                            tts.setLanguage(new java.util.Locale("nb", "NO"));
                            tts.speak(t, android.speech.tts.TextToSpeech.QUEUE_FLUSH, null, "ks");
                        }
                    });
                } else {
                    tts.speak(t, android.speech.tts.TextToSpeech.QUEUE_FLUSH, null, "ks");
                }
            });
        }

        @JavascriptInterface
        public void stopSpeak() {
            runOnUiThread(() -> { if (tts != null) tts.stop(); });
        }

        /** «Bruk mobilen som webkamera»: kamera-skjermen sender bildene til PC-en siden er hentet fra. */
        @JavascriptInterface
        public void camera(String token) {
            runOnUiThread(() -> {
                Uri u = Uri.parse(web.getUrl() == null ? "" : web.getUrl());
                if (u.getScheme() == null || !u.getScheme().startsWith("http") || u.getHost() == null) return;
                String base = u.getScheme() + "://" + u.getHost() + (u.getPort() > 0 ? ":" + u.getPort() : "");
                android.content.Intent i = new android.content.Intent(MainActivity.this, CamActivity.class);
                i.putExtra("base", base);
                i.putExtra("token", token);
                startActivity(i);
            });
        }

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

        /** Last ned et klipp/bilde fra PC-en til telefonen (Nedlastinger) – kan deles derfra. */
        @JavascriptInterface
        public void download(String url, String name) {
            Uri u = Uri.parse(url);
            if (!"http".equals(u.getScheme()) || !isLocal(u.getHost())) return;
            String safe = name == null ? "klipp.mp4" : name.replaceAll("[\\\\/:*?\"<>|]", "_");
            android.app.DownloadManager.Request r = new android.app.DownloadManager.Request(u)
                    .setTitle(safe).setDescription("Kontrollsenter")
                    .setNotificationVisibility(android.app.DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                    .setDestinationInExternalPublicDir(android.os.Environment.DIRECTORY_DOWNLOADS, "Kontrollsenter/" + safe);
            android.app.DownloadManager dm = getSystemService(android.app.DownloadManager.class);
            if (dm != null) dm.enqueue(r);
        }

        /** Del et skjermbilde/klipp fra PC-en: hent det til telefonen og åpne Androids delemeny. */
        @JavascriptInterface
        public void share(String url, String name) {
            Uri u = Uri.parse(url);
            if (!"http".equals(u.getScheme()) || !isLocal(u.getHost())) return;
            String safe = (name == null || name.isEmpty() ? "klipp.mp4" : name).replaceAll("[\\\\/:*?\"<>|]", "_");
            if (safe.startsWith(".")) safe = "_" + safe;
            String fname = safe;
            new Thread(() -> {
                try {
                    java.io.File dir = ShareProvider.dir(MainActivity.this);
                    java.io.File[] old = dir.listFiles();               // rydd bort det som ble delt før
                    if (old != null) for (java.io.File f : old) if (System.currentTimeMillis() - f.lastModified() > 3600_000L) f.delete();
                    java.io.File out = new java.io.File(dir, fname);
                    HttpURLConnection c = (HttpURLConnection) new java.net.URL(url).openConnection();
                    c.setConnectTimeout(8000);
                    c.setReadTimeout(30000);
                    if (c.getResponseCode() != 200) throw new IOException("PC-en svarte " + c.getResponseCode());
                    try (InputStream in = c.getInputStream(); OutputStream o = new java.io.FileOutputStream(out)) {
                        byte[] b = new byte[65536];
                        int n;
                        while ((n = in.read(b)) > 0) o.write(b, 0, n);
                    }
                    Uri cu = new Uri.Builder().scheme("content").authority(ShareProvider.AUTH).appendPath(fname).build();
                    Intent send = new Intent(Intent.ACTION_SEND)
                            .setType(ShareProvider.mime(fname))
                            .putExtra(Intent.EXTRA_STREAM, cu)
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    send.setClipData(android.content.ClipData.newRawUri(fname, cu));
                    Intent ch = Intent.createChooser(send, "Del " + fname).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                    runOnUiThread(() -> {
                        web.evaluateJavascript("window.ksShareReady && window.ksShareReady()", null);
                        startActivity(ch);
                    });
                } catch (Exception e) {
                    String m = "Kunne ikke dele: " + e.getMessage();
                    runOnUiThread(() -> android.widget.Toast.makeText(MainActivity.this, m, android.widget.Toast.LENGTH_LONG).show());
                }
            }).start();
        }

        /** Åpne en annen app (Moonlight, RustDesk). Mangler den: åpne Google Play. */
        @JavascriptInterface
        public boolean openApp(String pkg) {
            if (pkg == null || !pkg.matches("[a-zA-Z0-9_.]{3,100}")) return false;
            Intent i = getPackageManager().getLaunchIntentForPackage(pkg);
            try {
                if (i != null) {
                    i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                    startActivity(i);
                    return true;
                }
                startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + pkg))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            } catch (Exception e) {
                startActivity(new Intent(Intent.ACTION_VIEW,
                        Uri.parse("https://play.google.com/store/apps/details?id=" + pkg))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            }
            return false;
        }

        @JavascriptInterface
        public boolean hasApp(String pkg) {
            return pkg != null && getPackageManager().getLaunchIntentForPackage(pkg) != null;
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
            if ((u.getPort() == 27100 && "/api/apk".equals(u.getPath())) || isGithub(u)) {
                runOnUiThread(() -> installFrom(url));
            }
        }

        /** Siste GitHub-sjekk fra oppstart (bakgrunnstråd) – svarer med en gang: JSON, eller "" hvis ikke ferdig. */
        @JavascriptInterface
        public String githubCached() {
            return ghCache != null ? ghCache : "";
        }

        /** Nyeste app på GitHub: {"version","code","url"} eller {"error"}. Kjøres på JS-broens egen tråd. */
        @JavascriptInterface
        public String githubLatest() {
            return fetchGithubLatest();
        }
        String fetchGithubLatest() {
            HttpURLConnection con = null;
            JSONObject out = new JSONObject();
            try {
                con = (HttpURLConnection) new URL("https://api.github.com/repos/" + GH_REPO + "/releases/latest")
                        .openConnection();
                con.setRequestProperty("User-Agent", "Kontrollsenter-app");
                con.setRequestProperty("Accept", "application/vnd.github+json");
                con.setConnectTimeout(10000);
                con.setReadTimeout(15000);
                if (con.getResponseCode() != 200) throw new IOException("GitHub svarte " + con.getResponseCode());
                StringBuilder sb = new StringBuilder();
                try (InputStream in = con.getInputStream()) {
                    byte[] buf = new byte[8192];
                    int n;
                    while ((n = in.read(buf)) > 0) sb.append(new String(buf, 0, n, "UTF-8"));
                }
                JSONObject j = new JSONObject(sb.toString());
                String ver = j.optString("tag_name", "").replaceFirst("^v", "");
                String[] p = (ver + ".0.0").split("\\.");
                long code = Long.parseLong(p[0]) * 10000 + Long.parseLong(p[1]) * 100 + Long.parseLong(p[2]);
                JSONArray as = j.optJSONArray("assets");
                String apk = null;
                for (int i = 0; as != null && i < as.length(); i++) {
                    String n = as.getJSONObject(i).optString("name");
                    if (n.endsWith(".apk")) apk = as.getJSONObject(i).optString("browser_download_url");
                }
                if (apk == null) throw new IOException("ingen app i siste versjon på GitHub");
                out.put("version", ver).put("code", code).put("url", apk);
            } catch (Exception e) {
                try { out.put("error", e.getMessage()); } catch (Exception ignored) { }
            } finally {
                if (con != null) con.disconnect();
            }
            return out.toString();
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

        /** Start det levende varselet (spillet, FPS, temperaturer) – appen kaller dette når et spill kjører. */
        @JavascriptInterface
        public void startLive() {
            try {
                LiveService.start(MainActivity.this);
            } catch (Exception e) {
                // ikke tillatt akkurat nå (f.eks. varsler er slått av)
            }
        }

        /** Åpne en https-lenke i riktig app (f.eks. en Discord-kanal i Discord-appen). */
        @JavascriptInterface
        public void openUrl(String url) {
            if (url == null || !(url.startsWith("https://") || url.startsWith("ntfy://"))) return;
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                } catch (Exception e) {
                    // ingen app kan åpne lenken
                }
            });
        }

        /** Scenene som snarveier på app-ikonet (hold inne) – og for Google Assistant / Bixby-rutiner. */
        @JavascriptInterface
        public void setScenes(String json) {
            try {
                android.content.pm.ShortcutManager sm = getSystemService(android.content.pm.ShortcutManager.class);
                if (sm == null) return;
                org.json.JSONArray a = new org.json.JSONArray(json);
                java.util.List<android.content.pm.ShortcutInfo> list = new java.util.ArrayList<>();
                int max = Math.min(a.length(), Math.max(0, sm.getMaxShortcutCountPerActivity() - 6));
                for (int i = 0; i < max; i++) {
                    org.json.JSONObject s = a.getJSONObject(i);
                    String id = s.optString("id"), name = s.optString("name");
                    if (!id.matches("[\\w-]{1,40}") || name.isEmpty()) continue;
                    Intent it = new Intent("no.waagan.kontrollsenter.SCENE")
                            .setClass(MainActivity.this, QuickAction.class).putExtra("id", id).putExtra("name", name);
                    list.add(new android.content.pm.ShortcutInfo.Builder(MainActivity.this, "scene-" + id)
                            .setShortLabel((s.optString("icon", "") + " " + name).trim())
                            .setLongLabel("Scene: " + name)
                            .setIcon(android.graphics.drawable.Icon.createWithResource(MainActivity.this, R.mipmap.ic_launcher))
                            .setIntent(it).build());
                }
                sm.setDynamicShortcuts(list);
            } catch (Exception e) {
                // ikke støttet på denne telefonen
            }
        }

        /** Fargetema (Nordlys, Synthwave …) – samme på startskjermen og for alle PC-ene. */
        @JavascriptInterface
        public String getLook() {
            return getSharedPreferences("ks", 0).getString("look", "");
        }

        @JavascriptInterface
        public void setLook(String name) {
            if (name == null || !name.matches("[a-z]{1,20}")) return;
            getSharedPreferences("ks", 0).edit().putString("look", name).apply();
        }

        /** Liquid Glass / Aero-valgene (JSON), felles for startskjermen og alle PC-ene. */
        @JavascriptInterface
        public String getAero() {
            return getSharedPreferences("ks", 0).getString("aero", "");
        }

        @JavascriptInterface
        public void setAero(String json) {
            if (json == null || json.length() > 300) return;
            getSharedPreferences("ks", 0).edit().putString("aero", json).apply();
        }

        @JavascriptInterface
        public void setGlassWindow(boolean on, int blur) {
            runOnUiThread(() -> MainActivity.this.setGlassWindow(on, blur));
        }

        /** Design: «klassisk», «ny», «3d» eller «lett» – felles for startskjermen og alle PC-ene. */
        @JavascriptInterface
        public String getDesign() {
            return getSharedPreferences("ks", 0).getString("design", "");
        }

        @JavascriptInterface
        public void setDesign(String name) {
            if (!"klassisk".equals(name) && !"ny".equals(name) && !"3d".equals(name) && !"lett".equals(name)) return;
            getSharedPreferences("ks", 0).edit().putString("design", name).apply();
        }

        @JavascriptInterface
        public String getLookColors() {
            return getSharedPreferences("ks", 0).getString("look_colors", "");
        }

        @JavascriptInterface
        public void setLookColors(String json) {
            if (json == null || json.length() > 200) return;
            getSharedPreferences("ks", 0).edit().putString("look_colors", json).apply();
        }

        /** Varselvalg på denne telefonen: JSON {"all":true,"temp":false,...} (mangler = på). */
        @JavascriptInterface
        public String getNotify() {
            JSONObject o = new JSONObject();
            try {
                for (java.util.Map.Entry<String, ?> e : getSharedPreferences("ks", 0).getAll().entrySet()) {
                    if (e.getKey().startsWith("nf_") && e.getValue() instanceof Boolean)
                        o.put(e.getKey().substring(3), e.getValue());
                }
            } catch (Exception e) {
                // tomt = alt på
            }
            return o.toString();
        }

        @JavascriptInterface
        public void setNotify(String kind, boolean on) {
            if (kind == null || !kind.matches("[a-z]{1,20}")) return;
            getSharedPreferences("ks", 0).edit().putBoolean("nf_" + kind, on).apply();
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
