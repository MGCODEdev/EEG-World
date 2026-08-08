import AVFoundation
import CoreLocation
import Foundation
import PhotosUI
import SwiftUI
import UIKit
import UniformTypeIdentifiers

struct MyAccountView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var member: Member?
    @State private var contracts: [Contract] = []
    @State private var profilePhotoData: Data?
    @State private var organization: OrganizationInfo?
    @State private var cardShowsBack = false
    @State private var feedbackMessage = ""
    @State private var feedbackAttachments: [FeedbackAttachment] = []
    @State private var selectedFeedbackPhotos: [PhotosPickerItem] = []
    @State private var showingFeedbackCamera = false
    @State private var showingFeedbackImporter = false
    @State private var isSendingFeedback = false
    @State private var feedbackResult: String?
    @StateObject private var feedbackLocation = FeedbackLocationManager()

    var body: some View {
        List {
            Section {
                if let member {
                    DigitalMembershipCard(
                        member: member,
                        photoData: profilePhotoData,
                        contracts: contracts,
                        organization: organization,
                        showsBack: $cardShowsBack
                    )
                        .listRowInsets(EdgeInsets())
                        .listRowBackground(Color.clear)
                } else {
                    ProgressView().frame(maxWidth: .infinity)
                }
            }
            feedbackSection
            Section("Konto") {
                NavigationLink { AccountView() } label: {
                    Label("Kontostand und Buchungen", systemImage: "eurosign.circle.fill")
                }
                NavigationLink { DocumentsView() } label: {
                    Label("Rechnungen und Verträge", systemImage: "folder.fill")
                }
                NavigationLink { ProfileView() } label: {
                    Label("Meine Daten und Einstellungen", systemImage: "person.text.rectangle")
                }
            }
            if !contracts.isEmpty {
                Section("Hinterlegte Verträge") {
                    ForEach(contracts) { contract in
                        NavigationLink {
                            ProtectedPDFPreviewView(
                                path: "contracts/\(contract.id)/pdf",
                                title: contract.filename
                            )
                        } label: {
                            Label(contract.filename, systemImage: "doc.richtext.fill")
                        }
                    }
                }
            }
        }
        .navigationTitle("Mein Konto")
        .task { await loadMemberCard() }
        .onChange(of: selectedFeedbackPhotos) { _, items in
            guard !items.isEmpty else { return }
            Task { await addPhotos(items) }
        }
        .sheet(isPresented: $showingFeedbackImporter) {
            FeedbackDocumentPicker { urls in
                showingFeedbackImporter = false
                addDocuments(urls)
            }
        }
        .fullScreenCover(isPresented: $showingFeedbackCamera) {
            FeedbackCameraPicker { image in
                showingFeedbackCamera = false
                guard let image, let data = image.profileJPEGData else { return }
                addAttachment(
                    .init(filename: "EEG-Foto-\(Date().timeIntervalSince1970.rounded()).jpg", mimeType: "image/jpeg", data: data)
                )
            }
        }
        .alert("Nachricht an die EEG", isPresented: Binding(
            get: { feedbackResult != nil },
            set: { if !$0 { feedbackResult = nil } }
        )) { Button("OK") { feedbackResult = nil } } message: {
            Text(feedbackResult ?? "")
        }
    }

    private var feedbackSection: some View {
        Section("Nachricht an die EEG") {
            TextField(
                "Nachricht, Frage oder Dokumentation …",
                text: $feedbackMessage,
                axis: .vertical
            )
            .lineLimit(3...7)

            if !feedbackAttachments.isEmpty {
                ForEach(feedbackAttachments) { attachment in
                    HStack(spacing: 10) {
                        Image(systemName: attachment.mimeType == "application/pdf" ? "doc.fill" : "photo.fill")
                            .foregroundStyle(EEGTheme.accent)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(attachment.filename).font(.subheadline).lineLimit(1)
                            Text(ByteCountFormatter.string(fromByteCount: Int64(attachment.data.count), countStyle: .file))
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button(role: .destructive) {
                            feedbackAttachments.removeAll { $0.id == attachment.id }
                        } label: { Image(systemName: "xmark.circle.fill") }
                            .buttonStyle(.plain)
                    }
                }
            }

            HStack(spacing: 14) {
                PhotosPicker(
                    selection: $selectedFeedbackPhotos,
                    maxSelectionCount: max(1, 5 - feedbackAttachments.count),
                    matching: .images
                ) { Label("Fotos", systemImage: "photo.on.rectangle") }
                Button { Task { await openFeedbackCamera() } } label: {
                    Label("Kamera", systemImage: "camera.fill")
                }
                Button { showingFeedbackImporter = true } label: {
                    Label("Datei", systemImage: "paperclip")
                }
            }
            .font(.caption.weight(.semibold))
            .disabled(feedbackAttachments.count >= 5)

            Label(
                "Beim Senden werden Standort und Verbindungs-IP automatisch beigefügt.",
                systemImage: "location.fill"
            )
            .font(.caption).foregroundStyle(.secondary)

            Button {
                Task { await sendFeedback() }
            } label: {
                HStack {
                    if isSendingFeedback { ProgressView().controlSize(.small) }
                    Label("Sicher an die EEG senden", systemImage: "paperplane.fill")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .disabled(
                isSendingFeedback || (
                    feedbackMessage.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    && feedbackAttachments.isEmpty
                )
            )
            Text("iOS fragt die Standortberechtigung erst beim ersten Senden an.")
                .font(.caption2).foregroundStyle(.tertiary)
        }
    }

    private func loadMemberCard() async {
        async let memberRequest = try? auth.authorized(MeResponse.self, path: "me")
        async let contractRequest = try? auth.authorized(ContractsResponse.self, path: "contracts")
        async let photoRequest = try? auth.authorizedImageData(path: "me/photo")
        let (memberResponse, contractResponse, photoResponse) = await (
            memberRequest, contractRequest, photoRequest
        )
        member = memberResponse?.member
        organization = memberResponse?.organization
        contracts = contractResponse?.contracts ?? []
        profilePhotoData = photoResponse
    }

    private func addPhotos(_ items: [PhotosPickerItem]) async {
        for item in items.prefix(max(0, 5 - feedbackAttachments.count)) {
            guard let source = try? await item.loadTransferable(type: Data.self),
                  let image = UIImage(data: source), let data = image.profileJPEGData else { continue }
            addAttachment(.init(
                filename: "EEG-Foto-\(UUID().uuidString.prefix(8)).jpg",
                mimeType: "image/jpeg", data: data
            ))
        }
        selectedFeedbackPhotos = []
    }

    private func addDocuments(_ urls: [URL]) {
        for url in urls.prefix(max(0, 5 - feedbackAttachments.count)) {
            let accessed = url.startAccessingSecurityScopedResource()
            defer { if accessed { url.stopAccessingSecurityScopedResource() } }
            guard let data = try? Data(contentsOf: url), data.count <= 5 * 1024 * 1024 else {
                feedbackResult = "Eine Anlage konnte nicht gelesen werden oder ist größer als 5 MB."
                continue
            }
            let type = UTType(filenameExtension: url.pathExtension)
            let mimeType = type?.preferredMIMEType ?? "application/octet-stream"
            guard ["application/pdf", "image/jpeg", "image/png"].contains(mimeType) else { continue }
            addAttachment(.init(filename: url.lastPathComponent, mimeType: mimeType, data: data))
        }
    }

    @MainActor
    private func openFeedbackCamera() async {
        guard UIImagePickerController.isSourceTypeAvailable(.camera) else {
            feedbackResult = "Der iOS-Simulator besitzt keine Kamera. Bitte diese Funktion auf einem echten iPhone testen."
            return
        }
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            showingFeedbackCamera = true
        case .notDetermined:
            if await AVCaptureDevice.requestAccess(for: .video) {
                showingFeedbackCamera = true
            } else {
                feedbackResult = "Der Kamerazugriff wurde nicht erlaubt. Bitte in Einstellungen › Datenschutz & Sicherheit › Kamera aktivieren."
            }
        case .denied, .restricted:
            feedbackResult = "Der Kamerazugriff ist deaktiviert. Bitte in Einstellungen › Datenschutz & Sicherheit › Kamera aktivieren."
        @unknown default:
            feedbackResult = "Die Kamera konnte nicht geöffnet werden."
        }
    }

    private func addAttachment(_ attachment: FeedbackAttachment) {
        guard feedbackAttachments.count < 5 else { return }
        let newTotal = feedbackAttachments.reduce(attachment.data.count) { $0 + $1.data.count }
        guard newTotal <= 15 * 1024 * 1024 else {
            feedbackResult = "Alle Anlagen dürfen zusammen höchstens 15 MB groß sein."
            return
        }
        feedbackAttachments.append(attachment)
    }

    private func sendFeedback() async {
        isSendingFeedback = true
        defer { isSendingFeedback = false }
        do {
            let location = try await feedbackLocation.currentLocation()
            let response = try await auth.sendMemberFeedback(
                message: feedbackMessage.trimmingCharacters(in: .whitespacesAndNewlines),
                latitude: location.coordinate.latitude,
                longitude: location.coordinate.longitude,
                accuracy: location.horizontalAccuracy,
                attachments: feedbackAttachments.map {
                    .init(fieldName: "attachments", filename: $0.filename, mimeType: $0.mimeType, data: $0.data)
                }
            )
            feedbackMessage = ""
            feedbackAttachments = []
            feedbackLocation.clear()
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            feedbackResult = "Nachricht #\(response.id) wurde sicher an die EEG übermittelt."
        } catch {
            UINotificationFeedbackGenerator().notificationOccurred(.error)
            feedbackResult = error.localizedDescription
        }
    }

}

private struct FeedbackAttachment: Identifiable {
    let id = UUID()
    let filename: String
    let mimeType: String
    let data: Data
}

private final class FeedbackLocationManager: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var location: CLLocation?
    @Published var errorMessage: String?
    private let manager = CLLocationManager()
    private var continuation: CheckedContinuation<CLLocation, Error>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func currentLocation() async throws -> CLLocation {
        if let location,
           abs(location.timestamp.timeIntervalSinceNow) < 120 {
            return location
        }
        return try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            requestCurrentLocation()
        }
    }

    private func requestCurrentLocation() {
        errorMessage = nil
        switch manager.authorizationStatus {
        case .notDetermined: manager.requestWhenInUseAuthorization()
        case .authorizedAlways, .authorizedWhenInUse: manager.requestLocation()
        default: finish(
            with: .failure(FeedbackLocationError.permissionRequired)
        )
        }
    }

    func clear() { location = nil; errorMessage = nil }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        if manager.authorizationStatus == .authorizedAlways || manager.authorizationStatus == .authorizedWhenInUse {
            manager.requestLocation()
        } else if manager.authorizationStatus == .denied || manager.authorizationStatus == .restricted {
            finish(with: .failure(FeedbackLocationError.permissionRequired))
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let newest = locations.last else {
            finish(with: .failure(FeedbackLocationError.unavailable))
            return
        }
        location = newest
        finish(with: .success(newest))
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        finish(with: .failure(FeedbackLocationError.unavailable))
    }

    private func finish(with result: Result<CLLocation, Error>) {
        guard let continuation else { return }
        self.continuation = nil
        if case .failure(let error) = result { errorMessage = error.localizedDescription }
        continuation.resume(with: result)
    }
}

private enum FeedbackLocationError: LocalizedError {
    case permissionRequired
    case unavailable

    var errorDescription: String? {
        switch self {
        case .permissionRequired:
            "Zum Senden muss der Standortzugriff in den iOS-Einstellungen erlaubt werden."
        case .unavailable:
            "Der aktuelle Standort konnte nicht bestimmt werden. Bitte erneut versuchen."
        }
    }
}

private struct FeedbackCameraPicker: UIViewControllerRepresentable {
    let completion: (UIImage?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraCaptureMode = .photo
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let completion: (UIImage?) -> Void
        init(completion: @escaping (UIImage?) -> Void) { self.completion = completion }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            completion(info[.originalImage] as? UIImage)
            picker.dismiss(animated: true)
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            completion(nil)
            picker.dismiss(animated: true)
        }
    }
}

private struct FeedbackDocumentPicker: UIViewControllerRepresentable {
    let completion: ([URL]) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker = UIDocumentPickerViewController(
            forOpeningContentTypes: [.pdf, .jpeg, .png],
            asCopy: true
        )
        picker.allowsMultipleSelection = true
        picker.shouldShowFileExtensions = true
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(
        _ uiViewController: UIDocumentPickerViewController,
        context: Context
    ) {}

    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let completion: ([URL]) -> Void

        init(completion: @escaping ([URL]) -> Void) {
            self.completion = completion
        }

        func documentPicker(
            _ controller: UIDocumentPickerViewController,
            didPickDocumentsAt urls: [URL]
        ) {
            completion(urls)
        }

        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            completion([])
        }
    }
}

private struct DigitalMembershipCard: View {
    let member: Member
    let photoData: Data?
    let contracts: [Contract]
    let organization: OrganizationInfo?
    @Binding var showsBack: Bool
    @State private var isFlying = false

    var body: some View {
        ZStack {
            cardFace { front }
                .opacity(showsBack ? 0 : 1)
                .rotation3DEffect(
                    .degrees(showsBack ? -90 : 0), axis: (x: 0, y: 1, z: 0),
                    perspective: 0.68
                )
            cardFace { back }
                .opacity(showsBack ? 1 : 0)
                .rotation3DEffect(
                    .degrees(showsBack ? 0 : 90), axis: (x: 0, y: 1, z: 0),
                    perspective: 0.68
                )
        }
        .animation(.spring(response: 0.48, dampingFraction: 0.82), value: showsBack)
        .scaleEffect(isFlying ? 1.045 : 1)
        .offset(y: isFlying ? -17 : 0)
        .rotationEffect(.degrees(isFlying ? -1.4 : 0))
        .shadow(color: .black.opacity(isFlying ? 0.28 : 0.10), radius: isFlying ? 24 : 8, y: isFlying ? 18 : 5)
        .onTapGesture { flipCard() }
        .accessibilityAction(named: "Ausweis umdrehen") { flipCard() }
    }

    private var front: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                HStack(spacing: 7) {
                    appLogo
                    Text("MITGLIEDSAUSWEIS").font(.caption.bold()).tracking(0.8)
                }
                Spacer()
                Text(isActive ? "AKTIV" : "INAKTIV")
                    .font(.caption2.bold())
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(.white.opacity(0.18), in: Capsule())
            }
            Spacer(minLength: 2)
            HStack(spacing: 12) {
                profilePhoto
                VStack(alignment: .leading, spacing: 3) {
                    Text(member.name).font(.title3.bold()).lineLimit(2)
                    Text(organization?.name ?? "EEG Trabocherstraße")
                        .font(.subheadline.weight(.semibold)).opacity(0.9)
                    Text("Verein · \(organization?.zvr ?? "ZVR nicht hinterlegt")")
                        .font(.caption2).opacity(0.72)
                }
            }
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("MITGLIEDSNUMMER").font(.caption2).opacity(0.72)
                    Text(String(format: "%06d", member.id))
                        .font(.subheadline.monospacedDigit().weight(.semibold))
                }
                Spacer()
                if let point = member.bezugZp, !point.isEmpty {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("ZÄHLPUNKT").font(.caption2).opacity(0.72)
                        Text(point.maskedMeteringPoint)
                            .font(.system(.caption, design: .monospaced)).lineLimit(1)
                    }
                }
            }
            Text(validUntilText)
                .font(.caption2.monospacedDigit().weight(.semibold))
                .opacity(0.78)
        }
    }

    private var back: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                appLogo
                Text("MITGLIEDSDETAILS").font(.caption.bold()).tracking(0.8)
                Spacer()
                Image(systemName: "arrow.triangle.2.circlepath")
            }
            Divider().overlay(.white.opacity(0.45))
            cardDetail("Teilnahme", value: member.teilnahme.map { "\($0.formatted(.percent.precision(.fractionLength(0))))" } ?? "–")
            cardDetail("Rolle", value: memberRole)
            cardDetail("Verträge", value: contracts.isEmpty ? "Keine hinterlegt" : "\(contracts.count) PDF-Dokument(e)")
            if memberStreetLine != nil || memberCityLine != nil {
                addressDetail
            }
            if let email = member.email, !email.isEmpty {
                cardDetail("Kontakt", value: email)
            }
            Spacer(minLength: 0)
            Text("Zum Zurückdrehen tippen")
                .font(.caption2).opacity(0.7).frame(maxWidth: .infinity, alignment: .center)
        }
    }

    private var memberRole: String {
        switch (member.bezugZp?.isEmpty == false, member.einspeiserZp?.isEmpty == false) {
        case (true, true): "Bezieher und Einspeiser"
        case (true, false): "Bezieher"
        case (false, true): "Einspeiser"
        default: "Mitglied"
        }
    }

    private var isActive: Bool { member.active ?? true }

    private var validUntilText: String {
        let validUntil = Calendar.current.date(byAdding: .year, value: 1, to: Date()) ?? Date()
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "de_AT")
        formatter.dateFormat = "MM/yyyy"
        return "Gültig bis " + formatter.string(from: validUntil)
    }

    private var memberStreetLine: String? {
        let street = member.addressStreet?.trimmingCharacters(in: .whitespacesAndNewlines)
        return street?.isEmpty == false ? street : nil
    }

    private var memberCityLine: String? {
        let city = [member.addressZip, member.addressCity]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }.joined(separator: " ")
        return city.isEmpty ? nil : city
    }

    private var addressDetail: some View {
        HStack(alignment: .top) {
            Text("Adresse").font(.caption2).opacity(0.72)
            Spacer()
            VStack(alignment: .trailing, spacing: 1) {
                if let street = memberStreetLine {
                    Text(street)
                }
                if let city = memberCityLine {
                    Text(city)
                }
            }
            .font(.caption.weight(.semibold))
            .multilineTextAlignment(.trailing)
            .lineLimit(1)
            .minimumScaleFactor(0.78)
        }
    }

    private func cardDetail(_ title: String, value: String, lineLimit: Int = 1) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(.caption2).opacity(0.72)
            Spacer()
            Text(value)
                .font(.caption.weight(.semibold))
                .multilineTextAlignment(.trailing)
                .lineLimit(lineLimit)
        }
    }

    private func flipCard() {
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        withAnimation(.spring(response: 0.22, dampingFraction: 0.72)) {
            isFlying = true
        }
        withAnimation(.spring(response: 0.58, dampingFraction: 0.78)) {
            showsBack.toggle()
        }
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 230_000_000)
            withAnimation(.spring(response: 0.34, dampingFraction: 0.72)) {
                isFlying = false
            }
        }
    }

    private var appLogo: some View {
        Group {
            if let image = bundleAppIcon {
                Image(uiImage: image).resizable().scaledToFit()
            } else {
                Image(systemName: "sun.max.fill").symbolRenderingMode(.multicolor)
            }
        }
        .frame(width: 27, height: 27)
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private var bundleAppIcon: UIImage? {
        let icons = Bundle.main.infoDictionary?["CFBundleIcons"] as? [String: Any]
        let primary = icons?["CFBundlePrimaryIcon"] as? [String: Any]
        let files = primary?["CFBundleIconFiles"] as? [String]
        return files?.last.flatMap(UIImage.init(named:)) ?? UIImage(named: "AppIcon")
    }

    private var profilePhoto: some View {
        Group {
            if let photoData, let image = UIImage(data: photoData) {
                Image(uiImage: image).resizable().scaledToFill()
            } else {
                Image(systemName: "person.crop.circle.fill")
                    .resizable().scaledToFit().foregroundStyle(.white.opacity(0.86))
            }
        }
        .frame(width: 58, height: 58)
        .clipShape(Circle())
        .overlay { Circle().stroke(.white.opacity(0.72), lineWidth: 2) }
    }

    private func cardFace<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
        .foregroundStyle(.white)
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .aspectRatio(85.60 / 53.98, contentMode: .fit)
        .background(
            LinearGradient(
                colors: isActive
                    ? [Color(red: 0.04, green: 0.20, blue: 0.23), EEGTheme.accent, Color(red: 0.04, green: 0.34, blue: 0.30)]
                    : [Color(red: 0.42, green: 0.03, blue: 0.05), Color.red, Color(red: 0.28, green: 0.02, blue: 0.04)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 22)
        )
        .overlay(alignment: .topTrailing) {
            Circle().fill(.white.opacity(0.08)).frame(width: 150, height: 150)
                .offset(x: 42, y: -58)
        }
        .overlay {
            LinearGradient(
                colors: [.clear, .white.opacity(0.20), .clear, .white.opacity(0.06)],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
            .blendMode(.screen)
            .clipShape(RoundedRectangle(cornerRadius: 22))
        }
        .overlay {
            if !isActive {
                Rectangle()
                    .fill(.white.opacity(0.82))
                    .frame(height: 4)
                    .rotationEffect(.degrees(-16))
                    .padding(.horizontal, 12)
                    .accessibilityHidden(true)
            }
        }
        .shadow(color: EEGTheme.accent.opacity(0.22), radius: 12, y: 6)
        .padding(.horizontal, 2).padding(.vertical, 8)
        .accessibilityElement(children: .combine)
    }
}

extension UIImage {
    var profileJPEGData: Data? {
        let maximumDimension: CGFloat = 1024
        let scale = min(1, maximumDimension / max(size.width, size.height))
        let target = CGSize(width: size.width * scale, height: size.height * scale)
        let renderer = UIGraphicsImageRenderer(size: target)
        let resized = renderer.image { _ in draw(in: CGRect(origin: .zero, size: target)) }
        return resized.jpegData(compressionQuality: 0.82)
    }
}

private extension String {
    var maskedMeteringPoint: String {
        guard count > 8 else { return self }
        return "\(prefix(4))…\(suffix(4))"
    }
}

struct AccountView: View {
    @EnvironmentObject private var auth: AuthManager
    @State private var account: AccountSummary?

    var body: some View {
        List {
            if let account {
                Section("Buchungsübersicht") {
                    BookingAmountRow(title: "Kontostand", value: account.balance, symbol: "creditcard.fill", color: EEGTheme.accent, emphasized: true)
                    BookingAmountRow(title: "Offene Forderungen", value: account.openClaims, symbol: "clock.fill", color: EEGTheme.warning)
                    BookingAmountRow(title: "Guthaben", value: abs(account.openCredits), symbol: "plus.circle.fill", color: EEGTheme.positive)
                    BookingAmountRow(title: "Überfällig", value: account.overdueClaims, symbol: "exclamationmark.circle.fill", color: .red)
                }
                Section("Buchungen") {
                    ForEach(account.history) { event in
                        HStack(spacing: 11) {
                            Image(systemName: event.amount >= 0 ? "arrow.down.left.circle.fill" : "arrow.up.right.circle.fill")
                                .font(.title3)
                                .foregroundStyle(event.amount >= 0 ? EEGTheme.positive : EEGTheme.grid)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(event.label)
                                    .font(.system(.subheadline, design: .rounded, weight: .semibold))
                                Text(DateText.date(event.date))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(event.amount.euro)
                                .font(.system(.subheadline, design: .monospaced, weight: .bold))
                        }
                        .padding(.vertical, 4)
                        .accessibilityElement(children: .combine)
                    }
                }
            }
        }
        .navigationTitle("Mitgliedskonto")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        account = try? await auth.authorized(AccountResponse.self, path: "account").account
    }
}

private struct BookingAmountRow: View {
    let title: String
    let value: Double
    let symbol: String
    let color: Color
    var emphasized = false

    var body: some View {
        HStack(spacing: 11) {
            Image(systemName: symbol)
                .foregroundStyle(color)
                .frame(width: 30, height: 30)
                .background(color.opacity(0.13), in: Circle())
            Text(title)
                .font(.system(.subheadline, design: .rounded, weight: emphasized ? .bold : .medium))
            Spacer()
            Text(value.euro)
                .font(.system(emphasized ? .headline : .subheadline, design: .monospaced, weight: .bold))
        }
        .accessibilityElement(children: .combine)
    }
}
