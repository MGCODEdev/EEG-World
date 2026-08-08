package at.eeg.trabocherstrasse.member.push

import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.Context
import androidx.core.app.NotificationCompat
import at.eeg.trabocherstrasse.member.BuildConfig
import at.eeg.trabocherstrasse.member.EEGApplication
import at.eeg.trabocherstrasse.member.MainActivity
import at.eeg.trabocherstrasse.member.R
import at.eeg.trabocherstrasse.member.core.DeviceRegistration
import at.eeg.trabocherstrasse.member.core.DeviceRegistrationResponse
import at.eeg.trabocherstrasse.member.core.SessionManager
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await

class EEGFirebaseMessagingService : FirebaseMessagingService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        scope.launch { runCatching { registerToken((application as EEGApplication).session, token) } }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val title = message.notification?.title ?: message.data["title"] ?: "EEG Trabocherstraße"
        val body = message.notification?.body ?: message.data["body"] ?: return
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("route", message.data["route"])
            putExtra("message_id", message.data["message_id"])
        }
        val pendingIntent = PendingIntent.getActivity(
            this, message.data["message_id"]?.toIntOrNull() ?: 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, "eeg_messages")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setContentTitle(title).setContentText(body).setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pendingIntent).setAutoCancel(true).setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        getSystemService(NotificationManager::class.java).notify(message.data["message_id"]?.toIntOrNull() ?: body.hashCode(), notification)
    }
}

suspend fun registerCurrentDeviceForPush(context: Context, session: SessionManager) {
    if (FirebaseApp.getApps(context).isEmpty()) return
    val token = FirebaseMessaging.getInstance().token.await()
    registerToken(session, token)
}

private suspend fun registerToken(session: SessionManager, token: String) {
    session.send<DeviceRegistrationResponse, DeviceRegistration>(
        "devices/current", "PUT",
        DeviceRegistration(token, appVersion = BuildConfig.VERSION_NAME),
    )
}
