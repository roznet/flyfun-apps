//
//  FlightListView.swift
//  FlyFunBrief
//
//  List view for managing flights.
//

import SwiftUI

/// Main list view for flights
struct FlightListView: View {
    @Environment(\.appState) private var appState
    @State private var showingNewFlight = false
    @State private var showingArchived = false

    var body: some View {
        Group {
            if let flights = appState?.flights.flights, !flights.isEmpty {
                flightList(flights)
            } else {
                emptyState
            }
        }
        .navigationTitle("Flights")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showingNewFlight = true
                } label: {
                    Label("New Flight", systemImage: "plus")
                }
            }

            ToolbarItem(placement: .secondaryAction) {
                Menu {
                    Button {
                        showingArchived = true
                    } label: {
                        Label("Archived Flights", systemImage: "archivebox")
                    }
                } label: {
                    Label("More", systemImage: "ellipsis.circle")
                }
            }
        }
        .sheet(isPresented: $showingNewFlight) {
            NavigationStack {
                FlightEditorView(mode: .create)
            }
        }
        .sheet(isPresented: $showingArchived) {
            NavigationStack {
                ArchivedFlightsView()
            }
        }
        .task {
            await appState?.flights.loadFlights()
        }
    }

    // MARK: - Flight List

    @ViewBuilder
    private func flightList(_ flights: [CDFlight]) -> some View {
        List(flights, id: \.id) { flight in
            Button {
                // Directly open the flight (enters flight view mode)
                appState?.flights.openFlight(flight)
            } label: {
                FlightRowView(flight: flight)
            }
            .buttonStyle(.plain)
            .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                Button(role: .destructive) {
                    Task {
                        await appState?.flights.deleteFlight(flight)
                    }
                } label: {
                    Label("Delete", systemImage: "trash")
                }

                Button {
                    Task {
                        await appState?.flights.archiveFlight(flight)
                    }
                } label: {
                    Label("Archive", systemImage: "archivebox")
                }
                .tint(.orange)
            }
        }
        .refreshable {
            await appState?.flights.refresh()
        }
    }

    // MARK: - Empty State

    private var emptyState: some View {
        ContentUnavailableView {
            Label("No Flights", systemImage: "airplane")
        } description: {
            Text("Create a flight to start tracking NOTAMs across briefings.")
        } actions: {
            Button {
                showingNewFlight = true
            } label: {
                Label("New Flight", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
        }
    }
}

// MARK: - Archived Flights View

struct ArchivedFlightsView: View {
    @Environment(\.appState) private var appState
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Group {
            if let flights = appState?.flights.archivedFlights, !flights.isEmpty {
                List(flights, id: \.id) { flight in
                    FlightRowView(flight: flight)
                        .swipeActions(edge: .trailing) {
                            Button {
                                Task {
                                    await appState?.flights.unarchiveFlight(flight)
                                }
                            } label: {
                                Label("Restore", systemImage: "arrow.uturn.backward")
                            }
                            .tint(.blue)

                            Button(role: .destructive) {
                                Task {
                                    await appState?.flights.deleteFlight(flight)
                                }
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                }
            } else {
                ContentUnavailableView {
                    Label("No Archived Flights", systemImage: "archivebox")
                } description: {
                    Text("Archived flights will appear here.")
                }
            }
        }
        .navigationTitle("Archived")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .cancellationAction) {
                Button("Done") {
                    dismiss()
                }
            }
        }
        .task {
            await appState?.flights.loadArchivedFlights()
        }
    }
}

// MARK: - Preview

#Preview {
    NavigationStack {
        FlightListView()
    }
    .environment(\.appState, AppState.preview())
}
