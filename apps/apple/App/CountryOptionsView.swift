import SwiftUI
import PrettyLisaCore

/// A native list preserves the blur and readable lock explanation on both platforms.
struct CountryOptionsView: View {
    @ObservedObject var model: AppModel
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(L("dash_where")).font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Button(L("ui_autopilot")) { choose("AUTO") }
                        .accessibilityIdentifier("country-AUTO")
                    ForEach(model.countries?.countries ?? []) { country in
                        Button { if country.selectable { choose(country.country_code) } } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text((locale.localizedString(forRegionCode: country.country_code) ?? country.country_code) + " · \(country.quality)%")
                                    .blur(radius: country.premium_required == true ? 2 : 0)
                                    .opacity(country.premium_required == true ? 0.45 : 1)
                                if country.premium_required == true {
                                    Label(L("premium_location_hint"), systemImage: "lock.fill")
                                        .font(.caption).foregroundStyle(Color(red: 44/255, green: 1/255, blue: 109/255))
                                }
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 6)
                        }.buttonStyle(.plain).disabled(!country.selectable)
                            .accessibilityIdentifier("country-" + country.country_code)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(24)
    }

    private func choose(_ code: String) {
        model.country = code
        dismiss()
    }
}
