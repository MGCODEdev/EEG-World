import Foundation

final class DeviceIdentity: @unchecked Sendable {
    static let shared = DeviceIdentity()

    let identifier: String

    private init() {
        let store = KeychainStore(service: "at.eeg.trabocherstrasse.member.device")
        if let existing = store.get("installationID"), existing.count >= 16 {
            identifier = existing
        } else {
            let generated = UUID().uuidString.lowercased()
            try? store.set(generated, for: "installationID")
            identifier = generated
        }
    }
}
