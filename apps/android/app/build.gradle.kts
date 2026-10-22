plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

val sourceSha = providers.gradleProperty("sourceSha").orElse("local").get()
require(sourceSha == "local" || sourceSha.matches(Regex("[0-9a-f]{40}")))

android {
    namespace = "com.prettylisavpn.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.prettylisavpn.android"
        minSdk = 26
        targetSdk = 36
        versionCode = 15
        versionName = "0.8.0"
        testInstrumentationRunner = "com.prettylisavpn.android.AcceptanceRunner"
        buildConfigField("String", "SOURCE_SHA", "\"$sourceSha\"")
    }
    // Public development key only. Never use this identity for release signing.
    signingConfigs {
        getByName("debug") {
            storeFile = rootProject.file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }
    buildTypes {
        debug {
            applicationIdSuffix = ".dev"
        }
        release {
            // Signing/release distribution are a separate task.
            isMinifyEnabled = false
        }
    }
    bundle { language { enableSplit = false } } // All six locales work offline, including future AAB installs.
    buildFeatures {
        compose = true
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    lint {
        warningsAsErrors = true
        checkDependencies = false
        // Keep online update notices visible without making a pinned build time-dependent.
        // API compatibility, resource and security warnings still fail CI.
        informational += setOf("GradleDependency", "AndroidGradlePluginVersion", "NewerVersionAvailable")
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.icons)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)
    debugImplementation(libs.androidx.compose.tooling)

    implementation(libs.okhttp.core)
    implementation(libs.gson)
    implementation("com.wireguard.android:tunnel:1.0.20260102")

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)

    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.test)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.espresso)
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.3.0")
}
