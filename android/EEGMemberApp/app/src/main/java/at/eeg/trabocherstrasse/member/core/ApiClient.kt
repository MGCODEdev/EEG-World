package at.eeg.trabocherstrasse.member.core

import at.eeg.trabocherstrasse.member.BuildConfig
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class ApiException(val status: Int, val code: String, override val message: String) : IOException(message)

class ApiClient(
    @PublishedApi internal val deviceId: String,
    @PublishedApi internal val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(90, TimeUnit.SECONDS)
        .build(),
) {
    @PublishedApi internal val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    @PublishedApi internal val baseUrl = BuildConfig.API_BASE_URL.toHttpUrl()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    suspend inline fun <reified T> get(path: String, token: String? = null): T =
        decode(execute(request(path, token).get().build()))

    suspend inline fun <reified T, reified B> send(
        path: String, method: String, body: B, token: String? = null,
    ): T {
        val payload = json.encodeToString(body).toRequestBody("application/json; charset=utf-8".toMediaType())
        return decode(execute(request(path, token).method(method, payload).build()))
    }

    suspend fun empty(path: String, method: String, token: String): Unit {
        execute(request(path, token).method(method, ByteArray(0).toRequestBody(null)).build()).close()
    }

    suspend fun bytes(path: String, token: String, accept: String): ByteArray {
        val response = execute(request(path, token).header("Accept", accept).build())
        response.use {
            val contentType = it.header("Content-Type").orEmpty()
            if (!contentType.contains(accept.removeSuffix("*"))) throw IOException("Unerwarteter Dateityp")
            return it.body?.bytes() ?: throw IOException("Leere Serverantwort")
        }
    }

    suspend inline fun <reified T> upload(
        path: String, token: String, bytes: ByteArray, contentType: String,
    ): T = decode(execute(request(path, token).put(bytes.toRequestBody(contentType.toMediaType())).build()))

    suspend inline fun <reified T> multipart(
        path: String,
        token: String,
        fields: Map<String, String>,
        attachments: List<UploadAttachment>,
    ): T {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM).apply {
            fields.toSortedMap().forEach { (name, value) -> addFormDataPart(name, value) }
            attachments.forEach { file ->
                addFormDataPart(
                    "attachments", file.filename,
                    file.bytes.toRequestBody(file.mimeType.toMediaType()),
                )
            }
        }.build()
        return decode(execute(request(path, token).post(body).build()))
    }

    @PublishedApi internal fun request(path: String, token: String?): Request.Builder {
        val url = baseUrl.resolve(path) ?: throw IOException("Ungültiger API-Pfad")
        return Request.Builder().url(url)
            .header("Accept", "application/json")
            .header("X-EEG-Device-ID", deviceId)
            .apply { if (token != null) header("Authorization", "Bearer $token") }
    }

    @PublishedApi internal suspend fun execute(request: Request): Response = suspendCancellableCoroutine { continuation ->
        val call = client.newCall(request)
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (continuation.isActive) continuation.resumeWithException(e)
            }
            override fun onResponse(call: Call, response: Response) {
                if (!continuation.isActive) { response.close(); return }
                if (response.isSuccessful) continuation.resume(response)
                else {
                    val raw = response.body?.string().orEmpty()
                    val envelope = runCatching { json.decodeFromString<ApiErrorEnvelope>(raw) }.getOrNull()
                    val error = ApiException(
                        response.code,
                        envelope?.error?.code ?: "server_error",
                        envelope?.error?.message ?: "Serverfehler (${response.code}).",
                    )
                    response.close()
                    continuation.resumeWithException(error)
                }
            }
        })
    }

    @PublishedApi internal inline fun <reified T> decode(response: Response): T = response.use {
        val raw = it.body?.string() ?: throw IOException("Leere Serverantwort")
        runCatching { json.decodeFromString<T>(raw) }
            .getOrElse { error -> throw IOException("Serverdaten konnten nicht gelesen werden.", error) }
    }
}
