import Foundation

enum SensitiveCache {
    private static let directoryName = "EEGMemberPrivate"

    private static var directory: URL {
        URL.cachesDirectory.appending(path: directoryName, directoryHint: .isDirectory)
    }

    static func url(for filename: String) throws -> URL {
        try FileManager.default.createDirectory(
            at: directory,
            withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.complete]
        )
        return directory.appending(path: filename)
    }

    static func write(_ data: Data, filename: String) throws -> URL {
        let target = try url(for: filename)
        try data.write(to: target, options: [.atomic, .completeFileProtection])
        return target
    }

    static func remove(_ url: URL?) {
        guard let url, url.path.hasPrefix(directory.path) else { return }
        try? FileManager.default.removeItem(at: url)
    }

    static func removeAll() {
        try? FileManager.default.removeItem(at: directory)
        // Entfernt den Cache der ersten App-Version, der ausserhalb des
        // geschuetzten Unterverzeichnisses gespeichert wurde.
        try? FileManager.default.removeItem(
            at: URL.cachesDirectory.appending(path: "dashboard.json")
        )
    }
}
