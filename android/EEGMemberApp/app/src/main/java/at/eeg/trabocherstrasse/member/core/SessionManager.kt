package at.eeg.trabocherstrasse.member.core

import android.os.Build
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.net.URI
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

sealed interface SessionState {
    data object Restoring : SessionState
    data object SignedOut : SessionState
    data class SignedIn(val memberName: String) : SessionState
}

class SessionManager(@PublishedApi internal val api: ApiClient, private val store: SecureStore) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val refreshMutex = Mutex()
    private val cacheJson = Json { ignoreUnknownKeys = true }
    private val _state = MutableStateFlow<SessionState>(SessionState.Restoring)
    val state: StateFlow<SessionState> = _state.asStateFlow()

    init { scope.launch { restore() } }

    suspend fun login(username: String, password: String) {
        val response: LoginResponse = api.send(
            "auth/login", "POST",
            LoginRequest(username.trim(), password, store.deviceId, deviceName()),
        )
        store(response)
    }

    suspend fun requestLink(email: String): String {
        val response: LinkResponse = api.send("auth/link/request", "POST", LinkRequest(email.trim()))
        return response.message
    }

    suspend fun connect(code: String? = null, linkToken: String? = null) {
        val response: LoginResponse = api.send(
            "auth/link/redeem", "POST",
            LinkRedeemRequest(code, linkToken, store.deviceId, deviceName()),
        )
        store(response)
    }

    suspend fun connectFromUri(uri: String) {
        val parsed = URI(uri)
        val token = if (parsed.scheme == "eegtrabocherstrasse") {
            parsed.query.orEmpty().split('&').firstOrNull { it.startsWith("token=") }?.substringAfter('=')
        } else {
            parsed.fragment.orEmpty().split('&').firstOrNull { it.startsWith("token=") }?.substringAfter('=')
        }
        require(!token.isNullOrBlank() && token.length >= 32) { "Ungültiger Verbindungslink." }
        connect(linkToken = token)
    }

    suspend inline fun <reified T> get(path: String): T = authorized { token -> api.get(path, token) }
    suspend inline fun <reified T, reified B> send(path: String, method: String, body: B): T =
        authorized { token -> api.send(path, method, body, token) }
    suspend inline fun <reified T> upload(path: String, bytes: ByteArray, contentType: String): T =
        authorized { token -> api.upload(path, token, bytes, contentType) }
    suspend inline fun <reified T> multipart(
        path: String, fields: Map<String, String>, attachments: List<UploadAttachment>,
    ): T = authorized { token -> api.multipart(path, token, fields, attachments) }
    suspend fun bytes(path: String, accept: String): ByteArray = authorized { token -> api.bytes(path, token, accept) }
    suspend fun empty(path: String, method: String = "POST") = authorized<Unit> { token -> api.empty(path, method, token) }

    suspend fun logout() {
        runCatching { empty("auth/logout") }
        store.clearSession()
        _state.value = SessionState.SignedOut
    }

    fun biometricEnabled(): Boolean = store.biometricLock
    fun setBiometricEnabled(enabled: Boolean) { store.biometricLock = enabled }
    fun cacheDashboard(value: DashboardResponse) { store.setDashboardCache(cacheJson.encodeToString(value)) }
    fun cachedDashboard(): DashboardResponse? = store.dashboardCache()?.let {
        runCatching { cacheJson.decodeFromString<DashboardResponse>(it) }.getOrNull()
    }

    @PublishedApi internal suspend fun <T> authorized(block: suspend (String) -> T): T {
        var token = store.accessToken ?: throw ApiException(401, "unauthorized", "Anmeldung erforderlich.")
        return try {
            block(token)
        } catch (error: ApiException) {
            if (error.status != 401) throw error
            refreshMutex.withLock {
                if (store.accessToken == token) refresh()
                token = store.accessToken ?: throw error
            }
            block(token)
        }
    }

    private suspend fun restore() {
        if (store.refreshToken == null) { _state.value = SessionState.SignedOut; return }
        runCatching {
            refresh()
            val me: MeResponse = get("me")
            store.memberName = me.member.name
            _state.value = SessionState.SignedIn(me.member.name)
        }.onFailure {
            store.clearSession()
            _state.value = SessionState.SignedOut
        }
    }

    private suspend fun refresh() {
        val refresh = store.refreshToken ?: throw ApiException(401, "unauthorized", "Sitzung abgelaufen.")
        val response: TokenResponse = api.send("auth/refresh", "POST", RefreshRequest(refresh))
        store.accessToken = response.accessToken
        store.refreshToken = response.refreshToken
    }

    private fun store(response: LoginResponse) {
        store.accessToken = response.accessToken
        store.refreshToken = response.refreshToken
        store.memberName = response.user.memberName
        _state.value = SessionState.SignedIn(response.user.memberName)
    }

    private fun deviceName() = "${Build.MANUFACTURER} ${Build.MODEL}".trim().take(80)
}
