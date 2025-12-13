# Add project specific ProGuard rules here.
-keepattributes *Annotation*

# Retrofit
-keepattributes Signature
-keepattributes Exceptions
-keep class retrofit2.** { *; }
-keepclasseswithmembers class * {
    @retrofit2.http.* <methods>;
}

# Kotlinx Serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** {
    *** Companion;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class me.zhaoqian.flyfun.**$$serializer { *; }
-keepclassmembers class me.zhaoqian.flyfun.** {
    *** Companion;
}
-keepclasseswithmembers class me.zhaoqian.flyfun.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**

# Google Maps
-keep class com.google.android.gms.maps.** { *; }
