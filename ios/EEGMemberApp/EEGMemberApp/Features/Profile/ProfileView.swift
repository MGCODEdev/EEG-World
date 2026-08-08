import PhotosUI
import SwiftUI
import UIKit
import UserNotifications

struct ProfileView: View {
    @EnvironmentObject private var auth: AuthManager
    @EnvironmentObject private var privacyLock: PrivacyLock
    @Environment(\.openURL) private var openURL
    @State private var member: Member?
    @State private var profilePhotoData: Data?
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var isUploadingPhoto = false
    @State private var notificationPreferences = NotificationPreferences(
        notificationsEnabled: true, soundEnabled: true,
        invoiceNotifications: true, communityNotifications: true
    )
    @State private var notificationStatus: UNAuthorizationStatus = .notDetermined
    @State private var isSaving = false
    @State private var saveMessage: String?

    var body: some View {
        Form {
            if let binding = Binding($member) {
                Section("Profilfoto") {
                    HStack(spacing: 16) {
                        profilePhoto
                        VStack(alignment: .leading, spacing: 7) {
                            Text("Dein Foto")
                                .font(.headline)
                            Text("Wird im Profil und auf dem Mitgliedsausweis verwendet.")
                                .font(.caption).foregroundStyle(.secondary)
                            PhotosPicker(selection: $selectedPhoto, matching: .images) {
                                Label(
                                    profilePhotoData == nil ? "Foto auswählen" : "Foto ändern",
                                    systemImage: "photo.badge.plus"
                                )
                                .font(.subheadline.weight(.semibold))
                            }
                            .disabled(isUploadingPhoto)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 5)
                    if isUploadingPhoto {
                        ProgressView("Foto wird sicher gespeichert …")
                            .font(.caption)
                    }
                }
                Section("Kontakt") {
                    TextField("E-Mail", text: binding.email.orEmpty)
                    TextField("Telefon", text: binding.phone.orEmpty)
                    TextField("Straße", text: binding.addressStreet.orEmpty)
                    TextField("PLZ", text: binding.addressZip.orEmpty)
                    TextField("Ort", text: binding.addressCity.orEmpty)
                }
                Section("Bankverbindung") {
                    TextField("Kontoinhaber", text: binding.accountHolder.orEmpty)
                    TextField("IBAN", text: binding.iban.orEmpty).textInputAutocapitalization(.characters)
                    TextField("BIC", text: binding.bic.orEmpty).textInputAutocapitalization(.characters)
                }
                Section {
                    Toggle("Newsletter erhalten", isOn: Binding(
                        get: { binding.wrappedValue.newsletterOptout != 1 },
                        set: { binding.wrappedValue.newsletterOptout = $0 ? 0 : 1 }
                    ))
                }
                Section("Sicherheit") {
                    Toggle("Mit Face ID schützen", isOn: $privacyLock.isEnabled)
                    Text("Beim erneuten Öffnen werden persönliche Daten und PDFs geschützt.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Section("Mitteilungen") {
                    Toggle("EEG-Mitteilungen", isOn: $notificationPreferences.notificationsEnabled)
                    Toggle("Ton abspielen", isOn: $notificationPreferences.soundEnabled)
                        .disabled(!notificationPreferences.notificationsEnabled)
                    Toggle("Neue Abrechnungen", isOn: $notificationPreferences.invoiceNotifications)
                        .disabled(!notificationPreferences.notificationsEnabled)
                    Toggle("Nachrichten der Gemeinschaft", isOn: $notificationPreferences.communityNotifications)
                        .disabled(!notificationPreferences.notificationsEnabled)
                    if notificationStatus == .denied {
                        Button("iOS-Mitteilungseinstellungen öffnen") {
                            openURL(URL(string: UIApplication.openSettingsURLString)!)
                        }
                    }
                    Button("Mitteilungseinstellungen speichern") {
                        Task { await saveNotificationPreferences() }
                    }
                    Button {
                        Task {
                            let scheduled = await PushNotificationManager.scheduleSoundPreview()
                            saveMessage = scheduled
                                ? "Der EEG-Testton wird gleich abgespielt."
                                : "Der Testton konnte nicht geplant werden. Bitte prüfen Sie die iOS-Mitteilungseinstellungen."
                        }
                    } label: {
                        Label("EEG-Ton testen", systemImage: "speaker.wave.2.fill")
                    }
                }
                Section {
                    Button("Änderungen speichern") { Task { await save(binding.wrappedValue) } }.disabled(isSaving)
                    Button("Abmelden", role: .destructive) { Task { await auth.logout() } }
                }
            } else { ProgressView() }
        }
        .navigationTitle("Meine Daten")
        .task { await load() }
        .onChange(of: selectedPhoto) { _, item in
            guard let item else { return }
            Task { await upload(item) }
        }
        .alert("EEG-App", isPresented: Binding(
            get: { saveMessage != nil }, set: { if !$0 { saveMessage = nil } }
        )) { Button("OK") { saveMessage = nil } } message: { Text(saveMessage ?? "") }
    }

    private func load() async {
        member = try? await auth.authorized(MeResponse.self, path: "me").member
        profilePhotoData = try? await auth.authorizedImageData(path: "me/photo")
        if let response = try? await auth.authorized(
            NotificationPreferencesResponse.self, path: "notification-preferences"
        ) { notificationPreferences = response.preferences }
        notificationStatus = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
    }

    private var profilePhoto: some View {
        Group {
            if let profilePhotoData, let image = UIImage(data: profilePhotoData) {
                Image(uiImage: image).resizable().scaledToFill()
            } else {
                Image(systemName: "person.crop.circle.fill")
                    .resizable().scaledToFit()
                    .foregroundStyle(EEGTheme.accent.opacity(0.72))
                    .padding(7)
            }
        }
        .frame(width: 82, height: 82)
        .background(Color(.secondarySystemGroupedBackground), in: Circle())
        .clipShape(Circle())
        .overlay { Circle().stroke(EEGTheme.accent.opacity(0.75), lineWidth: 2) }
        .shadow(color: EEGTheme.accent.opacity(0.16), radius: 7, y: 3)
        .accessibilityLabel(profilePhotoData == nil ? "Kein Profilfoto" : "Aktuelles Profilfoto")
    }

    private func upload(_ item: PhotosPickerItem) async {
        isUploadingPhoto = true
        defer { isUploadingPhoto = false }
        guard let source = try? await item.loadTransferable(type: Data.self),
              let image = UIImage(data: source),
              let data = image.profileJPEGData else {
            saveMessage = "Das ausgewählte Foto konnte nicht verarbeitet werden."
            return
        }
        do {
            try await auth.uploadProfilePhoto(data)
            profilePhotoData = data
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            saveMessage = "Das Profilfoto wurde sicher gespeichert."
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
            saveMessage = error.localizedDescription
        }
    }

    private func save(_ member: Member) async {
        isSaving = true; defer { isSaving = false }
        let update = ProfileUpdate(
            email: member.email ?? "", phone: member.phone ?? "",
            addressStreet: member.addressStreet ?? "", addressZip: member.addressZip ?? "",
            addressCity: member.addressCity ?? "", accountHolder: member.accountHolder ?? "",
            iban: member.iban ?? "", bic: member.bic ?? "",
            newsletterOptout: member.newsletterOptout == 1
        )
        guard let body = try? await APIClient.shared.encode(update) else { return }
        do {
            self.member = try await auth.authorized(
                MeResponse.self, path: "me", method: "PATCH", body: body
            ).member
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            saveMessage = "Änderungen wurden gespeichert."
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
            saveMessage = error.localizedDescription
        }
    }

    private func saveNotificationPreferences() async {
        if notificationPreferences.notificationsEnabled && notificationStatus != .authorized {
            _ = await PushNotificationManager.requestAuthorization()
            notificationStatus = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
            await PushNotificationManager.registerIfPossible(using: auth)
        }
        do {
            let body = try await APIClient.shared.encode(notificationPreferences)
            _ = try await auth.authorized(
                UpdateResponse.self, path: "notification-preferences", method: "PATCH", body: body
            )
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            saveMessage = "Mitteilungseinstellungen wurden gespeichert."
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
            saveMessage = error.localizedDescription
        }
    }
}

private extension Binding where Value == String? {
    var orEmpty: Binding<String> {
        Binding<String>(get: { wrappedValue ?? "" }, set: { wrappedValue = $0 })
    }
}
