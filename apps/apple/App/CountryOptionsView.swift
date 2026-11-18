import SwiftUI
import PrettyLisaCore

/// A native list preserves the blur and readable lock explanation on both platforms.
struct CountryOptionsView: View {
    @ObservedObject var model: AppModel
    @Environment(\.locale) private var locale
    @Environment(\.colorScheme) private var colors
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(L("dash_where")).font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Button(L("ui_autopilot")) { choose("AUTO") }
                        .accessibilityIdentifier("country-AUTO")
                    ForEach(model.countries?.countries ?? []) { country in
                        VStack(alignment: .leading, spacing: 4) {
                            Button { if country.selectable { choose(country.country_code) } } label: {
                                Text((locale.localizedString(forRegionCode: country.country_code) ?? country.country_code) + " · \(country.quality)%")
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .blur(radius: country.premium_required == true ? 2 : 0)
                                    .opacity(country.premium_required == true ? 0.45 : 1)
                            }.buttonStyle(.plain).disabled(!country.selectable)
                                .accessibilityIdentifier("country-" + country.country_code)
                            // Keep the explanation outside the disabled button's dimming.
                            if country.premium_required == true {
                                Label(L("premium_location_hint"), systemImage: "lock.fill")
                                    .font(.caption).foregroundStyle(colors == .dark
                                        ? Color(red: 172/255, green: 115/255, blue: 1)
                                        : Color(red: 44/255, green: 1/255, blue: 109/255))
                            }
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 6)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(24)
            // The phone card's black text is inherited by its presented sheet.
            .foregroundStyle(colors == .dark
                ? Color(red: 228/255, green: 228/255, blue: 228/255)
                : Color(red: 1/255, green: 1/255, blue: 1/255))
    }

    private func choose(_ code: String) {
        model.country = code
        dismiss()
    }
}
