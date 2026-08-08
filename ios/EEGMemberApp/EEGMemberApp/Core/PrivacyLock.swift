import LocalAuthentication
import SwiftUI

@MainActor
final class PrivacyLock: ObservableObject {
    @AppStorage("faceIDEnabled") var isEnabled = false
    @Published var isLocked = false

    func lock() {
        if isEnabled { isLocked = true }
    }

    func unlock() async {
        guard isEnabled else { isLocked = false; return }
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            isLocked = false
            return
        }
        do {
            if try await context.evaluatePolicy(
                .deviceOwnerAuthentication,
                localizedReason: "EEG-Daten und Abrechnungen entsperren"
            ) { isLocked = false }
        } catch { }
    }
}

struct PrivacyLockView: View {
    @EnvironmentObject private var lock: PrivacyLock

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "lock.shield.fill")
                .font(.system(size: 52)).foregroundStyle(EEGTheme.accent)
            Text("EEG-App gesperrt").font(.title2.bold())
            Button("Mit Face ID entsperren") { Task { await lock.unlock() } }
                .buttonStyle(.borderedProminent)
        }
        .padding()
        .task { await lock.unlock() }
    }
}
