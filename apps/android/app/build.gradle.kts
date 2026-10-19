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
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "SOURCE_SHA", "\"$sourceSha\"")
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
        informational += setOf("GradleDependency", "AndroidGradlePluginVersion")
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

    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.test)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.junit)
}
