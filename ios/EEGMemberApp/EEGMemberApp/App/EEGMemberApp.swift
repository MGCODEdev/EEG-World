import SwiftUI

@main
struct EEGMemberApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var auth = AuthManager()
    @StateObject private var router = AppRouter()
    @StateObject private var privacyLock = PrivacyLock()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            Group {
                if auth.isRestoringSession {
                    ProgressView("Sitzung wird geladen …")
                } else if auth.isAuthenticated && privacyLock.isLocked {
                    PrivacyLockView()
                } else if auth.isAuthenticated {
                    MainTabView()
                } else {
                    LoginView()
                }
            }
            .environmentObject(auth)
            .environmentObject(router)
            .environmentObject(privacyLock)
            .tint(EEGTheme.accent)
            .task(id: auth.isAuthenticated) {
                guard auth.isAuthenticated else { return }
                _ = await PushNotificationManager.requestAuthorization()
                await PushNotificationManager.registerIfPossible(using: auth)
            }
            .onReceive(NotificationCenter.default.publisher(for: .apnsTokenChanged)) { _ in
                Task { await PushNotificationManager.registerIfPossible(using: auth) }
            }
            .onReceive(NotificationCenter.default.publisher(for: .pushRouteReceived)) { note in
                let payload = note.userInfo ?? [:]
                router.handleNotification(payload)
                if let id = payload["message_id"] as? Int {
                    Task { try? await auth.authorizedEmpty(path: "messages/\(id)/read") }
                }
                UIApplication.shared.applicationIconBadgeNumber = 0
            }
            .onOpenURL { url in
                Task { await auth.handle(magicURL: url) }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background { privacyLock.lock() }
                if phase == .active && privacyLock.isLocked { Task { await privacyLock.unlock() } }
            }
        }
    }
}
