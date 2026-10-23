plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}
android {
    namespace = "com.prettylisavpn.engine"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.prettylisavpn.engine"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }
    signingConfigs {
        getByName("debug") {
            storeFile = rootProject.file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }
    buildTypes {
        debug { applicationIdSuffix = ".dev" }
        release { isMinifyEnabled = false }
    }
    buildFeatures { aidl = true; buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    lint {
        warningsAsErrors = true
        informational += setOf("GradleDependency", "AndroidGradlePluginVersion", "NewerVersionAvailable")
    }
}
dependencies {
    // Built from ../../engines/managed, never linked into the main :app APK.
    implementation(files("libs/managed.aar"))
}
