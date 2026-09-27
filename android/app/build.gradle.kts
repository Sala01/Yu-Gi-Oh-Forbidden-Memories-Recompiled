plugins {
    id("com.android.application")
}

android {
    namespace = "org.unchiga.yfmrecomp"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.unchiga.yfmrecomp"
        minSdk = 21
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.2"
        ndk {
            abiFilters.add("arm64-v8a")
        }
    }

    sourceSets {
        getByName("main") {
            jniLibs.srcDirs("src/main/jniLibs")
        }
    }

    packaging {
        jniLibs.useLegacyPackaging = true
    }

    lint {
        abortOnError = false
    }
}

dependencies {
    implementation(fileTree(mapOf("dir" to "libs", "include" to listOf("*.jar"))))
}
