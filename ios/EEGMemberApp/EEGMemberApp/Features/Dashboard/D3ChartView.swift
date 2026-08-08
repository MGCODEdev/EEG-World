import SwiftUI
import WebKit

struct D3ChartPayload: Encodable, Equatable {
    struct Category: Encodable, Equatable {
        let label: String
        let detail: String
        let estimated: Bool
    }

    struct Series: Encodable, Equatable {
        let label: String
        let color: String
        let stack: String
        let values: [Double?]
        let colors: [String?]?

        init(
            label: String,
            color: String,
            stack: String,
            values: [Double?],
            colors: [String?]? = nil
        ) {
            self.label = label
            self.color = color
            self.stack = stack
            self.values = values
            self.colors = colors
        }
    }

    let kind: String
    let unit: String
    let categories: [Category]
    let series: [Series]
}

struct D3ChartView: UIViewRepresentable {
    let payload: D3ChartPayload

    func makeCoordinator() -> Coordinator { Coordinator(payload: payload) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.backgroundColor = .clear
        webView.scrollView.isScrollEnabled = true
        webView.scrollView.alwaysBounceVertical = false
        webView.scrollView.alwaysBounceHorizontal = false
        webView.scrollView.showsHorizontalScrollIndicator = false
        context.coordinator.webView = webView
        context.coordinator.loadChart()
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        context.coordinator.update(payload)
    }

    static func dismantleUIView(_ webView: WKWebView, coordinator: Coordinator) {
        webView.stopLoading()
        webView.navigationDelegate = nil
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        weak var webView: WKWebView?
        private var payload: D3ChartPayload
        private var isReady = false

        init(payload: D3ChartPayload) { self.payload = payload }

        func loadChart() {
            guard let webView,
                  let url = Bundle.main.url(
                    forResource: "energy-chart",
                    withExtension: "html",
                    subdirectory: "Chord"
                  ) ?? Bundle.main.url(forResource: "energy-chart", withExtension: "html")
            else { return }
            webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        }

        func update(_ newPayload: D3ChartPayload) {
            guard payload != newPayload else { return }
            payload = newPayload
            renderIfReady()
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            isReady = true
            renderIfReady()
        }

        func webView(
            _ webView: WKWebView,
            decidePolicyFor navigationAction: WKNavigationAction,
            decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
        ) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }
            decisionHandler(url.isFileURL || url.scheme == "about" ? .allow : .cancel)
        }

        private func renderIfReady() {
            guard isReady,
                  let webView,
                  let data = try? JSONEncoder().encode(payload),
                  let json = String(data: data, encoding: .utf8)
            else { return }
            webView.evaluateJavaScript("window.renderEEGD3Chart(\(json));")
        }
    }
}
