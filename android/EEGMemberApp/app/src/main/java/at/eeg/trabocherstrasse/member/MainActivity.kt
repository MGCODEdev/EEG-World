package at.eeg.trabocherstrasse.member

import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.fragment.app.FragmentActivity
import at.eeg.trabocherstrasse.member.ui.EEGApp

class MainActivity : FragmentActivity() {
    private var incomingLink: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        incomingLink = intent?.dataString
        setContent {
            EEGApp(
                session = (application as EEGApplication).session,
                initialLink = incomingLink,
                initialMessageId = intent?.getStringExtra("message_id")?.toIntOrNull(),
                consumeLink = { incomingLink = null },
            )
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        incomingLink = intent.dataString
        recreate()
    }
}
