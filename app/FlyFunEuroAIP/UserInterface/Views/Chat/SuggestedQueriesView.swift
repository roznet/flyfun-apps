//
//  SuggestedQueriesView.swift
//  FlyFunEuroAIP
//
//  Displays suggested follow-up queries as tappable chips.
//

import SwiftUI

struct SuggestedQueriesView: View {
    let queries: [SuggestedQuery]
    let onSelect: (SuggestedQuery) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(queries) { query in
                    Button {
                        onSelect(query)
                    } label: {
                        Text(query.text)
                            .font(.caption)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.accentColor.opacity(0.1))
                            .foregroundColor(.accentColor)
                            .cornerRadius(16)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)
        }
        .frame(height: 36)
    }
}

// MARK: - Preview

#Preview("With Queries") {
    VStack {
        Spacer()
        SuggestedQueriesView(
            queries: [
                SuggestedQuery(text: "Show airports with ILS"),
                SuggestedQuery(text: "Filter by country France"),
                SuggestedQuery(text: "Find border crossings")
            ],
            onSelect: { query in
                print("Selected: \(query.text)")
            }
        )
    }
}

#Preview("Empty") {
    SuggestedQueriesView(
        queries: [],
        onSelect: { _ in }
    )
}
