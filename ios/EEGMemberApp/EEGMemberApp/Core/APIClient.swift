import Foundation

enum APIError: LocalizedError {
    case invalidResponse
    case server(status: Int, message: String, code: String)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "Der Server hat ungültig geantwortet."
        case let .server(_, message, _): return message
        case .decoding: return "Die Serverdaten konnten nicht gelesen werden."
        }
    }
}

private struct APIErrorEnvelope: Decodable {
    struct Detail: Decodable { let code: String; let message: String }
    let error: Detail
}

actor APIClient {
    struct MultipartFile: Sendable {
        let fieldName: String
        let filename: String
        let mimeType: String
        let data: Data
    }
    static let shared = APIClient()
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder = JSONEncoder()

    init(session: URLSession = .shared) {
        self.session = session
        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    private func endpointURL(for path: String) throws -> URL {
        let cleanPath = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let parts = cleanPath.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false)
        let base = AppConfiguration.apiBaseURL.appending(path: String(parts[0]))
        guard parts.count == 2 else { return base }
        guard var components = URLComponents(url: base, resolvingAgainstBaseURL: false) else {
            throw APIError.invalidResponse
        }
        components.percentEncodedQuery = String(parts[1])
        guard let url = components.url else { throw APIError.invalidResponse }
        return url
    }

    func encode<T: Encodable>(_ value: T) throws -> Data { try encoder.encode(value) }

    private func applyDeviceBinding(to request: inout URLRequest) {
        request.setValue(DeviceIdentity.shared.identifier, forHTTPHeaderField: "X-EEG-Device-ID")
    }

    func request<T: Decodable>(
        _ type: T.Type,
        path: String,
        method: String = "GET",
        body: Data? = nil,
        accessToken: String? = nil
    ) async throws -> T {
        let url = try endpointURL(for: path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        applyDeviceBinding(to: &request)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if let accessToken {
            request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let envelope = try? decoder.decode(APIErrorEnvelope.self, from: data)
            throw APIError.server(
                status: http.statusCode,
                message: envelope?.error.message ?? "Serverfehler (\(http.statusCode)).",
                code: envelope?.error.code ?? "server_error"
            )
        }
        do { return try decoder.decode(type, from: data) }
        catch { throw APIError.decoding(error) }
    }

    func requestEmpty(
        path: String,
        method: String,
        accessToken: String
    ) async throws {
        var request = URLRequest(url: try endpointURL(for: path))
        request.httpMethod = method
        applyDeviceBinding(to: &request)
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw APIError.invalidResponse
        }
    }

    func requestData(path: String, accessToken: String) async throws -> Data {
        try await requestData(
            path: path, accessToken: accessToken,
            acceptedContentType: "application/pdf"
        )
    }

    func requestData(
        path: String,
        accessToken: String,
        acceptedContentType: String
    ) async throws -> Data {
        var request = URLRequest(url: try endpointURL(for: path))
        request.timeoutInterval = 60
        applyDeviceBinding(to: &request)
        request.setValue(acceptedContentType, forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let envelope = try? decoder.decode(APIErrorEnvelope.self, from: data)
            throw APIError.server(
                status: http.statusCode,
                message: envelope?.error.message ?? "Serverfehler (\(http.statusCode)).",
                code: envelope?.error.code ?? "server_error"
            )
        }
        guard http.value(forHTTPHeaderField: "Content-Type")?.contains(acceptedContentType) == true else {
            throw APIError.invalidResponse
        }
        return data
    }

    func upload<T: Decodable>(
        _ type: T.Type,
        path: String,
        data: Data,
        contentType: String,
        accessToken: String
    ) async throws -> T {
        var request = URLRequest(url: try endpointURL(for: path))
        request.httpMethod = "PUT"
        request.timeoutInterval = 60
        request.httpBody = data
        applyDeviceBinding(to: &request)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        let (responseData, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let envelope = try? decoder.decode(APIErrorEnvelope.self, from: responseData)
            throw APIError.server(
                status: http.statusCode,
                message: envelope?.error.message ?? "Serverfehler (\(http.statusCode)).",
                code: envelope?.error.code ?? "server_error"
            )
        }
        do { return try decoder.decode(type, from: responseData) }
        catch { throw APIError.decoding(error) }
    }

    func uploadMultipart<T: Decodable>(
        _ type: T.Type,
        path: String,
        fields: [String: String],
        files: [MultipartFile],
        accessToken: String
    ) async throws -> T {
        let boundary = "EEG-\(UUID().uuidString)"
        var body = Data()
        func append(_ value: String) { body.append(Data(value.utf8)) }
        for (name, value) in fields.sorted(by: { $0.key < $1.key }) {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
            append(value)
            append("\r\n")
        }
        for file in files {
            let safeName = file.filename.replacingOccurrences(of: "\"", with: "")
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(file.fieldName)\"; filename=\"\(safeName)\"\r\n")
            append("Content-Type: \(file.mimeType)\r\n\r\n")
            body.append(file.data)
            append("\r\n")
        }
        append("--\(boundary)--\r\n")

        var request = URLRequest(url: try endpointURL(for: path))
        request.httpMethod = "POST"
        request.timeoutInterval = 90
        request.httpBody = body
        applyDeviceBinding(to: &request)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        let (responseData, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            let envelope = try? decoder.decode(APIErrorEnvelope.self, from: responseData)
            throw APIError.server(
                status: http.statusCode,
                message: envelope?.error.message ?? "Serverfehler (\(http.statusCode)).",
                code: envelope?.error.code ?? "server_error"
            )
        }
        do { return try decoder.decode(type, from: responseData) }
        catch { throw APIError.decoding(error) }
    }
}
