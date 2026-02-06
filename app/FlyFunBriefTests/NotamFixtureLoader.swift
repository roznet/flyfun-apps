//
//  NotamFixtureLoader.swift
//  FlyFunBriefTests
//
//  Loads NOTAM text fixtures from bundled .txt files for parsing and priority tests.
//

import Foundation

// MARK: - Fixture Model

/// A single NOTAM test fixture with raw text and metadata.
struct NotamFixture {
    /// Fixture identifier (e.g., "rwy_closure_lfpg")
    let id: String

    /// Raw NOTAM text suitable for NotamParser.parse()
    let rawText: String

    /// Metadata key-value pairs from ### headers
    let metadata: [String: String]

    /// Expected Q-code from metadata (e.g., "QMRLC")
    var expectedQCode: String? { metadata["expected_qcode"] }

    /// Expected location from metadata (e.g., "LFPG")
    var expectedLocation: String? { metadata["expected_location"] }

    /// Tags from metadata as array (e.g., ["movement_area", "closure"])
    var tags: [String] {
        guard let tagString = metadata["tags"] else { return [] }
        return tagString.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
    }

    /// Whether this fixture has a specific tag
    func hasTag(_ tag: String) -> Bool {
        tags.contains(tag)
    }
}

// MARK: - Fixture Loader

enum FixtureError: Error, CustomStringConvertible {
    case fileNotFound(String)
    case noFixturesFound(String)

    var description: String {
        switch self {
        case .fileNotFound(let path): return "Fixture file not found: \(path)"
        case .noFixturesFound(let file): return "No fixtures found in: \(file)"
        }
    }
}

/// Loads NOTAM test fixtures from .txt files in the Fixtures directory.
///
/// Fixture format:
/// ```
/// ### id: rwy_closure_lfpg
/// ### expected_qcode: QMRLC
/// ### expected_location: LFPG
/// ### tags: movement_area, closure
/// A1234/24 NOTAMN
/// Q) LFFF/QMRLC/IV/NBO/A/000/999/4901N00225E005
/// ...
/// ===NOTAM===
/// ### id: next_fixture
/// ...
/// ```
enum NotamFixtureLoader {

    /// Load all fixtures from a file in the Fixtures directory.
    ///
    /// Locates the file relative to the test source file using `#file`.
    static func load(filename: String, sourceFile: String = #file) throws -> [NotamFixture] {
        let fixtureURL = findFixtureFile(filename: filename, sourceFile: sourceFile)

        guard let fixtureURL, FileManager.default.fileExists(atPath: fixtureURL.path) else {
            throw FixtureError.fileNotFound(filename)
        }

        let content = try String(contentsOf: fixtureURL, encoding: .utf8)
        let fixtures = parseFixtures(content)

        if fixtures.isEmpty {
            throw FixtureError.noFixturesFound(filename)
        }

        return fixtures
    }

    /// Load a single fixture by ID.
    static func loadFixture(id: String, filename: String = "notam_priority_samples.txt", sourceFile: String = #file) throws -> NotamFixture {
        let fixtures = try load(filename: filename, sourceFile: sourceFile)
        guard let fixture = fixtures.first(where: { $0.id == id }) else {
            throw FixtureError.noFixturesFound("Fixture with id '\(id)' not found in \(filename)")
        }
        return fixture
    }

    // MARK: - Private

    private static func findFixtureFile(filename: String, sourceFile: String) -> URL? {
        // Use source file location to find Fixtures directory relative to test files
        let sourceURL = URL(fileURLWithPath: sourceFile)
        let testDir = sourceURL.deletingLastPathComponent()
        let fixtureURL = testDir.appendingPathComponent("Fixtures").appendingPathComponent(filename)

        if FileManager.default.fileExists(atPath: fixtureURL.path) {
            return fixtureURL
        }

        return nil
    }

    private static func parseFixtures(_ content: String) -> [NotamFixture] {
        // Split on ===NOTAM=== separator
        let blocks = content.components(separatedBy: "===NOTAM===")
        var fixtures: [NotamFixture] = []

        for block in blocks {
            let trimmed = block.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { continue }

            if let fixture = parseFixtureBlock(trimmed) {
                fixtures.append(fixture)
            }
        }

        return fixtures
    }

    private static func parseFixtureBlock(_ block: String) -> NotamFixture? {
        var metadata: [String: String] = [:]
        var textLines: [String] = []

        for line in block.components(separatedBy: "\n") {
            if line.hasPrefix("### ") {
                // Parse metadata: "### key: value"
                let content = String(line.dropFirst(4))
                if let colonIndex = content.firstIndex(of: ":") {
                    let key = content[content.startIndex..<colonIndex].trimmingCharacters(in: .whitespaces)
                    let value = content[content.index(after: colonIndex)...].trimmingCharacters(in: .whitespaces)
                    metadata[key] = value
                }
            } else {
                textLines.append(line)
            }
        }

        let rawText = textLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rawText.isEmpty else { return nil }

        let id = metadata["id"] ?? "unknown"
        return NotamFixture(id: id, rawText: rawText, metadata: metadata)
    }
}
