package at.eeg.trabocherstrasse.member

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import at.eeg.trabocherstrasse.member.core.ApiClient
import at.eeg.trabocherstrasse.member.core.SecureStore
import at.eeg.trabocherstrasse.member.core.SessionManager
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions

class EEGApplication : Application() {
    lateinit var session: SessionManager
        private set

    override fun onCreate() {
        super.onCreate()
        val store = SecureStore(this)
        session = SessionManager(ApiClient(store.deviceId), store)
        configureFirebase()
        createNotificationChannel()
    }

    private fun configureFirebase() {
        if (BuildConfig.FIREBASE_APP_ID.isBlank() || BuildConfig.FIREBASE_PROJECT_ID.isBlank() ||
            BuildConfig.FIREBASE_API_KEY.isBlank() || BuildConfig.FIREBASE_SENDER_ID.isBlank() ||
            FirebaseApp.getApps(this).isNotEmpty()) return
        FirebaseApp.initializeApp(
            this,
            FirebaseOptions.Builder()
                .setApplicationId(BuildConfig.FIREBASE_APP_ID)
                .setProjectId(BuildConfig.FIREBASE_PROJECT_ID)
                .setApiKey(BuildConfig.FIREBASE_API_KEY)
                .setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID)
                .build(),
        )
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val sound = Uri.parse("android.resource://$packageName/raw/eeg_notification")
        val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).build()
        val channel = NotificationChannel(
            "eeg_messages", "EEG-Nachrichten", NotificationManager.IMPORTANCE_HIGH,
        ).apply {
            description = "Abrechnungen und wichtige Mitteilungen der EEG"
            enableVibration(true)
            setSound(sound, attributes)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }
}
