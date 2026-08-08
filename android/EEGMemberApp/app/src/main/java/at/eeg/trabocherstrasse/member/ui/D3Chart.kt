package at.eeg.trabocherstrasse.member.ui

import android.annotation.SuppressLint
import android.graphics.Color
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable data class ChartCategory(val label: String, val detail: String, val estimated: Boolean = false)
@Serializable data class ChartSeries(
    val label: String, val color: String, val stack: String,
    val values: List<Double?>, val colors: List<String?>? = null,
)
@Serializable data class ChartPayload(
    val kind: String, val unit: String,
    val categories: List<ChartCategory>, val series: List<ChartSeries>,
)

@SuppressLint("SetJavaScriptEnabled")
@Composable fun D3Chart(payload: ChartPayload, modifier: Modifier = Modifier) {
    val json = Json.encodeToString(payload)
    var webView: WebView? = null
    AndroidView(
        modifier = modifier,
        factory = { context ->
            WebView(context).apply {
                webView = this
                setBackgroundColor(Color.TRANSPARENT)
                isVerticalScrollBarEnabled = false
                isHorizontalScrollBarEnabled = false
                settings.javaScriptEnabled = true
                settings.allowFileAccess = true
                settings.allowContentAccess = false
                settings.domStorageEnabled = false
                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                        request.url.scheme !in setOf("file", "about")
                    override fun onPageFinished(view: WebView, url: String) {
                        view.evaluateJavascript("window.renderEEGD3Chart($json);", null)
                    }
                }
                loadUrl("file:///android_asset/charts/energy-chart.html")
            }
        },
        update = { view ->
            webView = view
            view.evaluateJavascript("if(window.renderEEGD3Chart){window.renderEEGD3Chart($json);}", null)
        },
    )
    DisposableEffect(Unit) { onDispose { webView?.destroy() } }
}
