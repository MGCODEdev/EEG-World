import Foundation

enum AppConfiguration {
    static let apiBaseURL: URL = {
        if let value = Bundle.main.object(forInfoDictionaryKey: "API_BASE_URL") as? String,
           let url = URL(string: value) {
            return url
        }
        return URL(string: "https://admin.eeg-trabocherstrasse.at/api/v1")!
    }()
}
