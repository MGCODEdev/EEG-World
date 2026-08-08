package at.eeg.trabocherstrasse.member.core

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.nio.ByteBuffer
import java.security.KeyStore
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class SecureStore(context: Context) {
    private val preferences = context.getSharedPreferences("eeg_secure_session_v2", Context.MODE_PRIVATE)
    private val keyAlias = "at.eeg.trabocherstrasse.session.aes"

    val deviceId: String
        get() = get("device_id") ?: "android-${UUID.randomUUID()}".also {
            put("device_id", it)
        }

    var accessToken: String?
        get() = get("access_token")
        set(value) { put("access_token", value) }
    var refreshToken: String?
        get() = get("refresh_token")
        set(value) { put("refresh_token", value) }
    var memberName: String?
        get() = get("member_name")
        set(value) { put("member_name", value) }
    var biometricLock: Boolean
        get() = get("biometric_lock") == "true"
        set(value) { put("biometric_lock", value.toString()) }

    fun clearSession() {
        preferences.edit().remove("access_token").remove("refresh_token").remove("member_name").remove("dashboard_cache").apply()
    }

    fun dashboardCache(): String? = get("dashboard_cache")
    fun setDashboardCache(value: String) { put("dashboard_cache", value) }

    private fun put(name: String, value: String?) {
        if (value == null) { preferences.edit().remove(name).apply(); return }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, encryptionKey())
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val combined = ByteBuffer.allocate(4 + cipher.iv.size + encrypted.size)
            .putInt(cipher.iv.size).put(cipher.iv).put(encrypted).array()
        preferences.edit().putString(name, Base64.encodeToString(combined, Base64.NO_WRAP)).apply()
    }

    private fun get(name: String): String? = preferences.getString(name, null)?.let { encoded ->
        runCatching {
            val buffer = ByteBuffer.wrap(Base64.decode(encoded, Base64.NO_WRAP))
            val iv = ByteArray(buffer.int).also { buffer.get(it) }
            val encrypted = ByteArray(buffer.remaining()).also { buffer.get(it) }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, encryptionKey(), GCMParameterSpec(128, iv))
            String(cipher.doFinal(encrypted), Charsets.UTF_8)
        }.getOrNull()
    }

    private fun encryptionKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(keyAlias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(
                KeyGenParameterSpec.Builder(
                    keyAlias,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build(),
            )
        }.generateKey()
    }
}
