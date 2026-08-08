import SwiftUI

struct LoginView: View {
    private enum Method: String, CaseIterable, Identifiable {
        case email = "E-Mail"
        case code = "Code"
        case password = "Passwort"
        var id: String { rawValue }
    }

    @EnvironmentObject private var auth: AuthManager
    @State private var method: Method = .email
    @State private var email = ""
    @State private var connectionCode = ""
    @State private var username = ""
    @State private var password = ""
    @State private var isLoading = false
    @State private var isScannerPresented = false
    @State private var errorMessage: String?
    @State private var successMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    VStack(spacing: 12) {
                        Image(systemName: "bolt.house.fill")
                            .font(.system(size: 48)).foregroundStyle(EEGTheme.accent)
                        Text("EEG Trabocherstraße").font(.title2.bold())
                        Text("Mitgliederportal").foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity).listRowBackground(Color.clear)
                }

                Section("Sicher verbinden") {
                    Picker("Anmeldeverfahren", selection: $method) {
                        ForEach(Method.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)

                    switch method {
                    case .email:
                        TextField("E-Mail-Adresse", text: $email)
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                        Button("Magic Link anfordern") { Task { await requestLink() } }
                            .disabled(isLoading || email.trimmingCharacters(in: .whitespaces).isEmpty)
                    case .code:
                        TextField("XXXXX-XXXXX", text: $connectionCode)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .fontDesign(.monospaced)
                        Button("Verbindungscode verwenden") { Task { await redeemCode() } }
                            .disabled(isLoading || connectionCode.isEmpty)
                        Button {
                            isScannerPresented = true
                        } label: {
                            Label("QR-Code scannen", systemImage: "qrcode.viewfinder")
                        }
                        .disabled(!QRCodeScannerView.isScanningAvailable)
                        if !QRCodeScannerView.isScanningAvailable {
                            Text("QR-Scannen ist auf diesem Gerät nicht verfügbar. Bitte den Code manuell eingeben.")
                                .font(.footnote).foregroundStyle(.secondary)
                        }
                    case .password:
                        TextField("Benutzername oder E-Mail", text: $username)
                            .textContentType(.username).textInputAutocapitalization(.never)
                        SecureField("Passwort", text: $password).textContentType(.password)
                        Button("Mit Passwort anmelden") { Task { await signIn() } }
                            .disabled(isLoading || username.isEmpty || password.isEmpty)
                    }
                }

                if isLoading || auth.isConnectingLink { Section { HStack { Spacer(); ProgressView(); Spacer() } } }
                if let successMessage { Section { Label(successMessage, systemImage: "checkmark.circle.fill").foregroundStyle(.green) } }
                if let errorMessage { Section { Label(errorMessage, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red) } }
                if let connectionError = auth.connectionError {
                    Section { Label(connectionError, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red) }
                }

                Section("Hilfe") {
                    Text("Kein Verbindungscode? Fordern Sie mit Ihrer beim Mitgliedskonto hinterlegten E-Mail-Adresse einen Link an oder wenden Sie sich an die EEG-Verwaltung.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Text("Codes sind zehn Minuten gültig und können nur einmal verwendet werden.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Willkommen")
            .sheet(isPresented: $isScannerPresented) {
                QRCodeScannerView { value in
                    isScannerPresented = false
                    Task { await redeemScanned(value) }
                }
            }
        }
    }

    private func begin() { isLoading = true; errorMessage = nil; successMessage = nil }

    private func requestLink() async {
        begin(); defer { isLoading = false }
        do { successMessage = try await auth.requestMagicLink(email: email.trimmingCharacters(in: .whitespaces)) }
        catch { errorMessage = error.localizedDescription }
    }

    private func redeemCode() async {
        begin(); defer { isLoading = false }
        do { try await auth.connect(code: connectionCode) }
        catch { errorMessage = error.localizedDescription }
    }

    private func redeemScanned(_ value: String) async {
        begin(); defer { isLoading = false }
        do {
            guard let url = URL(string: value) else { throw APIError.invalidResponse }
            try await auth.connect(magicURL: url)
        } catch { errorMessage = error.localizedDescription }
    }

    private func signIn() async {
        begin(); defer { isLoading = false }
        do { try await auth.login(username: username, password: password) }
        catch { errorMessage = error.localizedDescription }
    }
}
