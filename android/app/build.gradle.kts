import java.util.Properties

plugins {
    id("com.android.application")
}

// Samme versjon som Kontrollsenter på PC-en (VERSION i hovedmappen), f.eks. 0.7.0 -> versionCode 700
val ver = rootProject.file("../VERSION").readText().trim()
val code = ver.split(".").map { it.toInt() }.let { it[0] * 10000 + it.getOrElse(1) { 0 } * 100 + it.getOrElse(2) { 0 } }

// Samme signeringsnøkkel som bygg-android.sh (~/.local/share/kontrollsenter-android) – da kan appen fra
// Android Studio installeres over appen fra NAS-en, og omvendt.
val keyDir = File(System.getProperty("user.home"), ".local/share/kontrollsenter-android")
val keyFile = File(keyDir, "kontrollsenter.jks")
val keyPass = File(keyDir, "passord").takeIf { it.exists() }?.readText()?.trim()

android {
    namespace = "no.waagan.kontrollsenter"
    compileSdk = 35

    defaultConfig {
        applicationId = "no.waagan.kontrollsenter"
        minSdk = 26
        targetSdk = 35
        versionCode = code
        versionName = ver
    }

    signingConfigs {
        if (keyFile.exists() && keyPass != null) {
            create("kontrollsenter") {
                storeFile = keyFile
                storePassword = keyPass
                keyAlias = "kontrollsenter"
                keyPassword = keyPass
            }
        }
    }

    buildTypes {
        val sc = signingConfigs.findByName("kontrollsenter")
        getByName("debug") {
            if (sc != null) signingConfig = sc
        }
        getByName("release") {
            isMinifyEnabled = false
            if (sc != null) signingConfig = sc
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
