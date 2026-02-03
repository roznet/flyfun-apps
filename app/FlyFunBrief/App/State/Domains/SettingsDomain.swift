//
//  SettingsDomain.swift
//  FlyFunBrief
//
//  Manages user preferences and settings.
//

import Foundation
import OSLog

/// Domain for user settings
@Observable
@MainActor
final class SettingsDomain {
    // MARK: - Settings

    /// API base URL for briefing parsing
    var apiBaseURL: String {
        didSet {
            UserDefaults.standard.set(apiBaseURL, forKey: Keys.apiBaseURL)
        }
    }

    /// Default grouping for NOTAM list
    var defaultGrouping: NotamGrouping {
        didSet {
            UserDefaults.standard.set(defaultGrouping.rawValue, forKey: Keys.defaultGrouping)
        }
    }

    /// Whether to auto-mark NOTAMs as read when viewing
    var autoMarkAsRead: Bool {
        didSet {
            UserDefaults.standard.set(autoMarkAsRead, forKey: Keys.autoMarkAsRead)
        }
    }

    /// Whether to show raw NOTAM text in detail view
    var showRawText: Bool {
        didSet {
            UserDefaults.standard.set(showRawText, forKey: Keys.showRawText)
        }
    }

    /// Whether to show map in NOTAM detail (when coordinates available)
    var showNotamMap: Bool {
        didSet {
            UserDefaults.standard.set(showNotamMap, forKey: Keys.showNotamMap)
        }
    }

    // MARK: - Priority Profile

    /// ID of the active priority profile (persisted)
    var priorityProfileId: String {
        didSet {
            UserDefaults.standard.set(priorityProfileId, forKey: Keys.priorityProfileId)
            onProfileChanged?(priorityProfile)
        }
    }

    /// The active priority profile
    var priorityProfile: PriorityProfile {
        PriorityProfiles.profile(for: priorityProfileId)
    }

    /// Callback when profile changes (wired by AppState)
    var onProfileChanged: ((PriorityProfile) -> Void)?

    // MARK: - Resurface Settings

    /// Days until a globally-read NOTAM resurfaces as unread
    var readResurfaceTimeDays: Int {
        didSet {
            UserDefaults.standard.set(readResurfaceTimeDays, forKey: Keys.readResurfaceTimeDays)
        }
    }

    /// Distance threshold in nm for route proximity resurface
    var readResurfaceDistanceNm: Double {
        didSet {
            UserDefaults.standard.set(readResurfaceDistanceNm, forKey: Keys.readResurfaceDistanceNm)
        }
    }

    /// Whether time-based resurfacing is enabled
    var timeResurfaceEnabled: Bool {
        didSet {
            UserDefaults.standard.set(timeResurfaceEnabled, forKey: Keys.timeResurfaceEnabled)
        }
    }

    /// Whether distance-based resurfacing is enabled
    var distanceResurfaceEnabled: Bool {
        didSet {
            UserDefaults.standard.set(distanceResurfaceEnabled, forKey: Keys.distanceResurfaceEnabled)
        }
    }

    /// Build ResurfaceSettings from current values
    var resurfaceSettings: ResurfaceSettings {
        ResurfaceSettings(
            timeDays: readResurfaceTimeDays,
            distanceNm: readResurfaceDistanceNm,
            timeResurfaceEnabled: timeResurfaceEnabled,
            distanceResurfaceEnabled: distanceResurfaceEnabled
        )
    }

    // MARK: - Keys

    private enum Keys {
        static let priorityProfileId = "priorityProfileId"
        static let apiBaseURL = "apiBaseURL"
        static let defaultGrouping = "defaultGrouping"
        static let autoMarkAsRead = "autoMarkAsRead"
        static let showRawText = "showRawText"
        static let showNotamMap = "showNotamMap"
        static let readResurfaceTimeDays = "readResurfaceTimeDays"
        static let readResurfaceDistanceNm = "readResurfaceDistanceNm"
        static let timeResurfaceEnabled = "timeResurfaceEnabled"
        static let distanceResurfaceEnabled = "distanceResurfaceEnabled"
    }

    // MARK: - Defaults

    private static let defaultAPIBaseURL = "http://localhost:8000"

    // MARK: - Init

    init() {
        // Load from UserDefaults with defaults
        self.priorityProfileId = UserDefaults.standard.string(forKey: Keys.priorityProfileId)
            ?? PriorityProfiles.default.id

        self.apiBaseURL = UserDefaults.standard.string(forKey: Keys.apiBaseURL)
            ?? Self.defaultAPIBaseURL

        if let groupingRaw = UserDefaults.standard.string(forKey: Keys.defaultGrouping),
           let grouping = NotamGrouping(rawValue: groupingRaw) {
            self.defaultGrouping = grouping
        } else {
            self.defaultGrouping = .airport
        }

        self.autoMarkAsRead = UserDefaults.standard.object(forKey: Keys.autoMarkAsRead) as? Bool ?? true
        self.showRawText = UserDefaults.standard.object(forKey: Keys.showRawText) as? Bool ?? true
        self.showNotamMap = UserDefaults.standard.object(forKey: Keys.showNotamMap) as? Bool ?? true

        // Resurface settings
        self.readResurfaceTimeDays = UserDefaults.standard.object(forKey: Keys.readResurfaceTimeDays) as? Int ?? 7
        self.readResurfaceDistanceNm = UserDefaults.standard.object(forKey: Keys.readResurfaceDistanceNm) as? Double ?? 25.0
        self.timeResurfaceEnabled = UserDefaults.standard.object(forKey: Keys.timeResurfaceEnabled) as? Bool ?? true
        self.distanceResurfaceEnabled = UserDefaults.standard.object(forKey: Keys.distanceResurfaceEnabled) as? Bool ?? true
    }

    // MARK: - Actions

    /// Restore settings from storage
    func restore() {
        Logger.app.info("Settings restored")
    }

    /// Save settings
    func save() {
        // Settings are auto-saved via didSet, but this can be used for explicit saves
        Logger.app.info("Settings saved")
    }

    /// Reset to defaults
    func resetToDefaults() {
        priorityProfileId = PriorityProfiles.default.id
        apiBaseURL = Self.defaultAPIBaseURL
        defaultGrouping = .airport
        autoMarkAsRead = true
        showRawText = true
        showNotamMap = true
        readResurfaceTimeDays = 7
        readResurfaceDistanceNm = 25.0
        timeResurfaceEnabled = true
        distanceResurfaceEnabled = true
        Logger.app.info("Settings reset to defaults")
    }
}
