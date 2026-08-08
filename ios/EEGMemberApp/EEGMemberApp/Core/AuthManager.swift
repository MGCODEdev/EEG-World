import Foundation

@MainActor
final class AuthManager: ObservableObject {
    @Published private(set) var isAuthenticated = false
    @Published private(set) var isRestoringSession = true
    @Published var memberName = ""
    @Published private(set) var connectionError: String?
    @Published private(set) var isConnectingLink = false

    private let client = APIClient.shared
    private let keychain = KeychainStore()
    private var accessToken: String?
    private var refreshToken: String?

    init() {
        accessToken = keychain.get("accessToken")
        refreshToken = keychain.get("refreshToken")
        if refreshToken == nil { SensitiveCache.removeAll() }
        Task { await restoreSession() }
    }

    func login(username: String, password: String) async throws {
        let body = try await client.encode(LoginRequest(
            username: username,
            password: password,
            deviceId: DeviceIdentity.shared.identifier,
            deviceName: "iPhone"
        ))
        let response = try await client.request(
            LoginResponse.self, path: "auth/login", method: "POST", body: body
        )
        try store(response)
        memberName = response.user.memberName
        isAuthenticated = true
    }

    func requestMagicLink(email: String) async throws -> String {
        let body = try await client.encode(MobileLinkRequest(email: email))
        let response = try await client.request(
            MobileLinkRequestResponse.self,
            path: "auth/link/request",
            method: "POST",
            body: body
        )
        return response.message
    }

    func connect(code: String? = nil, linkToken: String? = nil) async throws {
        let body = try await client.encode(MobileLinkRedeemRequest(
            code: code,
            linkToken: linkToken,
            deviceId: DeviceIdentity.shared.identifier,
            deviceName: "iPhone"
        ))
        let response = try await client.request(
            LoginResponse.self,
            path: "auth/link/redeem",
            method: "POST",
            body: body
        )
        try store(response)
        memberName = response.user.memberName
        isAuthenticated = true
    }

    func connect(magicURL: URL) async throws {
        guard let components = URLComponents(url: magicURL, resolvingAgainstBaseURL: false) else {
            throw APIError.server(status: 400, message: "Ungültiger Verbindungslink.", code: "invalid_link")
        }
        let isCustomLink = magicURL.scheme == "eegtrabocherstrasse" && magicURL.host == "connect"
        let isUniversalLink = magicURL.scheme == "https"
            && magicURL.host == AppConfiguration.apiBaseURL.host
            && magicURL.path == "/mobile-connect"
        let fragmentItems = URLComponents(
            string: "https://local.invalid/?\(magicURL.fragment ?? "")"
        )?.queryItems
        let token = isCustomLink
            ? components.queryItems?.first(where: { $0.name == "token" })?.value
            : fragmentItems?.first(where: { $0.name == "token" })?.value
        guard (isCustomLink || isUniversalLink), let token, token.count >= 32 else {
            throw APIError.server(status: 400, message: "Ungültiger Verbindungslink.", code: "invalid_link")
        }
        try await connect(linkToken: token)
    }

    func handle(magicURL: URL) async {
        isConnectingLink = true
        connectionError = nil
        defer { isConnectingLink = false }
        do { try await connect(magicURL: magicURL) }
        catch { connectionError = error.localizedDescription }
    }

    func authorized<T: Decodable>(
        _ type: T.Type,
        path: String,
        method: String = "GET",
        body: Data? = nil
    ) async throws -> T {
        guard let accessToken else { throw APIError.invalidResponse }
        do {
            return try await client.request(
                type, path: path, method: method, body: body, accessToken: accessToken
            )
        } catch let APIError.server(status, _, _) where status == 401 {
            try await refresh()
            guard let renewed = self.accessToken else { throw APIError.invalidResponse }
            return try await client.request(
                type, path: path, method: method, body: body, accessToken: renewed
            )
        }
    }

    func authorizedData(path: String) async throws -> Data {
        guard let accessToken else { throw APIError.invalidResponse }
        do {
            return try await client.requestData(path: path, accessToken: accessToken)
        } catch let APIError.server(status, _, _) where status == 401 {
            try await refresh()
            guard let renewed = self.accessToken else { throw APIError.invalidResponse }
            return try await client.requestData(path: path, accessToken: renewed)
        }
    }

    func authorizedImageData(path: String) async throws -> Data {
        guard let accessToken else { throw APIError.invalidResponse }
        do {
            return try await client.requestData(
                path: path, accessToken: accessToken, acceptedContentType: "image/"
            )
        } catch let APIError.server(status, _, _) where status == 401 {
            try await refresh()
            guard let renewed = self.accessToken else { throw APIError.invalidResponse }
            return try await client.requestData(
                path: path, accessToken: renewed, acceptedContentType: "image/"
            )
        }
    }

    func uploadProfilePhoto(_ data: Data) async throws {
        guard let accessToken else { throw APIError.invalidResponse }
        do {
            _ = try await client.upload(
                UpdateResponse.self, path: "me/photo", data: data,
                contentType: "image/jpeg", accessToken: accessToken
            )
        } catch let APIError.server(status, _, _) where status == 401 {
            try await refresh()
            guard let renewed = self.accessToken else { throw APIError.invalidResponse }
            _ = try await client.upload(
                UpdateResponse.self, path: "me/photo", data: data,
                contentType: "image/jpeg", accessToken: renewed
            )
        }
    }

    func sendMemberFeedback(
        message: String,
        latitude: Double?,
        longitude: Double?,
        accuracy: Double?,
        attachments: [APIClient.MultipartFile]
    ) async throws -> MemberFeedbackResponse {
        var fields = ["message": message]
        if let latitude { fields["latitude"] = String(latitude) }
        if let longitude { fields["longitude"] = String(longitude) }
        if let accuracy { fields["location_accuracy_m"] = String(accuracy) }
        guard let accessToken else { throw APIError.invalidResponse }
        do {
            return try await client.uploadMultipart(
                MemberFeedbackResponse.self, path: "member-feedback",
                fields: fields, files: attachments, accessToken: accessToken
            )
        } catch let APIError.server(status, _, _) where status == 401 {
            try await refresh()
            guard let renewed = self.accessToken else { throw APIError.invalidResponse }
            return try await client.uploadMultipart(
                MemberFeedbackResponse.self, path: "member-feedback",
                fields: fields, files: attachments, accessToken: renewed
            )
        }
    }

    func authorizedEmpty(path: String, method: String = "POST") async throws {
        guard let accessToken else { throw APIError.invalidResponse }
        do {
            try await client.requestEmpty(path: path, method: method, accessToken: accessToken)
        } catch {
            try await refresh()
            guard let renewed = self.accessToken else { throw APIError.invalidResponse }
            try await client.requestEmpty(path: path, method: method, accessToken: renewed)
        }
    }

    func logout() async {
        if let accessToken { try? await client.requestEmpty(path: "auth/logout", method: "POST", accessToken: accessToken) }
        clearSession()
    }

    func registerDevice(token: String) async throws {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
        let registration = DeviceRegistration(
            deviceToken: token, environment: APNSEnvironment.current, appVersion: version
        )
        let body = try await client.encode(registration)
        _ = try await authorized(
            DeviceRegistrationResponse.self, path: "devices/current", method: "PUT", body: body
        )
    }

    private func restoreSession() async {
        defer { isRestoringSession = false }
        guard refreshToken != nil else { return }
        do {
            try await refresh()
            let me = try await authorized(MeResponse.self, path: "me")
            memberName = me.member.name
            isAuthenticated = true
        } catch { clearSession() }
    }

    private func refresh() async throws {
        guard let refreshToken else { throw APIError.invalidResponse }
        let body = try await client.encode(RefreshRequest(refreshToken: refreshToken))
        let response = try await client.request(
            TokenResponse.self, path: "auth/refresh", method: "POST", body: body
        )
        try store(response)
    }

    private func store<T: AuthTokens>(_ tokens: T) throws {
        accessToken = tokens.accessToken
        refreshToken = tokens.refreshToken
        try keychain.set(tokens.accessToken, for: "accessToken")
        try keychain.set(tokens.refreshToken, for: "refreshToken")
    }

    private func clearSession() {
        accessToken = nil
        refreshToken = nil
        memberName = ""
        isAuthenticated = false
        keychain.removeAll()
        SensitiveCache.removeAll()
    }
}

private enum APNSEnvironment {
    #if DEBUG
    static let current = "sandbox"
    #else
    static let current = "production"
    #endif
}
