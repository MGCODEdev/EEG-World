import UIKit
import UserNotifications

extension Notification.Name {
    static let apnsTokenChanged = Notification.Name("at.eeg.apnsTokenChanged")
    static let pushRouteReceived = Notification.Name("at.eeg.pushRouteReceived")
}

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.setNotificationCategories([
            UNNotificationCategory(
                identifier: "EEG_MESSAGE",
                actions: [UNNotificationAction(identifier: "OPEN", title: "Öffnen")],
                intentIdentifiers: []
            ),
            UNNotificationCategory(
                identifier: "EEG_INVOICE",
                actions: [UNNotificationAction(identifier: "OPEN", title: "Abrechnung öffnen")],
                intentIdentifiers: []
            )
        ])
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken token: Data) {
        let value = token.map { String(format: "%02x", $0) }.joined()
        UserDefaults.standard.set(value, forKey: "apnsDeviceToken")
        NotificationCenter.default.post(name: .apnsTokenChanged, object: value)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        NotificationCenter.default.post(name: .apnsTokenChanged, object: nil)
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound, .badge]
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        NotificationCenter.default.post(
            name: .pushRouteReceived,
            object: nil,
            userInfo: response.notification.request.content.userInfo
        )
    }
}

@MainActor
enum PushNotificationManager {
    static func requestAuthorization() async -> Bool {
        do {
            let granted = try await UNUserNotificationCenter.current()
                .requestAuthorization(options: [.alert, .sound, .badge])
            if granted { UIApplication.shared.registerForRemoteNotifications() }
            return granted
        } catch {
            return false
        }
    }

    static func registerIfPossible(using auth: AuthManager) async {
        guard let token = UserDefaults.standard.string(forKey: "apnsDeviceToken") else { return }
        try? await auth.registerDevice(token: token)
    }

    static func scheduleSoundPreview() async -> Bool {
        guard await requestAuthorization() else { return false }
        let content = UNMutableNotificationContent()
        content.title = "EEG-Testton"
        content.body = "So klingen neue Mitteilungen der EEG Trabocherstraße."
        content.sound = UNNotificationSound(
            named: UNNotificationSoundName(rawValue: "eeg-notification.caf")
        )
        let request = UNNotificationRequest(
            identifier: "eeg-sound-preview",
            content: content,
            trigger: UNTimeIntervalNotificationTrigger(timeInterval: 1, repeats: false)
        )
        do {
            try await UNUserNotificationCenter.current().add(request)
            return true
        } catch {
            return false
        }
    }
}
