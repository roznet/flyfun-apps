//
//  IgnoredAirportRowView.swift
//  FlyFunBrief
//
//  Row view for displaying an ignored airport entry.
//

import SwiftUI
import CoreData

/// Row view for an ignored airport
struct IgnoredAirportRowView: View {
    let ignoredAirport: CDIgnoredAirport

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // ICAO code
            Text(ignoredAirport.icaoCode ?? "????")
                .font(.headline.monospaced())

            // Reason if provided
            if let reason = ignoredAirport.reason, !reason.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "text.quote")
                        .font(.caption2)
                    Text(reason)
                        .font(.caption)
                        .italic()
                }
                .foregroundStyle(.tertiary)
            }

            // Added date
            Text("Added \(ignoredAirport.formattedCreatedAt)")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Preview

struct IgnoredAirportRowView_Previews: PreviewProvider {
    static var previews: some View {
        let context = PersistenceController.preview.viewContext
        let ignored = CDIgnoredAirport(context: context)
        ignored.id = UUID()
        ignored.icaoCode = "EGLL"
        ignored.reason = "Large commercial airport"
        ignored.createdAt = Date()
        return List {
            IgnoredAirportRowView(ignoredAirport: ignored)
        }
    }
}
